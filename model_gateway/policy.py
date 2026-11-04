"""Pure routing policy for the plan-only gateway. No I/O.

``wants_cloud_plan`` decides whether a turn should first ask the cloud planning
model for a text plan. It never changes *which local model answers*: the
router's own GPU/CPU decision stands, and the plan is injected as context for
that local model. No turn is ever answered by the cloud and no tool is ever
called there.

Eligible: an interactive turn (a prompt is present) classified as heavy logic
(``capability == "logic"``, i.e. ``difficulty.needs_escalation``), while the
cloud switch is on and a credential is present, and the operator has not
forced the offline tier (``prefer == "cpu"``). Callers that pass
``allow_cloud=False`` (the local planner, background helpers) are never
eligible.
"""
from __future__ import annotations

from .config import GatewayConfig

CAP_LOGIC = "logic"


def wants_cloud_plan(
    *,
    config: GatewayConfig,
    prefer: str,
    model: str | None,
    capability: str,
    has_prompt: bool,
    allow_cloud: bool = True,
) -> tuple[bool, str]:
    """Return ``(wanted, reason)``. ``model`` is accepted for symmetry with the
    router and for future per-pin exclusions; a pinned local model can still
    receive a plan because planning is additive."""
    del model
    if not allow_cloud:
        return False, "caller excluded cloud planning"
    if not config.cloud_enabled:
        return False, "cloud planning disabled (MODEL_GATEWAY_CLOUD is not 1)"
    if not config.credential_present:
        return False, "no ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) is set"
    if prefer == "cpu":
        return False, "operator forced the offline tier"
    if not has_prompt:
        return False, "no interactive prompt (helper/background caller)"
    if capability != CAP_LOGIC:
        return False, f"capability {capability or 'none'} is not heavy logic"
    return True, "heavy-logic turn: ask the planning model for a plan, execute locally"
