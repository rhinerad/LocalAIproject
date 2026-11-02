"""Offline tests for the pure routing policy and config loader."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_gateway import config as cfgmod  # noqa: E402
from model_gateway import policy  # noqa: E402


def cfg(**env):
    base = {"MODEL_GATEWAY_CLOUD": "1", "ANTHROPIC_API_KEY": "sk-test"}
    base.update(env)
    return cfgmod.load_config(base, read_env_file=False)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        c = cfg()
        self.assertTrue(c.cloud_enabled and c.credential_present)
        self.assertEqual("claude-opus-5-5", c.heavy.model)
        self.assertEqual("claude-sonnet-5-5", c.fast.model)
        self.assertEqual(("high", "medium"), (c.heavy.effort, c.fast.effort))
        self.assertEqual("anthropic://api.anthropic.com", c.host())
        self.assertTrue(c.send_effort and c.prompt_cache)

    def test_disabled_by_default_without_flag(self):
        c = cfgmod.load_config({"ANTHROPIC_API_KEY": "sk"}, read_env_file=False)
        self.assertFalse(c.cloud_enabled)

    def test_custom_local_base_url_turns_off_effort_and_cache(self):
        c = cfg(MODEL_GATEWAY_BASE_URL="http://127.0.0.1:11435",
                MODEL_GATEWAY_HEAVY_MODEL="qwen3:8b")
        self.assertEqual("127.0.0.1:11435", c.netloc)
        self.assertFalse(c.is_official_endpoint)
        self.assertFalse(c.send_effort)
        self.assertFalse(c.prompt_cache)
        self.assertEqual("anthropic://127.0.0.1:11435", c.host())
        self.assertEqual("qwen3:8b", c.heavy.model)

    def test_anthropic_base_url_env_is_honoured(self):
        c = cfg(ANTHROPIC_BASE_URL="http://localhost:4000")
        self.assertEqual("http://localhost:4000", c.base_url)

    def test_public_dict_never_leaks_key(self):
        c = cfg()
        self.assertNotIn("sk-test", str(c.public_dict()))

    def test_env_file_does_not_override(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("MODEL_GATEWAY_CLOUD=1\nMODEL_GATEWAY_HEAVY_EFFORT='max'\nANTHROPIC_API_KEY=sk-file\n")
            env = {"ANTHROPIC_API_KEY": "sk-process"}
            added = cfgmod.apply_env_file(env, path)
            self.assertEqual(["MODEL_GATEWAY_CLOUD", "MODEL_GATEWAY_HEAVY_EFFORT"], added)
            self.assertEqual("sk-process", env["ANTHROPIC_API_KEY"])
            self.assertEqual("max", env["MODEL_GATEWAY_HEAVY_EFFORT"])

    def test_pin_detection(self):
        self.assertTrue(cfgmod.is_cloud_pin("cloud-heavy"))
        self.assertTrue(cfgmod.is_cloud_pin("claude-opus-5-5"))
        self.assertFalse(cfgmod.is_cloud_pin("huihui_ai/qwen3-abliterated:14b"))
        self.assertFalse(cfgmod.is_cloud_pin(None))
        self.assertTrue(cfgmod.is_cloud_host("anthropic://api.anthropic.com"))
        self.assertFalse(cfgmod.is_cloud_host("127.0.0.1:11434"))


class PolicyTests(unittest.TestCase):
    def choose(self, c=None, **kw):
        base = dict(config=c or cfg(), prefer="auto", model=None, capability="tool",
                    gpu_busy=False, busy_reason="", has_prompt=True, allow_cloud=True)
        base.update(kw)
        return policy.choose_cloud_tier(**base)

    def test_logic_turn_goes_heavy(self):
        choice = self.choose(capability="logic")
        self.assertEqual(policy.TIER_CLOUD_HEAVY, choice.alias)
        self.assertEqual("claude-opus-5-5", choice.model)
        self.assertFalse(choice.pinned)

    def test_tool_turn_idle_gpu_stays_local(self):
        self.assertIsNone(self.choose(capability="tool"))
        self.assertIsNone(self.choose(capability="code"))

    def test_busy_gpu_tool_and_code_go_fast(self):
        for cap in ("tool", "code"):
            choice = self.choose(capability=cap, gpu_busy=True, busy_reason="8188 listening")
            self.assertEqual(policy.TIER_CLOUD_FAST, choice.alias)
            self.assertEqual("claude-sonnet-5-5", choice.model)
            self.assertIn("8188", choice.reason)

    def test_busy_gpu_logic_still_heavy(self):
        choice = self.choose(capability="logic", gpu_busy=True)
        self.assertEqual(policy.TIER_CLOUD_HEAVY, choice.alias)

    def test_busy_gpu_image_and_creative_stay_local(self):
        self.assertIsNone(self.choose(capability="image", gpu_busy=True))
        self.assertIsNone(self.choose(capability="creative", gpu_busy=True))

    def test_busy_tier_can_be_disabled(self):
        c = cfg(MODEL_GATEWAY_BUSY_TIER="0")
        self.assertIsNone(self.choose(c, capability="tool", gpu_busy=True))

    def test_prefer_cpu_never_cloud(self):
        self.assertIsNone(self.choose(capability="logic", prefer="cpu"))
        self.assertIsNone(self.choose(capability="tool", gpu_busy=True, prefer="cpu"))

    def test_no_prompt_never_cloud(self):
        self.assertIsNone(self.choose(capability="logic", has_prompt=False))
        self.assertIsNone(self.choose(capability="", gpu_busy=True, has_prompt=False))

    def test_local_pin_stays_local(self):
        self.assertIsNone(self.choose(capability="logic", model="huihui_ai/qwen3-abliterated:14b"))

    def test_cloud_pins(self):
        self.assertEqual("claude-sonnet-5-5", self.choose(model="cloud-fast", has_prompt=False).model)
        self.assertEqual("claude-opus-5-5", self.choose(model="cloud-heavy", prefer="cpu").model)
        literal = self.choose(model="claude-haiku-5-5")
        self.assertEqual("claude-haiku-5-5", literal.model)
        self.assertTrue(literal.pinned)

    def test_cloud_pin_refused_when_disabled_or_no_key(self):
        off = cfgmod.load_config({"ANTHROPIC_API_KEY": "sk"}, read_env_file=False)
        r = self.choose(off, model="cloud-heavy")
        self.assertIsInstance(r, policy.Refusal)
        self.assertIn("MODEL_GATEWAY_CLOUD", r.reason)
        nokey = cfgmod.load_config({"MODEL_GATEWAY_CLOUD": "1"}, read_env_file=False)
        r = self.choose(nokey, model="cloud-heavy")
        self.assertIsInstance(r, policy.Refusal)
        self.assertIn("ANTHROPIC_API_KEY", r.reason)

    def test_disabled_or_missing_key_means_local_for_unpinned(self):
        off = cfgmod.load_config({"ANTHROPIC_API_KEY": "sk"}, read_env_file=False)
        self.assertIsNone(self.choose(off, capability="logic"))
        nokey = cfgmod.load_config({"MODEL_GATEWAY_CLOUD": "1"}, read_env_file=False)
        self.assertIsNone(self.choose(nokey, capability="logic", gpu_busy=True))

    def test_allow_cloud_false_ignores_everything(self):
        self.assertIsNone(self.choose(capability="logic", allow_cloud=False))
        self.assertIsNone(self.choose(model="cloud-heavy", allow_cloud=False))

    def test_as_detail_carries_options(self):
        c = cfg(MODEL_GATEWAY_MAX_TOKENS="4096")
        d = self.choose(c, capability="logic").as_detail(c)
        self.assertEqual({"effort": "high", "max_tokens": 4096}, d["options"])
        self.assertEqual("api.anthropic.com", d["endpoint"])


if __name__ == "__main__":
    unittest.main()
