"""Offline tests for the plan-only policy and config loader."""
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
        self.assertTrue(c.cloud_enabled and c.credential_present and c.planning_available)
        self.assertEqual("claude-opus-5-5", c.plan.model)
        self.assertEqual("high", c.plan.effort)
        self.assertEqual(1500, c.plan.max_tokens)
        self.assertTrue(c.send_effort and c.prompt_cache)
        self.assertEqual("plan-only", c.public_dict()["mode"])

    def test_disabled_by_default_without_flag(self):
        c = cfgmod.load_config({"ANTHROPIC_API_KEY": "sk"}, read_env_file=False)
        self.assertFalse(c.cloud_enabled)
        self.assertFalse(c.planning_available)

    def test_plan_overrides_and_heavy_aliases(self):
        c = cfg(MODEL_GATEWAY_PLAN_MODEL="claude-sonnet-5-5", MODEL_GATEWAY_PLAN_EFFORT="medium",
                MODEL_GATEWAY_PLAN_MAX_TOKENS="800")
        self.assertEqual(("claude-sonnet-5-5", "medium", 800),
                         (c.plan.model, c.plan.effort, c.plan.max_tokens))
        alias = cfg(MODEL_GATEWAY_HEAVY_MODEL="claude-sonnet-5-5", MODEL_GATEWAY_HEAVY_EFFORT="low")
        self.assertEqual(("claude-sonnet-5-5", "low"), (alias.plan.model, alias.plan.effort))
        clamped = cfg(MODEL_GATEWAY_PLAN_MAX_TOKENS="99999")
        self.assertEqual(8000, clamped.plan.max_tokens)

    def test_custom_local_base_url_turns_off_effort_and_cache(self):
        c = cfg(MODEL_GATEWAY_BASE_URL="http://127.0.0.1:11435", MODEL_GATEWAY_PLAN_MODEL="qwen3:8b")
        self.assertEqual("127.0.0.1:11435", c.netloc)
        self.assertFalse(c.is_official_endpoint)
        self.assertFalse(c.send_effort)
        self.assertFalse(c.prompt_cache)
        self.assertEqual("qwen3:8b", c.plan.model)

    def test_anthropic_base_url_env_is_honoured(self):
        c = cfg(ANTHROPIC_BASE_URL="http://localhost:4000")
        self.assertEqual("http://localhost:4000", c.base_url)

    def test_public_dict_never_leaks_key(self):
        self.assertNotIn("sk-test", str(cfg().public_dict()))

    def test_env_file_does_not_override(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("MODEL_GATEWAY_CLOUD=1\nMODEL_GATEWAY_PLAN_EFFORT='max'\nANTHROPIC_API_KEY=sk-file\n")
            env = {"ANTHROPIC_API_KEY": "sk-process"}
            added = cfgmod.apply_env_file(env, path)
            self.assertEqual(["MODEL_GATEWAY_CLOUD", "MODEL_GATEWAY_PLAN_EFFORT"], added)
            self.assertEqual("sk-process", env["ANTHROPIC_API_KEY"])
            self.assertEqual("max", env["MODEL_GATEWAY_PLAN_EFFORT"])


class PolicyTests(unittest.TestCase):
    def wants(self, c=None, **kw):
        base = dict(config=c or cfg(), prefer="auto", model=None, capability="logic",
                    has_prompt=True, allow_cloud=True)
        base.update(kw)
        return policy.wants_cloud_plan(**base)

    def test_logic_turn_wants_a_plan(self):
        wanted, why = self.wants()
        self.assertTrue(wanted)
        self.assertIn("plan", why)

    def test_other_capabilities_do_not(self):
        for cap in ("tool", "code", "image", "creative", ""):
            with self.subTest(cap=cap):
                self.assertFalse(self.wants(capability=cap)[0])

    def test_pinned_local_model_still_gets_a_plan(self):
        self.assertTrue(self.wants(model="huihui_ai/qwen3-abliterated:14b")[0])

    def test_prefer_cpu_never(self):
        self.assertFalse(self.wants(prefer="cpu")[0])

    def test_no_prompt_never(self):
        self.assertFalse(self.wants(has_prompt=False)[0])

    def test_allow_cloud_false_never(self):
        self.assertFalse(self.wants(allow_cloud=False)[0])

    def test_disabled_or_missing_key_never(self):
        off = cfgmod.load_config({"ANTHROPIC_API_KEY": "sk"}, read_env_file=False)
        wanted, why = self.wants(off)
        self.assertFalse(wanted)
        self.assertIn("MODEL_GATEWAY_CLOUD", why)
        nokey = cfgmod.load_config({"MODEL_GATEWAY_CLOUD": "1"}, read_env_file=False)
        wanted, why = self.wants(nokey)
        self.assertFalse(wanted)
        self.assertIn("ANTHROPIC_API_KEY", why)


if __name__ == "__main__":
    unittest.main()
