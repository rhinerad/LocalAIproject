"""Retrieval cache fixes (AUDIT_2026-11-02 P2 "Retrieval").

- vectors keyed by chunk-text hash; legacy id-keyed caches migrate on load
- new vectors persisted after every embed batch (partial builds survive)
- BM25 tf/df computed once per chunk list and reused
- float32 array vectors with precomputed norms give the same ranking
- file index keyed by content hash, so a fresh clone (new mtimes) re-chunks
  and rewrites nothing
- orphan vectors pruned when their text leaves the index

Everything runs against temp files; no Ollama, no farm.
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import retrieval  # noqa: E402


class _CacheBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.cache_file = self.dir / "retrieval_embeddings.json"
        for name, value in (("EMBEDDING_CACHE_FILE", self.cache_file),
                            ("_EMBED_CACHE", None)):
            p = patch.object(retrieval, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(retrieval._FAST_VECTORS.clear)
        # Keep the farm out of it.
        p = patch("farm_offload.should_route", return_value=False)
        p.start()
        self.addCleanup(p.stop)


class ContentHashKeyTests(_CacheBase):
    def test_vectors_are_stored_under_the_text_hash(self):
        scorer = retrieval.EmbeddingScorer()
        chunk = {"id": "a.md:0", "text": "alpha text"}
        with patch.object(scorer, "_embed", return_value=[[1.0, 0.0]]):
            scorer.vectors_for([chunk])
        saved = json.loads(self.cache_file.read_text(encoding="utf-8"))
        self.assertEqual(retrieval.CACHE_VERSION, saved["version"])
        self.assertEqual({retrieval._chunk_hash("alpha text"): [1.0, 0.0]}, saved["vectors"])

    def test_moved_chunk_with_same_text_is_not_re_embedded(self):
        scorer = retrieval.EmbeddingScorer()
        with patch.object(scorer, "_embed", return_value=[[1.0, 0.0]]):
            scorer.vectors_for([{"id": "old/a.md:0", "text": "same words"}])
        with patch.object(scorer, "_embed", side_effect=AssertionError("re-embedded")):
            out = scorer.vectors_for([{"id": "new/a.md:3", "text": "same words"}])
        self.assertEqual({"new/a.md:3": [1.0, 0.0]}, out)

    def test_legacy_id_keyed_cache_migrates_on_load(self):
        h = retrieval._chunk_hash("legacy")
        self.cache_file.write_text(json.dumps({
            "model": retrieval.EMBED_MODEL,
            "vectors": {"doc.md:0": {"hash": h, "vector": [0.5, 0.5]},
                        "broken": {"hash": 7}},
        }), encoding="utf-8")
        cache = retrieval._load_embedding_cache()
        self.assertEqual({h: [0.5, 0.5]}, cache["vectors"])
        self.assertEqual([0.5, 0.5],
                         retrieval.cached_vector(cache, {"id": "x", "text": "legacy"}))

    def test_edited_text_is_stale(self):
        cache = {"vectors": {retrieval._chunk_hash("v1"): [1.0]}}
        self.assertIsNone(retrieval.cached_vector(cache, {"id": "a", "text": "v2"}))

    def test_corrupt_cache_file_starts_empty(self):
        self.cache_file.write_text("[1, 2", encoding="utf-8")
        self.assertEqual({}, retrieval._load_embedding_cache()["vectors"])


class PerBatchPersistenceTests(_CacheBase):
    def test_finished_batches_survive_a_later_batch_failure(self):
        scorer = retrieval.EmbeddingScorer()
        n = retrieval._EMBED_BATCH + 3
        chunks = [{"id": f"c{i}", "text": f"text {i}"} for i in range(n)]
        calls = []

        def embed(texts):
            calls.append(len(texts))
            if len(calls) == 2:
                raise ConnectionError("ollama went away")
            return [[float(i), 1.0] for i in range(len(texts))]

        with patch.object(scorer, "_embed", side_effect=embed):
            with self.assertRaises(ConnectionError):
                scorer.vectors_for(chunks)
        saved = json.loads(self.cache_file.read_text(encoding="utf-8"))
        self.assertEqual(retrieval._EMBED_BATCH, len(saved["vectors"]))

        # The retry embeds only what is still missing.
        retry = []
        with patch.object(scorer, "_embed",
                          side_effect=lambda t: retry.append(len(t)) or [[9.0, 9.0]] * len(t)):
            out = scorer.vectors_for(chunks)
        self.assertEqual([3], retry)
        self.assertEqual(n, len(out))

    def test_each_batch_triggers_a_save(self):
        scorer = retrieval.EmbeddingScorer()
        chunks = [{"id": f"c{i}", "text": f"t{i}"} for i in range(retrieval._EMBED_BATCH * 2)]
        with patch.object(scorer, "_embed", side_effect=lambda t: [[1.0]] * len(t)), \
             patch.object(retrieval, "_save_embedding_cache") as save:
            scorer.vectors_for(chunks)
        self.assertEqual(2, save.call_count)


class FastVectorScoringTests(_CacheBase):
    def test_array_scoring_matches_list_cosine(self):
        scorer = retrieval.EmbeddingScorer()
        chunks = [{"id": "a", "text": "a"}, {"id": "b", "text": "b"}, {"id": "c", "text": "c"}]
        vecs = {"a": [1.0, 0.0, 0.0], "b": [0.6, 0.8, 0.0], "c": [0.0, 0.0, 0.0]}
        q = [0.8, 0.6, 0.0]
        with patch.object(scorer, "vectors_for", return_value=vecs), \
             patch.object(scorer, "_embed", return_value=[q]):
            ranked = scorer.score("query", chunks)
        self.assertEqual(["b", "a", "c"], [c["id"] for _, c in ranked])
        for sim, ch in ranked:
            self.assertAlmostEqual(retrieval._cosine(q, vecs[ch["id"]]), sim, places=5)
        self.assertTrue(all(isinstance(v[0], retrieval.array)
                            for v in retrieval._FAST_VECTORS.values()))

    def test_dimension_mismatch_scores_zero(self):
        scorer = retrieval.EmbeddingScorer()
        with patch.object(scorer, "vectors_for", return_value={"a": [1.0, 0.0]}), \
             patch.object(scorer, "_embed", return_value=[[1.0, 0.0, 0.0]]):
            ranked = scorer.score("q", [{"id": "a", "text": "a"}])
        self.assertEqual(0.0, ranked[0][0])

    def test_norm_is_precomputed(self):
        arr, norm = retrieval._fast([3.0, 4.0])
        self.assertAlmostEqual(5.0, norm)
        self.assertEqual("f", arr.typecode)


class LexicalStatsTests(unittest.TestCase):
    def test_stats_computed_once_per_chunk_list(self):
        chunks = [{"id": "1", "text": "duration ladder retries"},
                  {"id": "2", "text": "thermal guard ceiling"}]
        retrieval._LEX_CACHE.clear()
        real = retrieval.re.findall
        count = []

        def counting(pattern, text, *a):
            count.append(1)
            return real(pattern, text, *a)

        lex = retrieval.LexicalScorer()
        with patch.object(retrieval.re, "findall", side_effect=counting):
            lex.score("duration", chunks)
            first = len(count)
            lex.score("thermal", chunks)
            second = len(count) - first
        self.assertEqual(3, first, "2 chunk tokenisations + 1 query")
        self.assertEqual(1, second, "only the query is tokenised again")

    def test_appended_chunk_invalidates(self):
        chunks = [{"id": "1", "text": "alpha"}]
        retrieval._lexical_stats(chunks)
        chunks.append({"id": "2", "text": "beta"})
        tf, df, lengths = retrieval._lexical_stats(chunks)
        self.assertEqual(2, len(tf))
        self.assertIn("beta", df)

    def test_bm25_ranking_unchanged(self):
        chunks = [{"id": "1", "text": "cat cat dog"}, {"id": "2", "text": "dog"},
                  {"id": "3", "text": "bird"}]
        ranked = retrieval.LexicalScorer().score("cat", chunks)
        self.assertEqual("1", ranked[0][1]["id"])
        self.assertEqual(0.0, ranked[-1][0])
        n, df, N = 1, 1, 3
        idf = math.log((N - n + 0.5) / (n + 0.5) + 1)
        self.assertGreater(ranked[0][0], 0.0)
        self.assertLess(ranked[0][0], idf * (retrieval.LexicalScorer.K1 + 1) + 1e-9)
        del df


class IndexKeyAndPruneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.root = root
        (root / "docs").mkdir()
        self.doc = root / "docs" / "a.md"
        self.doc.write_text("# A\n\nalpha section text\n", encoding="utf-8")
        (root / "docs" / "b.md").write_text("# B\n\nbeta section text\n", encoding="utf-8")
        knowledge = root / "knowledge"
        self.index_file = knowledge / "retrieval_index.json"
        self.cache_file = knowledge / "retrieval_embeddings.json"
        for name, value in (("ROOT", root), ("INDEX_FILE", self.index_file),
                            ("EMBEDDING_CACHE_FILE", self.cache_file),
                            ("SOURCE_GLOBS", ["docs/*.md"]),
                            ("_EMBED_CACHE", None), ("_INDEX_CACHE", None)):
            p = patch.object(retrieval, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_chunks_carry_their_content_hash(self):
        idx = retrieval.load_index()
        for c in idx["chunks"]:
            self.assertEqual(retrieval._chunk_hash(c["text"]), c["hash"])

    def test_new_mtime_same_content_reuses_chunks(self):
        retrieval.load_index()
        later = time.time() + 100
        os.utime(self.doc, (later, later))
        with patch.object(retrieval, "_build_file_chunks",
                          side_effect=AssertionError("re-chunked unchanged file")):
            idx = retrieval.load_index()
        self.assertEqual(2, len(idx["files"]))
        stored = json.loads(self.index_file.read_text(encoding="utf-8"))
        self.assertTrue(stored["files"]["docs/a.md"]["key"].startswith("sha1:"))
        self.assertEqual(retrieval._file_stat(self.doc), stored["files"]["docs/a.md"]["stat"])

    def test_unchanged_tree_does_not_rewrite_the_index(self):
        retrieval.load_index()
        with patch.object(retrieval, "atomic_write_text",
                          side_effect=AssertionError("index rewritten")):
            idx = retrieval.load_index()
        self.assertEqual(2, len(idx["chunks"]))

    def test_old_mtime_size_index_upgrades_without_losing_vectors(self):
        retrieval.load_index()
        data = json.loads(self.index_file.read_text(encoding="utf-8"))
        for fd in data["files"].values():
            fd["key"] = "123:45"          # pre-2026-11 key format
            fd.pop("stat", None)
            for c in fd["chunks"]:
                c.pop("hash", None)
        self.index_file.write_text(json.dumps(data), encoding="utf-8")
        idx = retrieval.load_index()
        self.assertTrue(all(c.get("hash") for c in idx["chunks"]))

    def test_removed_file_prunes_its_vectors(self):
        idx = retrieval.load_index()
        cache = {"model": retrieval.EMBED_MODEL,
                 "vectors": {c["hash"]: [1.0] for c in idx["chunks"]}}
        cache["vectors"]["f" * 40] = [2.0]              # an orphan already
        self.cache_file.write_text(json.dumps(cache), encoding="utf-8")
        retrieval._EMBED_CACHE = None
        gone = {c["hash"] for c in idx["chunks"] if c["source"] == "docs/b.md"}
        (self.root / "docs" / "b.md").unlink()
        idx = retrieval.load_index()
        saved = json.loads(self.cache_file.read_text(encoding="utf-8"))["vectors"]
        self.assertEqual({c["hash"] for c in idx["chunks"]}, set(saved))
        self.assertFalse(gone & set(saved))

    def test_redirected_cache_elsewhere_is_never_pruned(self):
        other = Path(self.tmp.name) / "elsewhere" / "retrieval_embeddings.json"
        other.parent.mkdir()
        other.write_text(json.dumps({"vectors": {"x" * 40: [1.0]}}), encoding="utf-8")
        with patch.object(retrieval, "EMBEDDING_CACHE_FILE", other):
            retrieval.load_index(force_rebuild=True)
        self.assertIn("x" * 40, json.loads(other.read_text(encoding="utf-8"))["vectors"])


if __name__ == "__main__":
    unittest.main()
