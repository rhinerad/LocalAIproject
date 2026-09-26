#!/usr/bin/env python3
"""Master batch: Backrooms 102-clip pack -> FLUX.1 + MiniMax via generate_video.

Ingests Backrooms_Sitcom_Audition_Prompt_Pack_MERGED_FINAL.md through
local_agent.managed_prompt_pack, then submits each clip on the same Comfy path
verified by the live generate_video.py smoke test (WebSocket queue -> render -> /free).

Default uses each clip's pack start_frame + video_prompt. Pass --via-director to
re-prompt through the compiled GVD student instead.

Checkpoint / resume: local_agent/runtime/gvd_backrooms_batch/progress.json

Examples:
  python batch_run_backrooms_gvd.py --limit 3 --dry-run
  python batch_run_backrooms_gvd.py --clip C001
  python batch_run_backrooms_gvd.py --clip C001 --force --stills-only
  python batch_run_backrooms_gvd.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
LOCAL_AGENT = ROOT / "local_agent"
DEFAULT_PACK = ROOT / "Backrooms_Sitcom_Audition_Prompt_Pack_MERGED_FINAL.md"
PROGRESS_DIR = LOCAL_AGENT / "runtime" / "gvd_backrooms_batch"
PROGRESS_PATH = PROGRESS_DIR / "progress.json"
# --dry-run records go here, never into progress["clips"]: a dry run used to
# overwrite real SELECTED/rendered entries (and their video_path) with
# {"status": "dry_run"}, destroying resume state and chain sources.
DRY_RUN_REPORT_PATH = PROGRESS_DIR / "dry_run_report.json"
OVERRIDES_DIR = ROOT / "clip_overrides"
DEFAULT_CATEGORY = "backrooms"

# --- Clip-to-clip video continuity (scene_reasoner-driven chaining) --------
# off    : today's behavior, fresh FLUX still per clip; reasoner never called.
# shadow : call scene_reasoner and record what it WOULD do; render unchanged.
# live   : chain the previous clip's actual last frame when policy allows.
CONTINUITY_OFF, CONTINUITY_SHADOW, CONTINUITY_LIVE = "off", "shadow", "live"
CONTINUITY_CHOICES = (CONTINUITY_OFF, CONTINUITY_SHADOW, CONTINUITY_LIVE)
# Quality-reset ceiling: at most this many CONSECUTIVE raw-chained clips; the
# next context_video clip gets a quality reset, so repeated decode->re-encode
# of chained frames cannot compound unbounded. 4 => a reset at least every 5th
# clip (~50 s of this pack). 0 => every context_video clip is reset.
CHAIN_MAX_CONSECUTIVE = 4
# What the reset is. refine (default): low-denoise FLUX img2img of the previous
# clip's actual last frame -- keeps pose/composition/blocking, cleans codec
# softness and drift -- and becomes the new clean anchor (chain depth 0).
# fresh_still: independent T2I still, i.e. a hard visual cut (pre-refine behavior).
CHAIN_RESET_REFINE, CHAIN_RESET_FRESH = "refine", "fresh_still"
CHAIN_RESET_CHOICES = (CHAIN_RESET_REFINE, CHAIN_RESET_FRESH)
# Refine-checkpoint KSampler denoise. Tuned 2026-09-23 (CHANGELOG 2026-09-23f,
# scripts/refine_denoise_compare.py, C008 last frame -> C009 prompts, ladder
# 0.10/0.15/0.20/0.35): 0.35 regenerated a different, younger face; 0.20
# already smoothed/de-aged it at crop scale; 0.10-0.15 kept identity. No value
# measurably sharpened the face. Re-check on a genuinely chain-drifted frame
# before trusting long live chains; record any change in a CHANGELOG entry.
REFINE_DENOISE = 0.15
# Optional core ImageSharpen alpha after the refine decode; 0 disables the node.
REFINE_SHARPEN_ALPHA = 0.0
# Character re-entry guard: the camera holder in a POV camera mode is never on
# screen yet never leaves, so his absence from a clip's text is not an exit.
# This pack: Mode B "camera in the actor's hand ... face/body is never shown".
POV_HOLDER_BY_CAMERA_MODE: dict[str, str] = {"B": "ACTOR"}
# Prior pack clips shown to the reasoner (<= scene_reasoner.HISTORY_DEFAULT_LIMIT).
REASONER_HISTORY_CLIPS = 6
REASONER_STORY_PREFIX = "backrooms-gvd"
SCENE_REASONER_PATH = ROOT / "work" / "scene_reasoner.py"

def hparams_from_backend_profile(
    *,
    backend_profile: str = "h3_distilled",
    quality_tier: str = "standard",
    motion_complexity: str = "moderate",
) -> dict:
    """P1-C: sampling from deterministic backend profiles, not planner CFG/steps."""
    try:
        from backend_profiles import planner_request_to_hparams
        hp = planner_request_to_hparams(
            backend_profile=backend_profile,
            quality_tier=quality_tier,
            motion_complexity=motion_complexity,
        )
        out = {
            "cfg_scale": hp.get("cfg_scale") if hp.get("uses_cfg") else None,
            "step_count": float(hp.get("step_count") or 20),
            "denoise": float(hp.get("denoise") or 1.0),
            "backend_profile": backend_profile,
            "quality_tier": quality_tier,
            "motion_complexity": motion_complexity,
        }
        return out
    except Exception:
        # Distilled H3 fallback — no invented Wan/FLUX CFG
        return {
            "cfg_scale": None,
            "step_count": 20.0,
            "denoise": 1.0,
            "backend_profile": backend_profile,
            "quality_tier": quality_tier,
            "motion_complexity": motion_complexity,
        }


DEFAULT_CFG = 5.5
DEFAULT_STEPS = 28.0

sys.path.insert(0, str(LOCAL_AGENT))
sys.path.insert(0, str(ROOT))


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_progress() -> dict:
    if PROGRESS_PATH.is_file():
        try:
            return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"pack": str(DEFAULT_PACK), "created": _now(), "clips": {}}


def save_progress(progress: dict) -> None:
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    progress["updated"] = _now()
    tmp = PROGRESS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PROGRESS_PATH)


def ingest_pack(pack_path: Path) -> list[dict]:
    import managed_prompt_pack as mpp

    if not pack_path.is_file():
        raise FileNotFoundError(f"Prompt pack not found: {pack_path}")
    raw = pack_path.read_text(encoding="utf-8", errors="ignore")
    # Support slight naming drift across revisions of managed_prompt_pack.
    is_pack = getattr(mpp, "is_prompt_pack", None) or getattr(mpp, "is_prompt_pack")
    parse = getattr(mpp, "parse_clips", None) or getattr(mpp, "parse_clips")
    validate = getattr(mpp, "validate_clips", None) or getattr(mpp, "validate_clips")
    if not is_pack(raw):
        raise ValueError(f"Not detected as a prompt pack: {pack_path}")
    clips = parse(raw)
    validate(clips)
    if len(clips) != 102:
        print(f"WARNING: expected 102 clips, got {len(clips)}")
    return clips


def clip_to_pred_and_hparams(clip: dict) -> tuple[SimpleNamespace, dict]:
    start = str(clip.get("start_frame") or "").strip()
    video = str(clip.get("video_prompt") or "").strip()
    # Empty string is intentional (FLUX/MiniMax concept-bleed): do not fall through.
    # Non-override path: negatives come from the pack clip only (never an unbound `override`).
    if "negative_prompt" in clip:
        neg = str(clip.get("negative_prompt") or "")
    else:
        neg = str(clip.get("start_frame_negative") or "")
    neg = neg.strip()
    if not start or not video:
        raise ValueError(f"{clip.get('id')}: missing start_frame or video_prompt")
    hp = hparams_from_backend_profile(backend_profile="h3_distilled")
    # Distilled H3: do not invent Wan/FLUX CFG; keep FLUX-still cfg only if uses_cfg
    cfg = hp["cfg_scale"] if hp["cfg_scale"] is not None else DEFAULT_CFG
    steps = hp["step_count"]
    pred = SimpleNamespace(
        start_prompt=start,
        video_prompt=video,
        negative_prompt=neg,
        cfg_scale=cfg,
        step_count=steps,
        denoise=hp["denoise"],
        quality_tier=hp["quality_tier"],
        motion_complexity=hp["motion_complexity"],
        backend_profile=hp["backend_profile"],
    )
    hparams = {
        "cfg_scale": cfg,
        "step_count": steps,
        "denoise": hp["denoise"],
        "backend_profile": hp["backend_profile"],
        "quality_tier": hp["quality_tier"],
        "motion_complexity": hp["motion_complexity"],
    }
    return pred, hparams


def clip_to_intent(clip: dict) -> str:
    return (str(clip.get("body") or clip.get("start_frame") or "").strip())[:900]


# Lifecycle states (P0-6): RENDERED -> QA_PENDING -> SELECTED
# Resume must NOT treat nonempty file / legacy "done" alone as selected.
PIPELINE_SELECTED = "SELECTED"
PIPELINE_QA_PENDING = "QA_PENDING"
PIPELINE_RENDERED = "RENDERED"


def already_done(entry: dict | None) -> bool:
    """Resume skip only when SELECTED (QA-verified), not merely rendered."""
    if not entry:
        return False
    path = entry.get("video_path")
    if not path:
        return False
    p = Path(path)
    try:
        file_ok = p.is_file() and p.stat().st_size > 10_000
    except OSError:
        file_ok = False
    if not file_ok:
        return False
    pipeline_state = str(entry.get("pipeline_state") or entry.get("state") or "").upper()
    status = str(entry.get("status") or "").lower()
    if pipeline_state == PIPELINE_SELECTED:
        return True
    if status in {"selected", "verified", "qa_passed"}:
        return True
    # Explicit verified flag after QA
    if entry.get("verified") is True:
        qa = entry.get("vlm_qa") or entry.get("qa") or {}
        if isinstance(qa, dict) and qa.get("pass") is True:
            return True
        # verified without QA object still counts if operator set it
        if entry.get("qa_required") is False:
            return True
    # Legacy "done" / nonempty file alone is REJECTED for resume (P0-6)
    return False




def load_clip_override(cid: str) -> dict:
    """Per-clip escape hatch JSON (clip_overrides/C00X.json).

    Supported flags:
      bypass_director / literal_prompt (bool): skip DSPy student entirely and
        feed start_prompt + video_prompt (or pack text) straight to Comfy.
    Optional fields: start_prompt, video_prompt, negative_prompt,
      cfg_scale, step_count, denoise, notes.
    """
    cid_u = str(cid or '').strip().upper()
    for name in (f'{cid_u}.json', f'{cid_u.lower()}.json'):
        p = OVERRIDES_DIR / name
        if p.is_file():
            import json as _json
            data = _json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                data['_override_path'] = str(p)
                return data
    return {}


def wants_literal(override: dict) -> bool:
    return bool(
        override.get("bypass_director")
        or override.get("literal_prompt")
        or override.get("bypass_director")
        or override.get("literal_prompt")
    )



def pred_from_override(override: dict, clip: dict) -> tuple:
    """Build pred/hparams from override JSON, falling back to pack fields."""
    start = str(
        override.get('start_prompt') or override.get('start_prompt')
        or override.get('start_frame')
        or clip.get('start_frame')
        or ''
    ).strip()
    video = str(
        override.get('video_prompt') or override.get('video_prompt')
        or clip.get('video_prompt')
        or ''
    ).strip()
    # Empty string is intentional — do NOT fall through via `or` (FLUX concept bleed).
    if 'negative_prompt' in override:
        neg = str(override.get('negative_prompt') if override.get('negative_prompt') is not None else '')
    elif 'negative_prompt' in override:
        neg = str(override.get('negative_prompt') if override.get('negative_prompt') is not None else '')
    else:
        neg = str(clip.get('start_frame_negative') or clip.get('start_frame_negative') or '')
    neg = neg.strip()
    # Literal / bypass: default empty negative (avoid concept bleed), but honor an
    # explicit non-empty override negative_prompt (e.g. hardware bans for POV).
    _lit = bool(
        override.get('bypass_director') or override.get('literal_prompt')
        or override.get('bypass_director') or override.get('literal_prompt')
    )
    if _lit and not neg:
        neg = ''
    if not start or not video:
        raise ValueError(f"literal override for {clip.get('id')} missing start/video prompt")
    cfg = float(override.get('cfg_scale', DEFAULT_CFG))
    steps = float(override.get('step_count', DEFAULT_STEPS))
    denoise = float(override.get('denoise', 1.0))
    pred = SimpleNamespace(
        start_prompt=start,
        video_prompt=video,
        negative_prompt=neg,
        bypass_director=bool(override.get('bypass_director') or override.get('bypass_director')),
        literal_prompt=bool(override.get('literal_prompt') or override.get('literal_prompt')),
        cfg_scale=cfg,
        step_count=steps,
        denoise=denoise,
    )
    hparams = {'cfg_scale': cfg, 'step_count': steps, 'denoise': denoise}
    return pred, hparams


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Batch-render the 102-clip Backrooms pack via generate_video."
    )
    p.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    p.add_argument("--clip", action="append", default=[], help="Clip id(s), e.g. C001")
    p.add_argument("--limit", type=int, default=0, help="Stop after N clips (0 = all)")
    p.add_argument("--start-from", default="", help="First clip id to run (inclusive)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--via-director", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument(
        "--stills-only",
        action="store_true",
        help="Preview FLUX start frame only (SaveImage); skip MiniMax I2V / video nodes.",
    )
    p.add_argument("--sleep", type=float, default=2.0, help="Pause after each /free")
    p.add_argument(
        "--continuity",
        choices=CONTINUITY_CHOICES,
        default=CONTINUITY_OFF,
        help="Clip-to-clip chaining via work/scene_reasoner.py. off (default): fresh FLUX "
             "still every clip. shadow: record reasoner decisions only, render unchanged. "
             "live: chain previous clip's last frame when policy allows. Run shadow and "
             "review it before live.",
    )
    p.add_argument(
        "--chain-max-consecutive",
        type=int,
        default=CHAIN_MAX_CONSECUTIVE,
        help=f"Quality-reset ceiling on consecutive chained clips (default {CHAIN_MAX_CONSECUTIVE}).",
    )
    p.add_argument(
        "--chain-reset",
        choices=CHAIN_RESET_CHOICES,
        default=CHAIN_RESET_REFINE,
        help="What happens at the ceiling. refine (default): low-denoise FLUX img2img of the "
             "previous clip's last frame (continuity kept, drift reset). fresh_still: "
             "independent FLUX still (hard visual cut).",
    )
    p.add_argument(
        "--refine-denoise",
        type=float,
        default=REFINE_DENOISE,
        help=f"Refine-checkpoint KSampler denoise, 0<d<1 (default {REFINE_DENOISE}; see CHANGELOG 2026-09-23f).",
    )
    p.add_argument(
        "--refine-sharpen",
        type=float,
        default=REFINE_SHARPEN_ALPHA,
        help="ImageSharpen alpha after the refine decode; 0 (default) adds no sharpen node.",
    )
    p.add_argument(
        "--continuity-story",
        default="",
        help="scene_reasoner story slug for its decision log "
             f"(default {REASONER_STORY_PREFIX}-<shadow|live>).",
    )
    p.add_argument(
        "--silent-fallback",
        action="store_true",
        help="Skip Fish/F5 voice clone nodes; render video with silent/native-safe mux (watcher circuit breaker).",
    )
    # Fix 2026-09-23 (readiness-audit finding 1.1): this batch driver had no
    # QA/approval gate of any kind before submit_comfy(). It now routes
    # through the same generate_video.apply_qa_gate() used by the single-clip
    # CLI, fail-closed by default (matches --require-qa-receipt default=True
    # in generate_video.py).
    p.add_argument("--qa-receipt", default=None,
                   help="Accepted still QA receipt JSON (see generate_video.py --qa-receipt).")
    p.add_argument("--qa-candidate", default=None,
                   help="Existing PNG to score instead of generating a new still.")
    p.add_argument("--qa-job-dir", default=None, help="Job directory for generate_until_accepted.")
    p.add_argument("--qa-generation-graph", default=None, help="Still generation API graph JSON.")
    p.add_argument("--qa-policy-json", default=None,
                   help="Policy JSON (local_agent/gvd_qa/profiles/provisional_loop_labels_v1.json).")
    p.add_argument("--qa-requirements-json", default=None,
                   help="Locked rubric JSON whose SHA-256 must match the QA receipt.")
    p.add_argument("--qa-policy-id", default=None)
    p.add_argument("--qa-audit-caption", default="")
    p.add_argument("--qa-local", action="store_true", default=False)
    p.add_argument("--qa-resume", action="store_true", default=False)
    p.add_argument("--qa-object-info", default=None)
    p.add_argument("--qa-seed", type=int, default=1)
    p.add_argument("--qa-save-node", default="9")
    p.add_argument("--qa-image-node", default="8")
    p.add_argument("--qa-seed-node", default="3")
    p.add_argument("--qa-seed-input", default="seed")
    p.add_argument("--qa-width", type=int, default=1024)
    p.add_argument("--qa-height", type=int, default=1024)
    p.add_argument(
        "--require-qa-receipt", action="store_true", default=True,
        help="Refuse video submission unless a still QA receipt is accepted (default on).",
    )
    p.add_argument(
        "--allow-ungated-i2v", action="store_true", default=False,
        help="Operator override: skip still QA receipt before submitting video (explicit, logged).",
    )
    p.add_argument(
        "--skip-visual-qa", action="store_true", default=False,
        help="Do not call Caption V4 on 127.0.0.1:11436. Also set automatically when that port is closed "
             "(only if --allow-ungated-i2v is also set; otherwise the run refuses to submit ungated).",
    )
    return p



C001_LITERAL_VLM_RULE = (
    "VERIFICATION REQUIREMENT: This clip depicts a normal residential room "
    "(bedroom/living room) with blue walls and domestic furniture. "
    "Verify that domestic items (bed, posters, windows, furniture) are clearly visible."
)


def run_literal_vlm_qa(
    video_path: Path,
    *,
    start_prompt: str,
    video_prompt: str,
    override: dict,
) -> dict:
    """Extract frames and run Qwen-VL with a dynamic literal-world rubric.

    Fail-closed for bypass_director / literal_prompt clips.
    """
    import json as _json
    from pathlib import Path as _Path
    import dspy_orchestrator as orch
    from media_accuracy_gate import (
        build_video_director_vlm_system_prompt,
        build_vlm_user_prompt,
    )

    frames_fn = getattr(orch, "extract_eval_frames", None) or getattr(orch, "extract_eval_frames", None)
    if frames_fn is None:
        # fallback: grab first frame via ffmpeg elsewhere
        raise RuntimeError("extract_eval_frames not available on dspy_orchestrator")
    frames = frames_fn(_Path(video_path))
    rule = str(override.get("vlm_literal_rule") or C001_LITERAL_VLM_RULE)
    sys_prompt = build_video_director_vlm_system_prompt(literal_mode=True, literal_rule=rule)
    user_prompt = build_vlm_user_prompt(
        start_prompt=start_prompt,
        video_prompt=video_prompt,
        literal_mode=True,
        expected_scene=str(override.get("expected_scene") or start_prompt),
    )
    judge = getattr(orch, "run_qwen_director_scores", None)
    try:
        parsed = judge(frames, user_prompt, system_prompt=sys_prompt)
    except TypeError:
        parsed = judge(frames, user_prompt)
    # Persist full reasoning
    dump = PROGRESS_DIR / f"vlm_qa_{override.get('id', 'clip')}.json"
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    dump.write_text(_json.dumps({
        "video_path": str(video_path),
        "system_prompt": sys_prompt,
        "user_prompt": user_prompt,
        "parsed": parsed,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  VLM QA dump -> {dump}")
    print(f"  VLM raw/rationale: {str((parsed or {}).get('raw') or (parsed or {}).get('rationale') or parsed)[:2000]}")
    # Fail closed
    scores = (parsed or {}).get("scores") or parsed or {}
    # accept several schema shapes
    tva = scores.get("text_video_alignment")
    if tva is None and isinstance(parsed, dict):
        tva = parsed.get("text_video_alignment")
    try:
        tva_f = float(tva) if tva is not None else 0.0
    except Exception:
        tva_f = 0.0
    passed = bool((parsed or {}).get("pass", tva_f >= 0.45))
    # hard reject if rationale/raw mentions backrooms while literal
    blob = str(parsed).lower()
    if any(k in blob for k in ("yellow wallpaper", "liminal", "backrooms hallway", "endless hallway")):
        # if model admits those are present, fail
        if any(k in blob for k in ("detect", "visible", "shows", "present", "see ", "failure", "fail")):
            passed = False
    if tva_f <= 0.10:
        passed = False
    return {"pass": passed, "text_video_alignment": tva_f, "parsed": parsed, "dump": str(dump)}




def _load_apply_qa_gate(local_agent: Path):
    """Load gvd_qa/i2v_gate.py's apply_qa_gate by path, not by `import gvd_qa`.

    `import gvd_qa` is ambiguous in this process: ROOT (containing the
    standalone gvd_qa.py) and LOCAL_AGENT (containing the gvd_qa/ package)
    are both on sys.path, and whichever was inserted last wins the bare
    name, which can silently break `from gvd_qa.i2v_gate import
    apply_qa_gate` depending on process/import order. Loading the file
    directly by path avoids that ambient package-resolution collision.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_gvd_i2v_gate_direct_batch", local_agent / "gvd_qa" / "i2v_gate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("_gvd_i2v_gate_direct_batch", mod)
    spec.loader.exec_module(mod)
    return mod.apply_qa_gate

def gate_before_video_submit(args, gv, cid: str, *, root, local_agent) -> None:
    """QA/approval gate before any video (I2V) submission for one clip.

    Fix 2026-09-23 (readiness-audit finding 1.1): batch_run_backrooms_gvd.py
    previously called gv.submit_comfy() directly with no QA/approval code
    path anywhere in the file. This routes every non-stills-only clip
    through the same hash-bound gvd_qa.i2v_gate.apply_qa_gate() that
    generate_video.py's CLI already uses, fail-closed by default: with no
    receipt and no explicit --allow-ungated-i2v / --skip-visual-qa, the
    clip is refused rather than submitted ungated. Raises RuntimeError to
    block the clip; never returns a "continue anyway" sentinel.
    """
    if not getattr(args, "skip_visual_qa", False) and not gv.caption_v4_listening():
        if getattr(args, "allow_ungated_i2v", False):
            print(f"  [{cid}] VISUAL QA SKIPPED: VLM offline, --allow-ungated-i2v set")
            args.skip_visual_qa = True
        else:
            raise RuntimeError(
                f"[{cid}] VISUAL QA UNAVAILABLE: 127.0.0.1:11436 is not accepting "
                "connections. Refusing to submit ungated. Start Caption V4, pass "
                "--skip-visual-qa / --allow-ungated-i2v to explicitly accept ungated "
                "submission, or supply --qa-receipt / --qa-candidate evidence."
            )
    elif getattr(args, "skip_visual_qa", False):
        print(f"  [{cid}] VISUAL QA SKIPPED: --skip-visual-qa")
    apply_qa_gate = _load_apply_qa_gate(local_agent)
    gate_code, _accepted_still = apply_qa_gate(args, root=root, local_agent=local_agent)
    if gate_code is not None:
        raise RuntimeError(f"[{cid}] QA gate blocked submission (exit code {gate_code})")

# ---------------------------------------------------------------------------
# Clip-to-clip continuity
#
# work/scene_reasoner.py owns the per-shot judgement (context_video vs
# reference_image vs none, including the "character re-enters after being
# offscreen" drift case). This driver only (a) feeds it pack-ordered context,
# (b) layers three deterministic guards on top -- camera-mode change,
# character re-entry, and the CHAIN_MAX_CONSECUTIVE quality-reset ceiling --
# and (c) executes. Every ambiguous outcome resolves to the fresh-FLUX-still
# path that ran before this existed.
#
# Past the ceiling, a still-context_video clip is a refine checkpoint rather
# than a hard cut: FLUX img2img-refines the previous clip's last frame at
# REFINE_DENOISE (dspy_orchestrator.bind_refine_checkpoint) and the chain
# counts from 0 again. Its failure modes fall back to a fresh still like a chain.
#
# The re-entry guard duplicates a judgement scene_reasoner is asked to make,
# on purpose: in the 2026-09-23 shadow passes (8B, and 14B on boundary clips)
# the model answered context_video for every shot, including every ENTITY
# re-entry, so the floor cannot depend on it.
#
# The adapter-era clip["references"] field (local_agent/backrooms_prompt_adapter
# .py) is deliberately NOT read here: that adapter returns early for the
# FULLY MERGED pack this driver renders, so the field is absent on all 102
# clips, and its "<prev>_approved_last_frame" contract is a still-review
# convention for the older pack format, still consumed by the still-QA
# modules. scene_reasoner is the only continuity input for this path.
#
# minimax_ref2vid (C001 identity/voice conditioning for C002+) is
# complementary but currently exclusive: its MiniMaxH3ReferenceToVideo node
# has no first_frame input, so a clip on that path never chains (recorded as
# ref2vid_path_has_no_first_frame). If both are ever wanted together, the
# chained frame should become an additional <Picture N> reference there.
# ---------------------------------------------------------------------------

_CAMERA_MODE_RE = re.compile(r"Camera Mode:\s*([A-Za-z0-9_-]+)")
_SCENE_REASONER = None


def clip_camera_mode(clip: dict) -> str | None:
    explicit = str(clip.get("camera_mode") or "").strip()
    if explicit:
        return explicit.upper()
    m = _CAMERA_MODE_RE.search(str(clip.get("body") or "")[:400])
    return m.group(1).upper() if m else None


def clip_speakers(clip: dict) -> list[str]:
    out: list[str] = []
    for line in clip.get("dialogue_lines") or []:
        speaker = str(line.get("speaker") or "").strip() if isinstance(line, dict) else ""
        if speaker and speaker not in out:
            out.append(speaker)
    return out


def clip_shot_summary(clip: dict, limit: int = 500) -> str:
    """The clip-specific action sentence(s), without the pack's shared boilerplate."""
    video = str(clip.get("video_prompt") or "")
    m = re.search(
        r"Beginning from Picture 1,\s*(.*?)(?:The action develops continuously|$)", video, re.S
    )
    action = m.group(1) if m else video.split("[Shot 1]", 1)[-1]
    return re.sub(r"\s+", " ", action).strip()[:limit]


def clip_opening_composition(clip: dict, limit: int = 400) -> str:
    start = str(clip.get("start_frame") or "")
    paras = [p.strip() for p in start.split("\n\n") if p.strip()]
    for i, para in enumerate(paras):
        if para.startswith("Preserve all character identity") and i > 0:
            return re.sub(r"\s+", " ", paras[i - 1])[:limit]
    return re.sub(r"\s+", " ", start).strip()[-limit:]


def pack_cast(clips: list[dict]) -> list[str]:
    """Every speaker id in the pack; these are the characters the re-entry guard tracks."""
    return sorted({s for c in clips for s in clip_speakers(c)})


def clip_characters_present(clip: dict, cast: list[str]) -> set[str]:
    """Characters that speak, or are named as a word in the opening composition or
    action text. A POV camera holder counts as present throughout that mode."""
    text = clip_opening_composition(clip) + " " + clip_shot_summary(clip, limit=5000)
    speakers = set(clip_speakers(clip))
    present = {
        name for name in cast
        if name in speakers or re.search(rf"\b{re.escape(name)}\b", text, re.I)
    }
    holder = POV_HOLDER_BY_CAMERA_MODE.get(clip_camera_mode(clip) or "")
    if holder and holder in cast:
        present.add(holder)
    return present


def character_reentries(clips: list[dict], index: int, cast: list[str] | None = None) -> list[str]:
    """Characters present in clips[index], absent from clips[index-1], and present
    in some earlier clip: the 'reappears after being offscreen' drift case."""
    if index < 2:
        return []
    cast = cast if cast is not None else pack_cast(clips)
    now = clip_characters_present(clips[index], cast)
    before = clip_characters_present(clips[index - 1], cast)
    candidates = now - before
    if not candidates:
        return []
    earlier: set[str] = set()
    for c in clips[: index - 1]:
        earlier |= clip_characters_present(c, cast)
    return sorted(candidates & earlier)


def build_reasoner_prompt_text(clip: dict) -> str:
    cid = str(clip.get("id") or "").upper()
    speakers = clip_speakers(clip)
    return "\n".join([
        f"Clip {cid}; camera mode {clip_camera_mode(clip) or 'unknown'}.",
        f"Speakers: {', '.join(speakers) if speakers else 'none'}.",
        f"Opening composition (start frame): {clip_opening_composition(clip)}",
        f"Action: {clip_shot_summary(clip)}",
    ])


def build_reasoner_history(clips: list[dict], index: int, prior=None) -> list[dict]:
    """Previous pack clips (oldest first) with shot context only.

    Prior decisions are deliberately NOT included: in the 2026-09-23 102-clip
    shadow pass the model copied its own earlier continuity_reason verbatim
    (5 distinct strings across 101 shots). ``prior`` is accepted for call
    compatibility and ignored.
    """
    rows: list[dict] = []
    for prev in clips[max(0, index - REASONER_HISTORY_CLIPS):index]:
        rows.append({
            "shot_id": str(prev.get("id") or "").upper(),
            "camera_mode": clip_camera_mode(prev),
            "speakers": clip_speakers(prev),
            "shot_summary": clip_shot_summary(prev, limit=300),
        })
    return rows


def _load_scene_reasoner():
    """Load work/scene_reasoner.py by path (work/ is not a package on sys.path)."""
    global _SCENE_REASONER
    if _SCENE_REASONER is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_scene_reasoner_batch", SCENE_REASONER_PATH)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        _SCENE_REASONER = mod
    return _SCENE_REASONER


def _summarize_reasoner(result: dict) -> dict:
    decision = (result or {}).get("decision") or {}
    eviction = (result or {}).get("eviction")
    return {
        "status": (result or {}).get("status"),
        "continuity_source": decision.get("continuity_source"),
        "continuity_reason": decision.get("continuity_reason"),
        "reference_character_ids": decision.get("reference_character_ids"),
        "confidence": decision.get("confidence"),
        "needs_operator_input": decision.get("needs_operator_input"),
        "question_for_operator": decision.get("question_for_operator"),
        "reasoning": decision.get("reasoning"),
        "parse_error": decision.get("parse_error"),
        "decision_log": (result or {}).get("decision_log"),
        "eviction_verified": eviction.get("verified") if isinstance(eviction, dict) else None,
    }


def continuity_policy(
    reasoner: dict | None,
    *,
    camera_changed: bool,
    prev_depth: int,
    max_consecutive: int,
    reentering: list[str] | tuple = (),
    reset: str = CHAIN_RESET_REFINE,
) -> tuple[str, str]:
    """Pure policy: ("chain" | "refine_checkpoint" | "fresh_still", reason_code).

    Anything but a clean, confident context_video decision inside the guards is
    a fresh still. A context_video clip past the consecutive-chain ceiling is a
    refine checkpoint (or a fresh still with reset=fresh_still): same scene, so
    continuity is kept, but the accumulated drift is reset."""
    if not reasoner or reasoner.get("status") == "error":
        return "fresh_still", "reasoner_unavailable"
    if reasoner.get("status") != "decided" or reasoner.get("needs_operator_input"):
        return "fresh_still", "reasoner_needs_operator_input"
    source = reasoner.get("continuity_source")
    if source == "reference_image":
        return "fresh_still", "reasoner_reference_image"
    if source != "context_video":
        return "fresh_still", "reasoner_none"
    if camera_changed:
        return "fresh_still", "camera_mode_change"
    if reentering:
        return "fresh_still", "character_reentry"
    if max_consecutive <= 0 or prev_depth >= max_consecutive:
        if reset == CHAIN_RESET_REFINE:
            return "refine_checkpoint", "chain_ceiling_refine"
        return "fresh_still", "chain_ceiling"
    return "chain", "reasoner_context_video"


def _wants_ref2vid(cid: str) -> bool:
    try:
        from minimax_ref2vid import wants_minimax_ref2vid
    except Exception:
        return False
    return bool(wants_minimax_ref2vid(cid))


def decide_continuity(
    args,
    clips: list[dict],
    index: int,
    *,
    prior,
    prev_entry: dict | None,
    reasoner=None,
    ref2vid=None,
    extract=None,
    upload=None,
    comfy_url: str | None = None,
) -> dict:
    """Decide (and in live mode, prepare) this clip's start-frame source.

    Returns the record persisted under progress["clips"][cid]["continuity"].
    ``prior(clip_id)`` returns an earlier clip's continuity record, if any.
    Injectable reasoner/ref2vid/extract/upload keep this testable offline.
    """
    clip = clips[index]
    cid = str(clip.get("id") or "").upper()
    setting = getattr(args, "continuity", CONTINUITY_OFF) or CONTINUITY_OFF
    rec: dict = {
        "setting": setting,
        "mode_used": "fresh_still",
        "policy": "fresh_still",
        "reason_code": "",
        "continuity_reason": "",
        "chain_depth": 0,
        "policy_chain_depth": 0,
        "camera_mode": clip_camera_mode(clip),
        "decided_at": _now(),
    }
    if setting == CONTINUITY_OFF:
        rec["reason_code"] = "continuity_off"
        return rec
    if index == 0:
        rec["reason_code"] = "first_clip"
        return rec
    if getattr(args, "stills_only", False):
        rec["reason_code"] = "stills_only"
        return rec

    prev = clips[index - 1]
    prev_id = str(prev.get("id") or "").upper()
    prev_mode = clip_camera_mode(prev)
    rec["source_clip_id"] = prev_id
    rec["camera_mode_changed"] = bool(rec["camera_mode"] and prev_mode and rec["camera_mode"] != prev_mode)
    rec["reentering_characters"] = character_reentries(clips, index)
    prior_prev = prior(prev_id) or {}
    prev_policy_depth = int(prior_prev.get("policy_chain_depth") or 0)
    prev_actual_depth = int(prior_prev.get("chain_depth") or 0)
    ceiling_depth = prev_actual_depth if setting == CONTINUITY_LIVE else prev_policy_depth
    rec["prev_chain_depth"] = ceiling_depth

    story = getattr(args, "continuity_story", "") or f"{REASONER_STORY_PREFIX}-{setting}"
    try:
        fn = reasoner or _load_scene_reasoner().reason_about_shot
        result = fn(
            story=story,
            shot_id=cid,
            prompt_text=build_reasoner_prompt_text(clip),
            is_video_shot=True,
            history=build_reasoner_history(clips, index, prior),
            # Dry runs never render, so evict once at the end instead of per shot.
            skip_eviction=bool(getattr(args, "dry_run", False)),
        )
        summary = _summarize_reasoner(result)
    except Exception as exc:
        summary = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    rec["reasoner"] = summary
    policy, reason = continuity_policy(
        summary,
        camera_changed=rec["camera_mode_changed"],
        prev_depth=ceiling_depth,
        max_consecutive=int(getattr(args, "chain_max_consecutive", CHAIN_MAX_CONSECUTIVE)),
        reentering=rec["reentering_characters"],
        reset=getattr(args, "chain_reset", CHAIN_RESET_REFINE),
    )
    rec["policy"] = policy
    rec["reason_code"] = reason
    rec["continuity_reason"] = str(summary.get("continuity_reason") or summary.get("error") or "")
    # A refine checkpoint is the new clean anchor: the chain counts from it.
    rec["policy_chain_depth"] = prev_policy_depth + 1 if policy == "chain" else 0

    if setting == CONTINUITY_SHADOW or getattr(args, "dry_run", False):
        rec["shadow_would_chain"] = policy == "chain"
        rec["shadow_would_refine"] = policy == "refine_checkpoint"
        return rec
    if policy not in ("chain", "refine_checkpoint"):
        return rec

    # --- live execution: every failure below falls back to a fresh still ---
    # Both chain and refine start from the previous clip's actual last frame.
    if (ref2vid or _wants_ref2vid)(cid):
        rec["reason_code"] = "ref2vid_path_has_no_first_frame"
        return rec
    if not already_done(prev_entry) or (prev_entry or {}).get("stills_only"):
        rec["reason_code"] = "prev_clip_not_selected"
        return rec
    refine = policy == "refine_checkpoint"
    source_video = Path(str(prev_entry["video_path"]))
    try:
        import video_chain
        frame = Path((extract or video_chain.extract_last_frame)(source_video))
        comfy_name = (upload or video_chain.upload_to_comfy_input)(
            frame,
            url=comfy_url or "http://127.0.0.1:8188",
            name=f"{'refine' if refine else 'chain'}_{cid.lower()}_{frame.name}",
        )
    except Exception as exc:
        rec["reason_code"] = "chain_frame_error"
        rec["chain_error"] = f"{type(exc).__name__}: {exc}"
        return rec
    rec.update({"source_video_path": str(source_video), "chain_frame_path": str(frame)})
    if refine:
        rec.update({
            "mode_used": "refine_checkpoint",
            "chain_depth": 0,
            "refine_frame_path": str(comfy_name),
            "refine_denoise": float(getattr(args, "refine_denoise", REFINE_DENOISE)),
            "refine_sharpen_alpha": float(getattr(args, "refine_sharpen", REFINE_SHARPEN_ALPHA)),
        })
    else:
        rec.update({
            "mode_used": "chained",
            "chain_depth": prev_actual_depth + 1,
            "start_frame_path": str(comfy_name),
        })
    return rec


def _continuity_line(rec: dict) -> str:
    src = (
        f" from {rec.get('source_clip_id')}"
        if rec.get("mode_used") in ("chained", "refine_checkpoint") else ""
    )
    why = str(rec.get("continuity_reason") or "")[:140]
    return (
        f"  continuity[{rec.get('setting')}]: policy={rec.get('policy')} "
        f"used={rec.get('mode_used')}{src} ({rec.get('reason_code')})"
        + (f" | {why}" if why else "")
    )


def write_shadow_review(records: dict[str, dict], clips: list[dict], path: Path) -> Path:
    """Human spot-check table for a shadow pass (the review gate before --continuity live)."""
    by_id = {str(c.get("id") or "").upper(): c for c in clips}
    lines = [
        "# Continuity shadow review",
        "",
        f"Generated {_now()}. Nothing below changed a render. Spot-check before `--continuity live`,",
        "especially `reasoner_reference_image` / `reasoner_needs_operator_input` rows and camera-mode boundaries.",
        "",
        "| clip | cam | speakers | re-entry | reasoner source | conf | policy | reason | reasoner's why |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cid, rec in records.items():
        r = rec.get("reasoner") or {}
        why = str(rec.get("continuity_reason") or r.get("question_for_operator") or "").replace("|", "/")
        lines.append(
            f"| {cid} | {rec.get('camera_mode') or ''} | {', '.join(clip_speakers(by_id.get(cid, {})))} "
            f"| {', '.join(rec.get('reentering_characters') or [])} "
            f"| {r.get('continuity_source') or ''} | {r.get('confidence') if r.get('confidence') is not None else ''} "
            f"| {rec.get('policy')} | {rec.get('reason_code')} | {why[:200]} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def apply_pipeline_rules(pred, clip: dict, cid: str, override: dict | None) -> None:
    """Immutable pipeline rules (universal negative, env cues, scrub SDXL/weights), in place.

    Fail-open, as it always was inline in main(). Shared with
    scripts/refine_denoise_compare.py so tuning renders see the batch's exact prompts.
    """
    try:
        import gvd_pipeline_rules as _rules
        merged = dict(clip)
        if isinstance(override, dict) and override:
            merged.update({k: v for k, v in override.items() if not str(k).startswith("_")})
        merged["id"] = cid
        # Carry current pred fields so rules can scrub/expand them
        merged["start_prompt"] = str(getattr(pred, "start_prompt", "") or "")
        merged["video_prompt"] = str(getattr(pred, "video_prompt", "") or "")
        merged["negative_prompt"] = str(getattr(pred, "negative_prompt", "") or "")
        if wants_literal(override):
            merged["bypass_director"] = True
            merged["literal_prompt"] = True
        ruled = _rules.apply_immutable_rules(merged)
        pred.start_prompt = ruled.get("start_prompt", pred.start_prompt)
        pred.video_prompt = ruled.get("video_prompt", pred.video_prompt)
        pred.negative_prompt = ruled.get("negative_prompt", pred.negative_prompt)
        print(f"  rules: v={ruled.get('rules_version')} env={ruled.get('env_band')} frames={ruled.get('duration_frames')}")
    except Exception as _rexc:
        print(f"  rules warning (fail-open): {_rexc}")


def main(argv: list[str] | None = None) -> int:
    parser = build_argparser()
    args = parser.parse_args(argv)
    if not 0.0 < args.refine_denoise < 1.0:
        parser.error(f"--refine-denoise must be between 0 and 1 exclusive, got {args.refine_denoise}")
    if args.refine_sharpen < 0:
        parser.error("--refine-sharpen must be >= 0")

    print(f"Ingesting pack\n  {args.pack}")
    clips = ingest_pack(Path(args.pack))
    print(f"  parsed {len(clips)} clips ({clips[0]['id']} .. {clips[-1]['id']})")
    try:
        import gvd_pipeline_rules as _rules
        lock = _rules.write_rules_lock(Path(args.pack))
        print(f"  pipeline rules lock -> {lock}")
    except Exception as _rules_exc:
        print(f"  pipeline rules lock warning: {_rules_exc}")

    wanted = {c.upper() for c in args.clip} if args.clip else None
    start_from = (args.start_from or "").strip().upper()
    started = not bool(start_from)

    progress = load_progress()
    progress["pack"] = str(Path(args.pack).resolve())
    save_progress(progress)

    director = None
    if args.via_director and not args.dry_run:
        import generate_video as gv

        print("Loading GVD student + compiled director ...")
        gv.configure_student_lm()
        director = gv.load_director(gv.DEFAULT_COMPILED, DEFAULT_CATEGORY)

    ran = ok = skipped = failed = 0

    continuity_setting = getattr(args, "continuity", CONTINUITY_OFF)
    if continuity_setting != CONTINUITY_OFF:
        print(
            f"Continuity: {continuity_setting} (scene_reasoner; ceiling "
            f"{args.chain_max_consecutive} consecutive chained clips, then "
            + (
                f"refine checkpoint at denoise {args.refine_denoise})"
                if args.chain_reset == CHAIN_RESET_REFINE else "fresh still)"
            )
        )
        if continuity_setting == CONTINUITY_LIVE and not args.dry_run:
            print("  LIVE: chained clips skip the FLUX still and start from the previous clip's last frame.")
            if args.chain_reset == CHAIN_RESET_REFINE:
                print("  LIVE: at the ceiling, FLUX img2img-refines that last frame instead of a fresh still.")
    # This run's continuity records; earlier runs' come from progress.json.
    run_continuity: dict[str, dict] = {}

    def prior_continuity(pid: str) -> dict | None:
        if pid in run_continuity:
            return run_continuity[pid]
        return (progress["clips"].get(pid) or {}).get("continuity")

    dry_report: dict = {"created": _now(), "pack": progress["pack"], "clips": {}}

    for index, clip in enumerate(clips):
        cid = str(clip["id"]).upper()
        if wanted is not None and cid not in wanted:
            continue
        if not started:
            if cid == start_from:
                started = True
            else:
                continue

        entry = progress["clips"].get(cid)
        if not args.force and already_done(entry):
            print(f"\n[{cid}] skip (done -> {entry.get('video_path')})")
            skipped += 1
            continue

        print(f"\n{'=' * 72}\n[{cid}] preparing")
        continuity_rec: dict | None = None
        try:
            override = load_clip_override(cid)
            if wants_literal(override):
                print(f"  LITERAL OVERRIDE from {override.get('_override_path')}")
                if override.get('notes'):
                    print(f"  notes: {override.get('notes')}")
                pred, hparams = pred_from_override(override, clip)
            elif args.via_director:
                import generate_video as gv

                intent = clip_to_intent(clip)
                print(f"  via-director intent[:160]={intent[:160]!r}")
                if director is None:
                    pred = SimpleNamespace(
                        start_prompt="(dry-run)",
                        video_prompt="(dry-run)",
                        negative_prompt="",
                    )
                    hparams = {
                        "cfg_scale": DEFAULT_CFG,
                        "step_count": DEFAULT_STEPS,
                        "denoise": 1.0,
                    }
                else:
                    pred = gv.run_director(
                        director,
                        intent=intent,
                        category=DEFAULT_CATEGORY,
                        focus="scene, motion_smoothness",
                        duration=8.0,
                        constraints="no text, no watermark, found-footage VHS",
                    )
                    import dspy_orchestrator as orch

                    hparams, _notes = orch.parse_director_hparams(pred)
                    hparams["denoise"] = 1.0
            else:
                pred, hparams = clip_to_pred_and_hparams(clip)

            apply_pipeline_rules(pred, clip, cid, override)

            print(f"  start_prompt[:140]={str(pred.start_prompt)[:140]!r}")
            print(f"  video_prompt[:140]={str(pred.video_prompt)[:140]!r}")
            print(f"  hparams={hparams}")

            comfy_url = None
            if continuity_setting == CONTINUITY_LIVE and not args.dry_run:
                import generate_video as gv
                comfy_url = gv.DEFAULT_COMFY
            continuity_rec = decide_continuity(
                args,
                clips,
                index,
                prior=prior_continuity,
                prev_entry=progress["clips"].get(str(clips[index - 1]["id"]).upper()) if index else None,
                comfy_url=comfy_url,
            )
            run_continuity[cid] = continuity_rec
            if continuity_setting != CONTINUITY_OFF:
                print(_continuity_line(continuity_rec))

            if args.dry_run:
                dry_report["clips"][cid] = {
                    "status": "dry_run",
                    "at": _now(),
                    "continuity": continuity_rec,
                }
                dry_report["updated"] = _now()
                PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
                DRY_RUN_REPORT_PATH.write_text(
                    json.dumps(dry_report, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                ran += 1
                ok += 1
                if args.limit and ran >= args.limit:
                    break
                continue

            import generate_video as gv
            import os as _os

            if getattr(args, "silent_fallback", False):
                _os.environ["GVD_F5_TTS"] = "0"
                _os.environ["GVD_SILENT_FALLBACK"] = "1"
                print("  silent-fallback: GVD_F5_TTS=0 (skip Fish/F5 voice clone)")

            progress["clips"][cid] = {"status": "running", "at": _now(), "continuity": continuity_rec}
            save_progress(progress)
            t0 = time.time()
            # Pack/override dialogue ONLY (never DSPy paraphrase) for F5 / C001 voice lock
            import dynamic_voice as _dv
            # Prefer clip_overrides dialogue fields, then pack clip (regex fallback).
            dialogue_src = dict(clip)
            if isinstance(override, dict) and override:
                dialogue_src.update(
                    {k: v for k, v in override.items() if not str(k).startswith("_")}
                )
            dialogue_lines = _dv.extract_dialogue_array(dialogue_src)
            raw_dialogue = _dv.dialogue_to_speech_text(dialogue_lines) or _dv.extract_raw_dialogue(dialogue_src)
            if dialogue_lines:
                print(
                    f"  pack dialogue[{len(dialogue_lines)}]: "
                    + "; ".join(f"{ln.speaker}: {ln.text[:80]}" for ln in dialogue_lines)[:200]
                )
            else:
                print("  pack dialogue: (empty)")

            dialogue_payload = [
                {"speaker": ln.speaker, "text": ln.text, "voice_asset_id": ln.voice_asset_id}
                for ln in dialogue_lines
            ] or None

            if not bool(args.stills_only):
                gate_before_video_submit(args, gv, cid, root=ROOT, local_agent=LOCAL_AGENT)

            # Chained: first_frame <- previous clip's last frame; FLUX still is pruned
            # from the graph. Refine checkpoint: FLUX still = low-denoise img2img of
            # that frame. Otherwise -> fresh FLUX still exactly as before.
            mode_used = (continuity_rec or {}).get("mode_used")
            chained_start = continuity_rec.get("start_frame_path") if mode_used == "chained" else None
            refine_kwargs = (
                {
                    "refine_frame_path": continuity_rec["refine_frame_path"],
                    "refine_denoise": continuity_rec["refine_denoise"],
                    "refine_sharpen_alpha": continuity_rec.get("refine_sharpen_alpha") or 0.0,
                }
                if mode_used == "refine_checkpoint" else {}
            )
            video_path = gv.submit_comfy(
                pred,
                hparams,
                clip_id=f"br_{cid.lower()}",
                category=DEFAULT_CATEGORY,
                stills_only=bool(args.stills_only),
                raw_dialogue=raw_dialogue,
                dialogue=dialogue_payload,
                start_frame_path=chained_start,
                duration_seconds=8.0,
                **refine_kwargs,
            )
            # C001: lock MiniMax native audio as the clone reference for C002+
            if (not args.stills_only) and _dv.is_c001(cid):
                try:
                    _dv.lock_c001_master_voice(
                        Path(video_path),
                        raw_dialogue=raw_dialogue,
                    )
                except Exception as _voice_exc:
                    print(f"  C001 voice-lock hook error (fail-open): {_voice_exc}")
            elapsed = time.time() - t0
            # P0-6: mark RENDERED then QA_PENDING before any SELECTED/done.
            # Never write status=done before VLM when QA is required.
            qa_required = bool(wants_literal(override) and (not args.stills_only))
            progress["clips"][cid] = {
                "status": "rendered",
                "pipeline_state": PIPELINE_RENDERED,
                "qa_required": qa_required,
                "verified": False,
                "video_path": str(video_path),
                "elapsed_sec": round(elapsed, 1),
                "at": _now(),
                "cfg_scale": hparams.get("cfg_scale"),
                "step_count": hparams.get("step_count"),
                "stills_only": bool(args.stills_only),
                "preview_path": str(video_path) if args.stills_only else None,
                "start_frame_source": (
                    f"chained_from:{continuity_rec.get('source_clip_id')}" if chained_start
                    else f"refined_from:{continuity_rec.get('source_clip_id')}" if refine_kwargs
                    else "fresh_flux_still"
                ),
                "continuity": continuity_rec,
            }
            save_progress(progress)

            # Promote to QA_PENDING before running VLM (or skip-QA selection).
            progress["clips"][cid]["pipeline_state"] = PIPELINE_QA_PENDING
            progress["clips"][cid]["status"] = "qa_pending"
            save_progress(progress)

            # Strict VLM QA for literal/bypass clips — fail closed, halt batch on C001 miss.
            # Stills-only previews are PNGs (no MP4); skip video VLM QA.
            if qa_required:
                print(f"  Running literal-world VLM QA for {cid} ...")
                qa = run_literal_vlm_qa(
                    Path(video_path),
                    start_prompt=str(getattr(pred, "start_prompt", "")),
                    video_prompt=str(getattr(pred, "video_prompt", "")),
                    override=override,
                )
                progress["clips"][cid]["vlm_qa"] = {
                    "pass": qa.get("pass"),
                    "text_video_alignment": qa.get("text_video_alignment"),
                    "dump": qa.get("dump"),
                }
                save_progress(progress)
                if not qa.get("pass"):
                    progress["clips"][cid]["status"] = "qa_failed"
                    progress["clips"][cid]["pipeline_state"] = "QA_FAILED"
                    progress["clips"][cid]["verified"] = False
                    save_progress(progress)
                    print(f"[{cid}] VLM QA FAILED — stopping batch until this clip passes.")
                    print(f"  See {qa.get('dump')}")
                    return 2
                # QA passed -> SELECTED
                progress["clips"][cid]["status"] = "selected"
                progress["clips"][cid]["pipeline_state"] = PIPELINE_SELECTED
                progress["clips"][cid]["verified"] = True
                save_progress(progress)
            else:
                # No VLM required: RENDERED -> QA_PENDING -> SELECTED (auto)
                progress["clips"][cid]["status"] = "selected"
                progress["clips"][cid]["pipeline_state"] = PIPELINE_SELECTED
                progress["clips"][cid]["verified"] = True
                # keep legacy alias for operators grepping "done"
                progress["clips"][cid]["legacy_status"] = "done"
                save_progress(progress)
            print(f"[{cid}] SELECTED in {elapsed:.0f}s -> {video_path}")
            ran += 1
            ok += 1
            if args.sleep > 0:
                time.sleep(args.sleep)
        except Exception as exc:
            failed += 1
            ran += 1
            progress["clips"][cid] = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "at": _now(),
                "continuity": continuity_rec,
            }
            save_progress(progress)
            print(f"[{cid}] ERROR: {type(exc).__name__}: {exc}")
            traceback.print_exc()
        if args.limit and ran >= args.limit:
            break

    if continuity_setting != CONTINUITY_OFF and run_continuity:
        from collections import Counter
        counts = Counter(r.get("reason_code") for r in run_continuity.values())
        used = Counter(r.get("mode_used") for r in run_continuity.values())
        print(f"\nContinuity summary: used={dict(used)} reasons={dict(counts)}")
        if continuity_setting == CONTINUITY_SHADOW:
            review = write_shadow_review(
                run_continuity, clips, PROGRESS_DIR / "continuity_shadow_review.md"
            )
            print(f"  shadow review table -> {review}")
        if args.dry_run:
            # Per-shot eviction was skipped for the dry run; free the GPU once now.
            try:
                ev = _load_scene_reasoner().evict_reasoning_model()
                print(f"  reasoner eviction: verified={ev.get('verified')} {ev.get('reason') or ''}")
            except Exception as exc:
                print(f"  reasoner eviction FAILED: {type(exc).__name__}: {exc}")
    if args.dry_run:
        print(f"  dry-run report -> {DRY_RUN_REPORT_PATH} (progress.json clips untouched)")
    print(
        f"\nBatch summary: ran={ran} ok={ok} skipped={skipped} failed={failed} "
        f"checkpoint={PROGRESS_PATH}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
