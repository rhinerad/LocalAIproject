# PATCH — inject PromptSurgeon / `literalism_critic` into `dspy_orchestrator.py`

**Status:** STAGED ONLY — do not apply while the live Comfy/DSPy GPU loop is running.  
**Target file:** `local_agent/dspy_orchestrator.py`  
**New module:** `local_agent/literalism_critic.py`  
**Constraint:** This markdown is the patch plan. It does **not** modify the live orchestrator.

## Intent

When `media_accuracy_gate` / VLM curriculum fails, run the literalism critic on
`(positive_prompt, negative_prompt, vlm_raw_description)`. If subject-object
literalism is detected, stash revised prompts on the fail feedback so the next
student hop (or a manual retry) can reuse them. Default critic path is
**heuristic / CPU-only** (`use_lm=False`) so applying the patch later still
avoids extra VRAM during GPU-heavy days.

## Hook site

In `generalized_video_metric` (FLUX+MiniMax / live eval path), **after** the VLM
`judge(...)` returns and **when curriculum / gate fails** — currently the block
near:

- mechanical fail → `_fail_result(...)` (~1374)
- VLM missing/fail → `_fail_result(...)` (~1451)
- `video_director_passes_curriculum(...)` false (immediately after ~1459)

Prefer the VLM-aware fail paths (1451+ and curriculum fail), because the critic
needs `vlm_raw_description`.

## 1) Import (near other local imports at top of `dspy_orchestrator.py`)

```python
from literalism_critic import critique_literalism
```

## 2) Helper (place above `generalized_video_metric`)

```python
def _vlm_raw_text(parsed: dict | None) -> str:
    if not isinstance(parsed, dict):
        return ""
    for key in ("rationale", "raw", "description", "caption", "reasons"):
        val = parsed.get(key)
        if isinstance(val, list):
            return " | ".join(str(x) for x in val)
        if val:
            return str(val)
    return str(parsed)


def _maybe_literalism_repair(
    *,
    example,
    pred,
    parsed: dict | None,
    positive_prompt: str,
    negative_prompt: str,
) -> dict:
    """CPU-only PromptSurgeon. Never calls Ollama unless use_lm=True later."""
    vlm_raw = _vlm_raw_text(parsed)
    if not vlm_raw:
        return {"literalism_detected": False}
    try:
        verdict = critique_literalism(
            original_positive_prompt=str(positive_prompt or ""),
            original_negative_prompt=str(negative_prompt or ""),
            vlm_raw_description=vlm_raw,
            use_lm=False,  # keep False under GPU lock
        )
    except Exception as exc:
        return {"literalism_detected": False, "critic_error": f"{type(exc).__name__}: {exc}"}
    return verdict
```

## 3) Inject on media_accuracy / curriculum failure

Replace the bare VLM-fail `_fail_result` (~1451) with:

```python
    if not parsed or parsed.get("status") != "pass" or not parsed.get("scores"):
        neg = str(_field(pred, "negative_prompt") or _field(example, "negative_prompt") or "")
        repair = _maybe_literalism_repair(
            example=example,
            pred=pred,
            parsed=parsed if isinstance(parsed, dict) else None,
            positive_prompt=prompt,
            negative_prompt=neg,
        )
        err = f"media_accuracy_gate/VLM failed: {parsed.get('reasons') if isinstance(parsed, dict) else parsed}"
        if repair.get("literalism_detected"):
            err = (
                "literalism_detected: "
                + str(repair.get("rationale") or "perspective gear rendered as prop")
                + " | "
                + err
            )
            # Stash revisions for the next retry / operator inspection.
            try:
                setattr(pred, "revised_positive_prompt", repair.get("revised_positive_prompt"))
                setattr(pred, "revised_negative_prompt", repair.get("revised_negative_prompt"))
            except Exception:
                pass
        result = _fail_result(
            hparams=hparams,
            example=example,
            pred=pred,
            error=err,
            video_path=str(video_path),
            vram_trace=vram_trace,
        )
        if isinstance(result, dict):
            result["literalism_critic"] = repair
            # Also mirror onto last_feedback JSON when present.
            fb = result.get("feedback")
            if isinstance(fb, dict):
                fb["literalism_critic"] = repair
        return result
```

And after curriculum scoring (~1459), when it fails:

```python
    curriculum = video_director_passes_curriculum(parsed, iteration, use_minimum=True)
    if not curriculum.get("pass"):
        neg = str(_field(pred, "negative_prompt") or _field(example, "negative_prompt") or "")
        repair = _maybe_literalism_repair(
            example=example,
            pred=pred,
            parsed=parsed,
            positive_prompt=prompt,
            negative_prompt=neg,
        )
        err = f"media_accuracy_gate curriculum fail: {curriculum.get('reasons')}"
        if repair.get("literalism_detected"):
            err = "literalism_detected: " + str(repair.get("rationale") or "") + " | " + err
            try:
                setattr(pred, "revised_positive_prompt", repair.get("revised_positive_prompt"))
                setattr(pred, "revised_negative_prompt", repair.get("revised_negative_prompt"))
            except Exception:
                pass
        result = _fail_result(
            hparams=hparams,
            example=example,
            pred=pred,
            error=err,
            video_path=str(video_path),
            vram_trace=vram_trace,
        )
        if isinstance(result, dict):
            result["literalism_critic"] = repair
            result["curriculum"] = curriculum
        return result
```

## 4) Optional later (NOT for GPU-busy days)

- Set `use_lm=True` only when Ollama CPU student is free and you want DSPy `PromptSurgeon`.
- Wire `revised_positive_prompt` / `revised_negative_prompt` into a single bounded retry
  inside the metric (max 1) — keep that behind an env flag, e.g. `GVD_LITERALISM_RETRY=1`.

## Apply checklist (manual)

1. Confirm GPU batch finished / VRAM idle.
2. Copy `literalism_critic.py` is already at `local_agent/literalism_critic.py`.
3. Apply the snippets above to `dspy_orchestrator.py` (do not auto-apply from agents).
4. Smoke with a known POV-vs-camera-in-frame fixture **without** starting a full MIPRO run.