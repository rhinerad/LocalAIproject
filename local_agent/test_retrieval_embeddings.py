#!/usr/bin/env python3
"""Tests for EmbeddingScorer / HybridScorer (RAG_EVALUATION.md Stages 1-2).

All Ollama calls are mocked — these tests never reach a real Ollama endpoint
and never touch the GPU. Embedding cache reads/writes go to a temp file so
they never disturb the real `knowledge/retrieval_embeddings.json`.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import retrieval


def _chunk(cid: str, text: str) -> dict:
    return {"id": cid, "source": "docs/x.md", "heading": "", "text": text}


class _TempCache:
    """Point the module's embedding cache at a throwaway temp file/state.

    Also mocks farm_offload.try_embed_on_farm to return None so a live farm
    worker doesn't bypass the ollama_client.embed mock these tests set up.
    The farm call is a real external dependency (subprocess → broker → worker);
    leaving it unpatched would make the tests non-deterministic when mac_worker
    is running and return real vectors instead of the test's fixed mock values.
    """

    def __enter__(self):
        from unittest.mock import patch as _patch
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_file = retrieval.EMBEDDING_CACHE_FILE
        self._old_cache = retrieval._EMBED_CACHE
        retrieval.EMBEDDING_CACHE_FILE = Path(self._tmpdir.name) / "retrieval_embeddings.json"
        retrieval._EMBED_CACHE = None
        self._farm_patch = _patch("farm_offload.try_embed_on_farm", return_value=None)
        self._farm_patch.start()
        return self

    def __exit__(self, *exc):
        self._farm_patch.stop()
        retrieval.EMBEDDING_CACHE_FILE = self._old_file
        retrieval._EMBED_CACHE = self._old_cache
        self._tmpdir.cleanup()


class EmbeddingScorerTests(unittest.TestCase):
    def test_embeds_and_ranks_by_cosine_similarity(self):
        chunks = [_chunk("a:0", "routing fallback keeps GPU work isolated"),
                  _chunk("a:1", "an unrelated note about lunch")]
        with _TempCache():
            with patch("ollama_client.embed") as mock_embed:
                # First call embeds the two chunks (batch), second embeds the query.
                mock_embed.side_effect = [
                    [[1.0, 0.0], [0.0, 1.0]],
                    [[1.0, 0.0]],
                ]
                scorer = retrieval.EmbeddingScorer()
                ranked = scorer.score("routing fallback", chunks)
        self.assertEqual(ranked[0][1]["id"], "a:0")
        self.assertAlmostEqual(ranked[0][0], 1.0, places=5)
        self.assertAlmostEqual(ranked[1][0], 0.0, places=5)

    def test_caches_vectors_and_does_not_re_embed_unchanged_chunks(self):
        chunks = [_chunk("a:0", "stable text")]
        with _TempCache():
            with patch("ollama_client.embed") as mock_embed:
                mock_embed.return_value = [[1.0, 0.0]]
                scorer = retrieval.EmbeddingScorer()
                scorer.vectors_for(chunks)
                self.assertEqual(mock_embed.call_count, 1)
                # Second call with the same chunk id + text must hit the cache.
                scorer.vectors_for(chunks)
                self.assertEqual(mock_embed.call_count, 1)

    def test_edited_chunk_text_invalidates_its_own_cache_entry_only(self):
        with _TempCache():
            with patch("ollama_client.embed") as mock_embed:
                mock_embed.return_value = [[1.0, 0.0]]
                scorer = retrieval.EmbeddingScorer()
                scorer.vectors_for([_chunk("a:0", "original text")])
                self.assertEqual(mock_embed.call_count, 1)
                # Same id, different text (file edited) -> must re-embed.
                mock_embed.return_value = [[0.0, 1.0]]
                vectors = scorer.vectors_for([_chunk("a:0", "edited text")])
                self.assertEqual(mock_embed.call_count, 2)
                self.assertEqual(vectors["a:0"], [0.0, 1.0])


class HybridScorerTests(unittest.TestCase):
    def test_fuses_lexical_and_embedding_hits(self):
        chunks = [
            _chunk("a:0", "duration ladder retries base seed"),
            _chunk("a:1", "an unrelated paragraph about lunch plans"),
        ]
        with _TempCache():
            with patch("ollama_client.embed") as mock_embed:
                mock_embed.side_effect = [
                    [[1.0, 0.0], [0.0, 1.0]],  # chunk vectors
                    [[1.0, 0.0]],              # query vector
                ]
                scorer = retrieval.HybridScorer()
                ranked = scorer.score("duration ladder retries", chunks)
        ids = [ch["id"] for _, ch in ranked]
        self.assertIn("a:0", ids)
        self.assertEqual(ids[0], "a:0")

    def test_excludes_chunks_below_both_relevance_bars(self):
        # Nothing shares lexical terms and the embedding similarity is weak
        # (below MIN_EMBED_SIMILARITY) -> must return empty, not "closest anyway".
        chunks = [_chunk("a:0", "completely unrelated content about weather")]
        with _TempCache():
            with patch("ollama_client.embed") as mock_embed:
                mock_embed.side_effect = [
                    [[1.0, 0.0]],   # chunk vector
                    [[0.0, 1.0]],   # query vector -> cosine 0.0, orthogonal
                ]
                scorer = retrieval.HybridScorer()
                ranked = scorer.score("duration ladder retries", chunks)
        self.assertEqual(ranked, [])

    def test_falls_back_to_lexical_only_when_embedding_endpoint_unavailable(self):
        chunks = [_chunk("a:0", "duration ladder retries base seed")]
        with _TempCache():
            with patch("ollama_client.embed", side_effect=ConnectionError("no ollama")):
                scorer = retrieval.HybridScorer()
                ranked = scorer.score("duration ladder retries", chunks)
        self.assertEqual([ch["id"] for _, ch in ranked], ["a:0"])

    def test_search_uses_hybrid_scorer_when_explicitly_passed(self):
        chunks = [_chunk("a:0", "duration ladder retries base seed")]
        fake_index = {"chunks": chunks}
        with _TempCache():
            with patch.object(retrieval, "_get_index", return_value=fake_index):
                with patch("ollama_client.embed") as mock_embed:
                    mock_embed.side_effect = [[[1.0, 0.0]], [[1.0, 0.0]]]
                    results = retrieval.search(
                        "duration ladder retries", scorer=retrieval.HybridScorer())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "docs/x.md")



class DefaultHybridScorerTests(unittest.TestCase):
    def test_module_default_scorer_is_hybrid(self):
        self.assertIsInstance(retrieval._DEFAULT_SCORER, retrieval.HybridScorer)

    def test_search_without_scorer_uses_hybrid_and_tags_match_by(self):
        chunks = [_chunk("a:0", "duration ladder retries base seed")]
        fake_index = {"chunks": chunks}
        with _TempCache():
            with patch.object(retrieval, "_get_index", return_value=fake_index):
                with patch("ollama_client.embed") as mock_embed:
                    mock_embed.side_effect = [[[1.0, 0.0]], [[1.0, 0.0]]]
                    results = retrieval.search("duration ladder retries")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "docs/x.md")
        self.assertEqual(results[0].get("match_by"), "both")
        self.assertGreaterEqual(mock_embed.call_count, 1)


class SessionLexicalVsHybridComparisonTests(unittest.TestCase):
    """2026-09-02ab Stage 5 cheap comparison — not a large eval.

    Mocked fixture: Hybrid must recall a semantic paraphrase Lexical misses
    and must not lose the lexical hit. On-disk: with the embedding endpoint
    failing, Hybrid's top-5 ids must match Lexical (fallback is not worse).
    """

    def test_mocked_fixture_hybrid_not_worse_than_lexical(self):
        relevant = _chunk(
            "rel:0",
            "Broker reachability is confirmed by a TCP check of the host "
            "parsed from FARM_BROKER_URL, then a Celery inspect.ping() for "
            "process liveness. Failures become unreachable or no_workers.",
        )
        distractor = _chunk(
            "d:0",
            "The prompt prefix sections are deterministically ordered and "
            "cached with lru_cache.",
        )
        chunks = [relevant, distractor]
        lexical_query = "Celery inspect ping liveness"
        semantic_query = "tell whether queued task daemons died"

        lex = retrieval.LexicalScorer()
        lex_lex = [ch["id"] for s, ch in lex.score(lexical_query, chunks) if s > 0]
        lex_sem = [ch["id"] for s, ch in lex.score(semantic_query, chunks) if s > 0]

        def embed_side(texts, **kwargs):
            out = []
            for t in texts:
                tl = t.lower()
                if "prompt prefix" in tl or "lru_cache" in tl:
                    out.append([0.0, 1.0])
                else:
                    # relevant chunk + both queries align on the same axis
                    out.append([1.0, 0.0])
            return out

        with _TempCache():
            with patch("ollama_client.embed", side_effect=embed_side):
                hybrid = retrieval.HybridScorer()
                hy_lex = [ch["id"] for s, ch in hybrid.score(lexical_query, chunks) if s > 0]
                hy_sem = [ch["id"] for s, ch in hybrid.score(semantic_query, chunks) if s > 0]

        self.assertIn("rel:0", lex_lex)
        self.assertIn("rel:0", hy_lex)
        self.assertIn("rel:0", hy_sem)
        lex_recall = int("rel:0" in lex_lex) + int("rel:0" in lex_sem)
        hy_recall = int("rel:0" in hy_lex) + int("rel:0" in hy_sem)
        self.assertGreaterEqual(hy_recall, lex_recall)
        self.assertGreaterEqual(hy_recall, 2)
        # Fixture numbers for the changelog: lexical semantic miss is expected.
        self.assertNotIn("rel:0", lex_sem)

    def test_on_disk_hybrid_fallback_matches_lexical_top5(self):
        idx = retrieval._get_index()
        chunks = idx.get("chunks") or []
        self.assertGreater(len(chunks), 10)
        queries = [
            "source citation contract",
            "changelog letter convention",
            "farm status snapshot daemon",
        ]
        lex = retrieval.LexicalScorer()
        with _TempCache():
            with patch("ollama_client.embed", side_effect=ConnectionError("offline")):
                hybrid = retrieval.HybridScorer()
                for q in queries:
                    lex_ids = [ch["id"] for s, ch in lex.score(q, chunks) if s > 0][:5]
                    hy_ids = [ch["id"] for s, ch in hybrid.score(q, chunks) if s > 0][:5]
                    self.assertEqual(lex_ids, hy_ids, q)

if __name__ == "__main__":
    unittest.main()
