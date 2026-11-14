"""Gateway configuration. Stdlib only.

The gateway is **plan-only**: the cloud model never answers a turn and never
calls tools. For a heavy prompt it returns a numbered text plan, and the local
Ollama model executes the whole turn with that plan in context. So the only
cloud "tier" is the planning model.

Everything here is read from environment variables so the production files
never embed a key or a hostname. ``load_config()`` is cheap and side-effect
free apart from an optional, non-overriding read of ``model_gateway/.env``.

    MODEL_GATEWAY_CLOUD=1               master switch (default 0: nothing leaves the box)
    ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN   standard SDK credential
    MODEL_GATEWAY_PLAN_MODEL            default claude-opus-5-5
    MODEL_GATEWAY_PLAN_EFFORT           default high
    MODEL_GATEWAY_PLAN_MAX_TOKENS       default 3000 (a structured plan, not an answer)
    MODEL_GATEWAY_BASE_URL / ANTHROPIC_BASE_URL   optional local Anthropic-compatible server
    MODEL_GATEWAY_PLAN_BACKEND          api (default) | claude_cli | auto
                                        api        = Anthropic API with the key above
                                        claude_cli = headless Claude Code (`claude -p`)
                                                     signed in with the Claude subscription
                                        auto       = claude_cli first, API as fallback
    MODEL_GATEWAY_CLAUDE_CLI            path to claude(.exe); default: ~/.local/bin, then PATH
    MODEL_GATEWAY_CLAUDE_CLI_MODEL      default opus (a Claude Code model alias or full name)
    MODEL_GATEWAY_CLAUDE_CLI_TIMEOUT_S  default 300
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent

ANTHROPIC_DEFAULT_NETLOC = "api.anthropic.com"
DEFAULT_PLAN_MODEL = "claude-opus-5-5"
DEFAULT_PLAN_EFFORT = "high"
DEFAULT_PLAN_MAX_TOKENS = 3000
VALID_EFFORT = ("low", "medium", "high", "xhigh", "max")
PLAN_BACKENDS = ("api", "claude_cli", "auto")
DEFAULT_PLAN_BACKEND = "api"
DEFAULT_CLAUDE_CLI_MODEL = "opus"
DEFAULT_CLAUDE_CLI_TIMEOUT_S = 300.0


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
class PlanTier:
    model: str
    effort: str
    max_tokens: int


@dataclass(frozen=True)
class GatewayConfig:
    cloud_enabled: bool
    credential_present: bool
    credential_source: str            # "ANTHROPIC_API_KEY" | "ANTHROPIC_AUTH_TOKEN" | ""
    base_url: str | None              # None -> SDK default (api.anthropic.com)
    netloc: str
    plan: PlanTier
    timeout_s: float
    max_retries: int
    send_effort: bool                 # off when targeting a non-Anthropic base URL
    prompt_cache: bool
    env_file_keys: tuple[str, ...] = field(default_factory=tuple)
    plan_backend: str = DEFAULT_PLAN_BACKEND   # "api" | "claude_cli" | "auto"
    claude_cli: str = ""                       # resolved executable; "" = not found / not needed
    claude_cli_model: str = DEFAULT_CLAUDE_CLI_MODEL
    claude_cli_timeout_s: float = DEFAULT_CLAUDE_CLI_TIMEOUT_S

    @property
    def is_official_endpoint(self) -> bool:
        return self.netloc == ANTHROPIC_DEFAULT_NETLOC

    @property
    def api_available(self) -> bool:
        return self.plan_backend in ("api", "auto") and self.credential_present

    @property
    def cli_available(self) -> bool:
        return self.plan_backend in ("claude_cli", "auto") and bool(self.claude_cli)

    @property
    def planning_available(self) -> bool:
        return self.cloud_enabled and (self.api_available or self.cli_available)

    def public_dict(self) -> dict:
        """Status/UI snapshot. Never includes the credential value."""
        return {
            "mode": "plan-only",
            "cloud_enabled": self.cloud_enabled,
            "credential_present": self.credential_present,
            "credential_source": self.credential_source,
            "planning_available": self.planning_available,
            "base_url": self.base_url or f"https://{ANTHROPIC_DEFAULT_NETLOC}",
            "official_endpoint": self.is_official_endpoint,
            "plan": {"model": self.plan.model, "effort": self.plan.effort,
                     "max_tokens": self.plan.max_tokens},
            "timeout_s": self.timeout_s,
            "send_effort": self.send_effort,
            "prompt_cache": self.prompt_cache,
            "env_file_keys": list(self.env_file_keys),
            "plan_backend": self.plan_backend,
            "claude_cli_found": bool(self.claude_cli),
            "claude_cli_model": self.claude_cli_model,
            "claude_cli_timeout_s": self.claude_cli_timeout_s,
        }


def _effort(value: str | None, default: str) -> str:
    value = (value or "").strip().lower()
    return value if value in VALID_EFFORT else default


def _plan_backend(value: str | None) -> str:
    value = (value or "").strip().lower().replace("-", "_")
    if value in ("cli", "claude", "claude_code"):
        value = "claude_cli"
    return value if value in PLAN_BACKENDS else DEFAULT_PLAN_BACKEND


def resolve_claude_cli(env: dict) -> str:
    """Find the Claude Code executable without running it.

    Order: ``MODEL_GATEWAY_CLAUDE_CLI``; the native installer location
    (``~/.local/bin/claude.exe`` / ``claude``); ``claude.exe`` then ``claude``
    on PATH. The native ``.exe`` is preferred over the npm ``claude.cmd`` shim
    because a ``.cmd`` goes through cmd.exe, which mangles an empty argument
    (``--tools ""``). Returns ``""`` when nothing is found.
    """
    explicit = (env.get("MODEL_GATEWAY_CLAUDE_CLI") or "").strip().strip('"')
    if explicit:
        return explicit if Path(explicit).is_file() else (shutil.which(explicit) or "")
    home = env.get("USERPROFILE") or env.get("HOME") or str(Path.home())
    for name in ("claude.exe", "claude"):
        candidate = Path(home) / ".local" / "bin" / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which("claude.exe") or shutil.which("claude") or ""


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

    plan_backend = _plan_backend(env.get("MODEL_GATEWAY_PLAN_BACKEND"))
    # Only look for the CLI when it may be used: the default api path stays
    # exactly as before (no filesystem/PATH probing).
    claude_cli = resolve_claude_cli(env) if plan_backend != "api" else ""

    # MODEL_GATEWAY_HEAVY_* are accepted as aliases from the first prototype.
    plan = PlanTier(
        (env.get("MODEL_GATEWAY_PLAN_MODEL") or env.get("MODEL_GATEWAY_HEAVY_MODEL")
         or DEFAULT_PLAN_MODEL).strip(),
        _effort(env.get("MODEL_GATEWAY_PLAN_EFFORT") or env.get("MODEL_GATEWAY_HEAVY_EFFORT"),
                DEFAULT_PLAN_EFFORT),
        _int("MODEL_GATEWAY_PLAN_MAX_TOKENS", DEFAULT_PLAN_MAX_TOKENS, 256, 8000),
    )

    return GatewayConfig(
        cloud_enabled=_truthy(env.get("MODEL_GATEWAY_CLOUD"), False),
        credential_present=bool(source),
        credential_source=source,
        base_url=base_url,
        netloc=netloc,
        plan=plan,
        timeout_s=_float("MODEL_GATEWAY_TIMEOUT_S", 180.0),
        max_retries=_int("MODEL_GATEWAY_MAX_RETRIES", 2, 0, 5),
        # Ollama's /v1/messages and other local proxies may reject
        # output_config; only send effort to the official endpoint by default.
        send_effort=_truthy(env.get("MODEL_GATEWAY_SEND_EFFORT"), official),
        prompt_cache=_truthy(env.get("MODEL_GATEWAY_PROMPT_CACHE"), official),
        env_file_keys=tuple(added),
        plan_backend=plan_backend,
        claude_cli=claude_cli,
        claude_cli_model=(env.get("MODEL_GATEWAY_CLAUDE_CLI_MODEL") or DEFAULT_CLAUDE_CLI_MODEL).strip(),
        claude_cli_timeout_s=_float("MODEL_GATEWAY_CLAUDE_CLI_TIMEOUT_S", DEFAULT_CLAUDE_CLI_TIMEOUT_S),
    )
