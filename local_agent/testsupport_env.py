"""Give unit tests the shipped router defaults, whatever the machine-wide env says.

``router.py`` and ``ollama_client.py`` read ``EQUAL_SHARES_*`` / ``POWERINFER_*``
variables once, at import, into module constants. The workstation sets
``EQUAL_SHARES_PRIMARY_REASONING_MODEL=gpt-oss-20b-heretic:latest`` machine-wide,
which turns the "primary" of the Huihui 14B/8B pair into a GPU-only opt-in model
and made 12 routing tests fail there while passing everywhere else
(CHANGELOG/2026-11-05c). The tests describe the shipped defaults; a deployment
override is not a test input. Call :func:`isolate_model_env` **before**
``import router`` in a test module.

If ``router`` was already imported with an override in effect (a batch run where
an earlier module imported it first), the module is reloaded in place so every
existing reference sees the default constants. Nothing outside the tests imports
this module.
"""
from __future__ import annotations

import importlib
import os
import sys

OVERRIDE_VARS = (
    "EQUAL_SHARES_PRIMARY_REASONING_MODEL",
    "EQUAL_SHARES_FALLBACK_REASONING_MODEL",
    "EQUAL_SHARES_PRIMARY_SAFE_PROMPT_TOKENS",
    "EQUAL_SHARES_CODING_MODEL",
    "EQUAL_SHARES_CODING_FALLBACK_MODEL",
    "EQUAL_SHARES_QWYTHOS_MODEL",
    "EQUAL_SHARES_DEEPSEEK_MODEL",
    "EQUAL_SHARES_JOSIEFIED_CODER_MODEL",
    "EQUAL_SHARES_CAPABILITY_GPU_NUM_CTX",
    "EQUAL_SHARES_CPU_HOST",
    "EQUAL_SHARES_GPU_HOST",
    "EQUAL_SHARES_COMFY_TIMESHARE",
    "EQUAL_SHARES_OLLAMA_HOST",
    "EQUAL_SHARES_OLLAMA_MODEL",
    "EQUAL_SHARES_CPU_CHAT_MODEL",
    "EQUAL_SHARES_ENSURE_CODING_MODEL",
    "POWERINFER_MODEL_ALIAS",
    "POWERINFER_PROXY_BIND",
    "POWERINFER_PROXY_PORT",
    "POWERINFER_BACKEND_URL",
    "POWERINFER_SERVER_EXE",
)
# Modules whose import-time constants come from those variables, in dependency
# order (ollama_client imports router).
_ENV_BOUND_MODULES = ("router", "ollama_client")


def isolate_model_env() -> list[str]:
    """Drop deployment overrides for this process. Returns the names removed.

    Idempotent. Reloads ``router`` / ``ollama_client`` only when an override was
    actually present *and* the module had already been imported, so the common
    case (helper called before the first ``import router``) touches nothing.
    """
    removed = [name for name in OVERRIDE_VARS if os.environ.pop(name, None) is not None]
    if removed:
        for mod_name in _ENV_BOUND_MODULES:
            module = sys.modules.get(mod_name)
            if module is not None:
                importlib.reload(module)
    return removed
