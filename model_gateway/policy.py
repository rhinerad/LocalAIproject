"""Pure routing policy: which turns may leave the workstation. No I/O.

``choose_cloud_tier`` returns ``None`` whenever the existing local router
should keep the decision. It never inspects the GPU itself; the router passes
in the result of its own ``gpu_busy()`` probe so the VRAM rules stay in one
place (``local_agent/router.py``).

Eligibility, as approved 2026-11-02:

* explicitly pinned cloud requests (``cloud-heavy``, ``cloud-fast``, ``claude-*``)
* unpinned heavy-logic turns (``capability == "logic"``) -> heavy tier
* unpinned interactive turns while the GPU is busy       -> fast tier
  (only ``tool`` / ``code`` capabilities; image and creative turns stay local
  because they drive local media tooling)

Never cloud: ``prefer == "cpu"`` (operator forced local), any call without a
prompt (planner, title helpers, background workers), any pinned local model,
and every caller that pins ``CPU_HOST`` directly (compactor, memory extractor).
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import (
    PIN_CLOUD_FAST,
    PIN_CLOUD_HEAVY,
    TIER_CLOUD_FAST,
    TIER_CLOUD_HEAVY,
    GatewayConfig,
    is_cloud_pin,
)

CAP_TOOL = "tool"
CAP_LOGIC = "logic"
CAP_CODE = "code"
CAP_IMAGE = "image"
CAP_CREATIVE = "creative"

BUSY_TIER_CAPABILITIES = frozenset({CAP_TOOL, CAP_CODE})


@dataclass(frozen=True)
class TierChoice:
    alias: str
    model: str
    effort: str
    reason: str
    pinned: bool

    def as_detail(self, config: GatewayConfig) -> dict:
        """What ``router.Decision.detail["gateway"]`` carries."""
        return {
            "alias": self.alias,
            "model": self.model,
            "effort": self.effort,
            "pinned": self.pinned,
            "reason": self.reason,
            "endpoint": config.netloc,
            "options": {"effort": self.effort, "max_tokens": config.max_tokens},
        }


@dataclass(frozen=True)
class Refusal:
    """A cloud pin that cannot run. The router turns this into a precise
    non-runnable Decision instead of silently substituting a local model."""
    model: str
    reason: str


def _pin_choice(model: str, config: GatewayConfig) -> TierChoice:
    name = model.strip()
    lowered = name.lower()
    if lowered == PIN_CLOUD_FAST:
        tier = config.fast
        return TierChoice(tier.alias, tier.model, tier.effort,
                          f"pinned {PIN_CLOUD_FAST} -> {tier.model}", True)
    if lowered == PIN_CLOUD_HEAVY:
        tier = config.heavy
        return TierChoice(tier.alias, tier.model, tier.effort,
                          f"pinned {PIN_CLOUD_HEAVY} -> {tier.model}", True)
    # Literal claude-* id: heavy-tier settings, the operator's exact model.
    return TierChoice(TIER_CLOUD_HEAVY, name, config.heavy.effort,
                      f"pinned literal cloud model {name}", True)


def choose_cloud_tier(
    *,
    config: GatewayConfig,
    prefer: str,
    model: str | None,
    capability: str,
    gpu_busy: bool,
    busy_reason: str = "",
    has_prompt: bool,
    allow_cloud: bool = True,
) -> TierChoice | Refusal | None:
    pinned_cloud = is_cloud_pin(model)

    if not allow_cloud:
        # Caller excluded itself (planner). A cloud pin falls back to the
        # local auto path; the router treats the pin as absent.
        return None

    if pinned_cloud:
        if not config.cloud_enabled:
            return Refusal(str(model), "cloud tier is disabled (MODEL_GATEWAY_CLOUD is not 1)")
        if not config.credential_present:
            return Refusal(str(model), "no ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) is set")
        return _pin_choice(str(model), config)

    if model:
        return None  # a pinned local model always stays local
    if not config.cloud_enabled or not config.credential_present:
        return None
    if prefer == "cpu":
        return None  # operator forced the offline tier
    if not has_prompt:
        return None  # background/helper callers never leave the box

    if capability == CAP_LOGIC:
        tier = config.heavy
        why = "heavy-logic turn -> cloud heavy tier"
        if gpu_busy:
            why += f" (GPU busy: {busy_reason or 'render owns the card'})"
        return TierChoice(tier.alias, tier.model, tier.effort, why, False)

    if gpu_busy and config.busy_tier_enabled and capability in BUSY_TIER_CAPABILITIES:
        tier = config.fast
        return TierChoice(
            tier.alias, tier.model, tier.effort,
            f"GPU busy ({busy_reason or 'render owns the card'}); "
            f"{capability or 'chat'} turn continues on cloud fast tier instead of CPU 8B",
            False)

    return None
