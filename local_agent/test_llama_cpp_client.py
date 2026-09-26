#!/usr/bin/env python3
"""llama_cpp_client.chat: what reaches the llama-server request body.

No server: urllib.request.urlopen is patched and the JSON body captured.
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import llama_cpp_client


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture(options: dict | None):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _Response(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8"))

    with patch.object(llama_cpp_client.urllib.request, "urlopen", side_effect=fake_urlopen):
        text, raw = llama_cpp_client.chat(
            [{"role": "system", "content": "s"}, {"role": "user", "content": "u", "images": ["QUJD"]}],
            host="127.0.0.1:1", model="m", options=options)
    seen["text"] = text
    return seen


class ChatBodyTests(unittest.TestCase):
    def test_repeat_penalty_and_sampler_fields_are_forwarded(self):
        # 2026-09-24: media_tools sets repeat_penalty 1.08; it used to be dropped.
        seen = _capture({"num_gpu": 99, "num_ctx": 16384, "temperature": 0.0,
                         "repeat_penalty": 1.08, "json_mode": True, "num_predict": 512})
        body = seen["body"]
        self.assertEqual(body["repeat_penalty"], 1.08)
        self.assertEqual(body["temperature"], 0.0)
        self.assertEqual(body["max_tokens"], 512)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["stream"], False)
        # Ollama-only keys never reach llama-server.
        for key in ("num_gpu", "num_ctx", "json_mode", "num_predict"):
            self.assertNotIn(key, body)
        self.assertEqual(seen["url"], "http://127.0.0.1:1/v1/chat/completions")
        self.assertEqual(seen["text"], "ok")

    def test_unset_sampler_fields_are_not_invented(self):
        body = _capture({"temperature": 0.0, "num_predict": 256})["body"]
        for key, _cast in llama_cpp_client._SAMPLER_FIELDS:
            self.assertNotIn(key, body)
        self.assertEqual(set(body), {"model", "messages", "stream", "temperature", "max_tokens"})

    def test_cache_prompt_is_forwarded_as_a_bool_only_when_set(self):
        # 2026-09-25o: the GVD judge sends cache_prompt False so llama-server
        # prefills every judgement cold instead of keeping the previous
        # request's shared prefix (measured in CHANGELOG 2026-09-25n).
        body = _capture({"temperature": 0.0, "num_predict": 256, "cache_prompt": False})["body"]
        self.assertIs(body["cache_prompt"], False)
        body = _capture({"temperature": 0.0, "num_predict": 256, "cache_prompt": 1})["body"]
        self.assertIs(body["cache_prompt"], True)
        self.assertNotIn("cache_prompt", _capture({"temperature": 0.0})["body"])

    def test_no_options_keeps_the_old_defaults(self):
        body = _capture(None)["body"]
        self.assertEqual(body["temperature"], 0.0)
        self.assertEqual(body["max_tokens"], 2048)
        self.assertNotIn("repeat_penalty", body)

    def test_other_sampler_fields_are_cast(self):
        body = _capture({"top_k": "40", "top_p": "0.9", "seed": 7.0, "stop": ("a", "b"),
                         "repeat_last_n": 64})["body"]
        self.assertEqual(body["top_k"], 40)
        self.assertEqual(body["top_p"], 0.9)
        self.assertEqual(body["seed"], 7)
        self.assertEqual(body["stop"], ["a", "b"])
        self.assertEqual(body["repeat_last_n"], 64)

    def test_images_become_data_urls(self):
        body = _capture(None)["body"]
        user = body["messages"][1]["content"]
        self.assertEqual(user[0], {"type": "text", "text": "u"})
        self.assertEqual(user[1]["image_url"]["url"], "data:image/jpeg;base64,QUJD")


if __name__ == "__main__":
    unittest.main()
