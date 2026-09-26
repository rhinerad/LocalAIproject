#!/usr/bin/env python3
"""Source-backed claims and citation-behavior regression suite (stdlib only).

Tests verify that:
- tool results carry explicit source metadata (URL, file path, doc source)
- artifact pointers preserve that metadata even after pruning
- the agent system prompt includes the citation contract
- _tool_source_label extracts the right label for each tool type
- no stale H3/ComfyUI source leaks into unrelated answers

Does not require Ollama, a GPU, or any external dependency.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import artifacts
import tools


class SourceLabelExtractionTests(unittest.TestCase):
    """_tool_source_label pulls the right provenance from each tool result."""

    def test_fetch_url_label_is_the_fetched_url(self):
        result = "[https://example.com/page]\n\nPage content here."
        label = agent._tool_source_label("fetch_url", result)
        self.assertEqual("https://example.com/page", label)

    def test_fetch_url_with_redirect_label_is_final_url(self):
        result = "[https://example.com/final]\n[redirected from https://example.com/old]\n\nContent."
        label = agent._tool_source_label("fetch_url", result)
        self.assertEqual("https://example.com/final", label)

    def test_web_search_label_includes_backend_and_query(self):
        result = "[duckduckgo: Python asyncio]\n\n1. Title\n   https://example.com\n   Snippet."
        label = agent._tool_source_label("web_search", result)
        self.assertEqual("duckduckgo: Python asyncio", label)

    def test_search_docs_label_lists_source_paths(self):
        payload = {
            "query": "duration ladder",
            "results": [
                {"source": "docs/H3_PROMPT_RULES.md", "heading": "## §10", "text": "..."},
                {"source": "CLAUDE.md", "heading": "## Duration", "text": "..."},
            ],
        }
        result = json.dumps(payload)
        label = agent._tool_source_label("search_docs", result)
        self.assertIn("docs/H3_PROMPT_RULES.md", label)
        self.assertIn("CLAUDE.md", label)

    def test_search_docs_empty_results_returns_none(self):
        result = json.dumps({"query": "xyz", "results": []})
        label = agent._tool_source_label("search_docs", result)
        self.assertIsNone(label)

    def test_read_file_label_is_the_file_path(self):
        result = "[File: A:\\Users\\rhine\\some_file.txt]\n\nHello world."
        label = agent._tool_source_label("read_file", result)
        self.assertEqual("A:\\Users\\rhine\\some_file.txt", label)

    def test_list_dir_label_is_directory_path(self):
        result = "A:\\Users\\rhine\\some_dir\n    file1.txt\n    file2.txt"
        label = agent._tool_source_label("list_dir", result)
        self.assertEqual("A:\\Users\\rhine\\some_dir", label)

    def test_list_memory_label_is_persistent_memory(self):
        result = "[Source: persistent memory]\nno facts remembered yet"
        label = agent._tool_source_label("list_memory", result)
        self.assertEqual("persistent memory", label)

    def test_remember_fact_label_is_persistent_memory(self):
        result = "fact stored (id=42)"
        label = agent._tool_source_label("remember_fact", result)
        self.assertEqual("persistent memory", label)

    def test_untracked_tool_returns_none(self):
        label = agent._tool_source_label("project_state", '{"clips": 124}')
        self.assertIsNone(label)

    def test_gpu_state_tool_returns_none(self):
        label = agent._tool_source_label("propose_gpu", '{"action": "render_auditions"}')
        self.assertIsNone(label)


class ArtifactSourceLabelTests(unittest.TestCase):
    """prune_large_text embeds source_label in the pruned pointer."""

    def test_source_label_included_in_pruned_pointer(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(artifacts, "ARTIFACT_DIR", Path(td)):
                text = "A" * 3000
                pointer = artifacts.prune_large_text(
                    "tool:fetch_url", text, limit=2400,
                    source_label="https://example.com/page")
        self.assertIn("output pruned", pointer)
        self.assertIn("source=https://example.com/page", pointer)
        self.assertIn("artifact_id=", pointer)

    def test_no_source_label_produces_unchanged_format(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(artifacts, "ARTIFACT_DIR", Path(td)):
                text = "B" * 3000
                pointer = artifacts.prune_large_text("tool:project_state", text, limit=2400)
        self.assertIn("output pruned", pointer)
        self.assertNotIn("source=", pointer)
        self.assertIn("artifact_id=", pointer)

    def test_small_result_is_returned_unchanged_regardless_of_label(self):
        result = artifacts.prune_large_text(
            "tool:fetch_url", "short text", limit=2400,
            source_label="https://example.com")
        self.assertEqual("short text", result)

    def test_source_label_survives_real_url_fetch_sized_result(self):
        url = "https://example.com/doc"
        big_content = "[%s]\n\n" % url + "X" * 3000
        with tempfile.TemporaryDirectory() as td:
            with patch.object(artifacts, "ARTIFACT_DIR", Path(td)):
                label = agent._tool_source_label("fetch_url", big_content)
                pointer = artifacts.prune_large_text(
                    "tool:fetch_url", big_content, limit=2400,
                    source_label=label)
        self.assertIn(url, pointer)


class ToolResultSourceHeaderTests(unittest.TestCase):
    """read_file and list_memory include source headers in their results."""

    def test_read_file_result_has_file_header(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "notes.txt"
            p.write_text("Hello from file.", encoding="utf-8")
            with patch.object(tools, "ROOT", Path(td)):
                result = tools.call("read_file", {"path": str(p)})
        self.assertTrue(result.startswith("[File: "))
        self.assertIn("Hello from file.", result)

    def test_read_file_label_extractable_from_header(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.json"
            p.write_text('{"key": "value"}', encoding="utf-8")
            with patch.object(tools, "ROOT", Path(td)):
                result = tools.call("read_file", {"path": str(p)})
        label = agent._tool_source_label("read_file", result)
        self.assertEqual(str(p.resolve()), label)

    def test_list_memory_result_has_source_header(self):
        import memory as _mem
        with tempfile.TemporaryDirectory() as td:
            facts_path = Path(td) / "memory.json"
            with patch.object(_mem, "_STORE", facts_path):
                result = tools.call("list_memory", {})
        self.assertIn("[Source: persistent memory]", result)


class AgentCitationContractTests(unittest.TestCase):
    """The system prompt carries the citation contract."""

    def test_conversation_rules_contain_source_citation_section(self):
        rules = agent.CONVERSATION_RULES
        self.assertIn("# Source citation", rules)
        self.assertIn("unverified", rules)
        self.assertIn("from model knowledge", rules)

    def test_citation_section_covers_web_internet(self):
        rules = agent.CONVERSATION_RULES
        self.assertIn("Web / internet", rules)
        self.assertIn("URL", rules)

    def test_citation_section_covers_project_docs(self):
        rules = agent.CONVERSATION_RULES
        self.assertIn("Project documents", rules)
        self.assertIn("file path", rules)

    def test_citation_section_covers_memory(self):
        rules = agent.CONVERSATION_RULES
        self.assertIn("Memory and prior chats", rules)
        self.assertIn("persistent memory", rules)

    def test_citation_exception_covers_creative_writing(self):
        rules = agent.CONVERSATION_RULES
        self.assertIn("creative writing", rules)
        self.assertIn("brainstorming", rules)


class NoStaleSpecialistSourceTests(unittest.TestCase):
    """Stale H3/ComfyUI context must not surface in unrelated answers."""

    def test_specialist_scope_guard_blocks_render_source_in_unrelated_turn(self):
        import ollama_client as oll
        import router

        class _Route:
            tier = "cpu"
            host = "127.0.0.1:11435"
            model = "stub-model"
            def options(self): return {}
            def as_dict(self): return {"tier": self.tier, "host": self.host, "model": self.model}

        stale_reply = ("Based on the Equal Shares render config, the H3 minimax node "
                       "batch_render should handle that.")

        replies = iter(["Fixed grounded answer.", stale_reply])

        def fake_stream(messages, **_kwargs):
            yield next(replies)

        with patch.object(agent.router, "gpu_busy", return_value=(True, "test", {})), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer([
                {"role": "user",
                 "content": "How do I write a Python function that reverses a list?"},
            ], prefer="cpu")

        self.assertNotIn("Equal Shares", reply)
        self.assertNotIn("batch_render", reply)


if __name__ == "__main__":
    unittest.main()
