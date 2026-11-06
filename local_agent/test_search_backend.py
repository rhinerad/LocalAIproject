#!/usr/bin/env python3
"""Stdlib tests for the pluggable search backend."""
from __future__ import annotations

import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import search_backend
import tools

DDG_HTML = """<!DOCTYPE html><html><head><title>DuckDuckGo</title></head><body>
""" + ("<!-- duckduckgo padding -->" * 40) + """
<table>
<tr><td>1.&nbsp;</td><td>
<a rel="nofollow" class="result-link"
   href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Falpha">Alpha Title</a>
</td></tr>
<tr><td></td><td class="result-snippet">Alpha snippet about the topic.</td></tr>
<tr><td>2.&nbsp;</td><td>
<a rel="nofollow" class="result-link"
   href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fbeta">Beta Title</a>
</td></tr>
<tr><td></td><td class="result-snippet">Beta snippet continues the subject.</td></tr>
</table>
</body></html>
"""


class _FakeResp:
    def __init__(self, body: str, status: int = 200):
        self.status = status
        self._body = body.encode("utf-8")

    def read(self, _n=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SearchBackendTests(unittest.TestCase):

    def test_ddg_parses_structured_results(self):
        with patch("urllib.request.urlopen", return_value=_FakeResp(DDG_HTML)):
            items = search_backend.DuckDuckGoBackend().search("python", max_results=8)
        self.assertEqual(2, len(items))
        self.assertEqual("https://example.com/alpha", items[0]["url"])
        self.assertEqual("Alpha Title", items[0]["title"])
        self.assertIn("Alpha snippet", items[0]["snippet"])

    def test_web_search_formats_text_via_interface(self):
        with patch("urllib.request.urlopen", return_value=_FakeResp(DDG_HTML)):
            text = tools.web_search({"query": "python"})
        self.assertTrue(text.startswith("[duckduckgo: python]"))
        self.assertIn("https://example.com/alpha", text)
        self.assertIn("Alpha Title", text)

    def test_env_selects_duckduckgo(self):
        with patch.dict(os.environ, {"EQUAL_SHARES_SEARCH_BACKEND": "duckduckgo"}, clear=False):
            backend = search_backend.get_backend()
        self.assertEqual("duckduckgo", backend.name)
        self.assertIsInstance(backend, search_backend.DuckDuckGoBackend)

    def test_unknown_backend_raises_helpful_error(self):
        with patch.dict(os.environ, {"EQUAL_SHARES_SEARCH_BACKEND": "bing"}, clear=False):
            with self.assertRaises(search_backend.SearchError) as ctx:
                search_backend.get_backend()
        self.assertEqual("unknown-backend", ctx.exception.code)
        self.assertIn("EQUAL_SHARES_SEARCH_BACKEND", str(ctx.exception))
        self.assertIn("duckduckgo", str(ctx.exception))

    def test_stub_keyed_backend_needs_api_key(self):
        with patch.dict(os.environ, {"EQUAL_SHARES_SEARCH_BACKEND": "brave",
                                     "EQUAL_SHARES_SEARCH_API_KEY": ""}, clear=False):
            os.environ.pop("EQUAL_SHARES_SEARCH_API_KEY", None)
            backend = search_backend.get_backend()
            with self.assertRaises(search_backend.SearchError) as ctx:
                backend.search("anything")
        self.assertEqual("needs-api-key", ctx.exception.code)
        self.assertIn("EQUAL_SHARES_SEARCH_API_KEY", str(ctx.exception))
        self.assertIn("brave", str(ctx.exception))

    def test_zero_results_is_not_silent_empty(self):
        html = "<html>duckduckgo No results.</html>" + ("x" * 500)
        with patch("urllib.request.urlopen", return_value=_FakeResp(html)):
            with self.assertRaises(search_backend.SearchError) as ctx:
                search_backend.DuckDuckGoBackend().search("zzz")
        self.assertEqual("zero-results", ctx.exception.code)

    def test_no_internet(self):
        err = urllib.error.URLError(OSError("Network is unreachable"))
        with patch("urllib.request.urlopen", side_effect=err):
            text = tools.web_search({"query": "python"})
        self.assertIn("No internet connection", text)


if __name__ == "__main__":
    unittest.main()
