"""Gateway configuration: tier map and environment resolution. Stdlib only.

Everything here is read from environment variables so the production files
never embed a key or a hostname. ``load_config()`` is cheap and side-effect
free apart from an optional, non-overriding read of ``model_gateway/.env``.

Tier aliases (operator-facing names, stable across adapters):

    tier-local-cpu     Ollama on EQUAL_SHARES_CPU_HOST   (unchanged, never cloud)
    tier-local-gpu     Ollama on EQUAL_SHARES_GPU_HOST   (unchanged)
    tier-cloud-heavy   Anthropic, heavy reasoning        (default claude-opus-5-5)
    tier-cloud-fast    Anthropic, busy-GPU continuation  (default claude-sonnet-5-5)

Picker pins the operator can select as a chat ``model``:

    cloud-heavy  -> tier-cloud-heavy
    cloud-fast   -> tier-cloud-fast
    claude-*     -> that literal Anthropic model id on the heavy tier settings
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent

TIER_LOCAL_CPU = "tier-local-cpu"
TIER_LOCAL_GPU = "tier-local-gpu"
TIER_CLOUD_HEAVY = "tier-cloud-heavy"
TIER_CLOUD_FAST = "tier-cloud-fast"

PIN_CLOUD_HEAVY = "cloud-heavy"
PIN_CLOUD_FAST = "cloud-fast"

# ``Decision.host`` for a cloud route. router/ollama_client branch on this
# prefix exactly the way they branch on the PowerInfer proxy host today.
CLOUD_HOST_PREFIX = "anthropic://"
ANTHROPIC_DEFAULT_NETLOC = "api.anthropic.com"

DEFAULT_HEAVY_MODEL = "claude-opus-5-5"
DEFAULT_FAST_MODEL = "claude-sonnet-5-5"
VALID_EFFORT = ("low", "medium", "high", "xhigh", "max")


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Comments and blank lines ignored; no expansion."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def apply_env_file(environ: dict | None = None, path: str | os.PathLike | None = None) -> list[str]:
    """Load ``model_gateway/.env`` (or MODEL_GATEWAY_ENV_FILE) without overriding.

    Returns the keys that were newly set. Existing process environment always
    wins so a launcher-exported variable cannot be shadowed by a stale file.
    """
    env = os.environ if environ is None else environ
    target = Path(path or env.get("MODEL_GATEWAY_ENV_FILE") or (PACKAGE_DIR / ".env"))
    if not target.is_file():
        return []
    added: list[str] = []
    for key, value in _read_env_file(target).items():
        if key not in env:
            env[key] = value
            added.append(key)
    return added


@dataclass(frozen=True)
class CloudTier:
    alias: str
    model: str
    effort: str


@dataclass(frozen=True)
class GatewayConfig:
    cloud_enabled: bool
    credential_present: bool
    credential_source: str            # "ANTHROPIC_API_KEY" | "ANTHROPIC_AUTH_TOKEN" | ""
    base_url: str | None              # None -> SDK default (api.anthropic.com)
    netloc: str                       # what Decision.host carries after the prefix
    heavy: CloudTier
    fast: CloudTier
    max_tokens: int
    timeout_s: float
    max_retries: int
    send_effort: bool                 # off when targeting a non-Anthropic base URL
    prompt_cache: bool
    busy_tier_enabled: bool           # unpinned turns while GPU busy -> fast tier
    server_fallback: bool             # beta server-side refusal fallback
    env_file_keys: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_official_endpoint(self) -> bool:
        return self.netloc == ANTHROPIC_DEFAULT_NETLOC

    def tier(self, alias: str) -> CloudTier:
        if alias == TIER_CLOUD_FAST:
            return self.fast
        return self.heavy

    def host(self) -> str:
        return CLOUD_HOST_PREFIX + self.netloc

    def public_dict(self) -> dict:
        """Status/UI snapshot. Never includes the credential value."""
        return {
            "cloud_enabled": self.cloud_enabled,
            "credential_present": self.credential_present,
            "credential_source": self.credential_source,
            "base_url": self.base_url or f"https://{ANTHROPIC_DEFAULT_NETLOC}",
            "official_endpoint": self.is_official_endpoint,
            "heavy": {"alias": self.heavy.alias, "model": self.heavy.model, "effort": self.heavy.effort},
            "fast": {"alias": self.fast.alias, "model": self.fast.model, "effort": self.fast.effort},
            "max_tokens": self.max_tokens,
            "timeout_s": self.timeout_s,
            "send_effort": self.send_effort,
            "prompt_cache": self.prompt_cache,
            "busy_tier_enabled": self.busy_tier_enabled,
            "server_fallback": self.server_fallback,
            "env_file_keys": list(self.env_file_keys),
        }


def _effort(value: str | None, default: str) -> str:
    value = (value or "").strip().lower()
    return value if value in VALID_EFFORT else default


def load_config(environ: dict | None = None, *, read_env_file: bool = True) -> GatewayConfig:
    env = os.environ if environ is None else environ
    added: list[str] = apply_env_file(env) if read_env_file else []

    api_key = (env.get("ANTHROPIC_API_KEY") or "").strip()
    auth_token = (env.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    if api_key:
        source = "ANTHROPIC_API_KEY"
    elif auth_token:
        source = "ANTHROPIC_AUTH_TOKEN"
    else:
        source = ""

    base_url = (env.get("MODEL_GATEWAY_BASE_URL") or env.get("ANTHROPIC_BASE_URL") or "").strip() or None
    if base_url:
        parsed = urlparse(base_url)
        netloc = parsed.netloc or base_url
    else:
        netloc = ANTHROPIC_DEFAULT_NETLOC
    official = netloc == ANTHROPIC_DEFAULT_NETLOC

    heavy = CloudTier(
        TIER_CLOUD_HEAVY,
        (env.get("MODEL_GATEWAY_HEAVY_MODEL") or DEFAULT_HEAVY_MODEL).strip(),
        _effort(env.get("MODEL_GATEWAY_HEAVY_EFFORT"), "high"),
    )
    fast = CloudTier(
        TIER_CLOUD_FAST,
        (env.get("MODEL_GATEWAY_FAST_MODEL") or DEFAULT_FAST_MODEL).strip(),
        _effort(env.get("MODEL_GATEWAY_FAST_EFFORT"), "medium"),
    )

    def _int(name: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(env.get(name) or default)))
        except (TypeError, ValueError):
            return default

    def _float(name: str, default: float) -> float:
        try:
            return max(5.0, float(env.get(name) or default))
        except (TypeError, ValueError):
            return default

    return GatewayConfig(
        cloud_enabled=_truthy(env.get("MODEL_GATEWAY_CLOUD"), False),
        credential_present=bool(source),
        credential_source=source,
        base_url=base_url,
        netloc=netloc,
        heavy=heavy,
        fast=fast,
        max_tokens=_int("MODEL_GATEWAY_MAX_TOKENS", 16000, 256, 128000),
        timeout_s=_float("MODEL_GATEWAY_TIMEOUT_S", 600.0),
        max_retries=_int("MODEL_GATEWAY_MAX_RETRIES", 2, 0, 5),
        # Ollama's /v1/messages and other local proxies may reject
        # output_config; only send effort to the official endpoint by default.
        send_effort=_truthy(env.get("MODEL_GATEWAY_SEND_EFFORT"), official),
        prompt_cache=_truthy(env.get("MODEL_GATEWAY_PROMPT_CACHE"), official),
        busy_tier_enabled=_truthy(env.get("MODEL_GATEWAY_BUSY_TIER"), True),
        server_fallback=_truthy(env.get("MODEL_GATEWAY_SERVER_FALLBACK"), False),
        env_file_keys=tuple(added),
    )


def is_cloud_host(host: str | None) -> bool:
    return bool(host) and str(host).startswith(CLOUD_HOST_PREFIX)


def is_cloud_pin(model: str | None) -> bool:
    """True for the picker aliases or any literal Anthropic model id."""
    name = str(model or "").strip().lower()
    return name in {PIN_CLOUD_HEAVY, PIN_CLOUD_FAST} or name.startswith("claude-")
