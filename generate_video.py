#!/usr/bin/env python3
"""Production CLI: intent -> compiled GeneralizedVideoDirector -> FLUX.1 + MiniMax I2V.

Loads the Path B deep-MIPRO artifact, runs the student director, prints
start_prompt / video_prompt / hparams, submits the fused Comfy graph to
Rockernow (127.0.0.1:8188), then POSTs /free.

Dry-run:
  python generate_video.py --intent "VHS drone racing through neon Tokyo" --category drone_high_kinematics --dry-run

Full render:
  python generate_video.py --intent "VHS drone racing through neon Tokyo" --category drone_high_kinematics
"""

from __future__ import annotations

try:
    import native_voice_continuity as _nvc
except Exception:  # pragma: no cover
    _nvc = None
try:
    import gvd_graph_builder as _ggb  # noqa: F401
except Exception:
    _ggb = None

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
LOCAL_AGENT = ROOT / "local_agent"
DEFAULT_COMPILED = (
    ROOT
    / "models"
    / "dspy_compiled"
    / "generalized_video_director_mipro_path_b_20260917T004757.json"
)
DEFAULT_COMFY = "http://127.0.0.1:8188"
STUDENT_MODEL = "qwen2.5:1.5b"
CATEGORIES = ['drone_high_kinematics', 'macro_nature', 'stylized_2d', 'backrooms']

# Re-export H3 timing helper for CLI / offline verify (P0-2).
try:
    from gvd_core import h3_generation_frames, editorial_vs_generation_frames
except Exception:
    def h3_generation_frames(required_frames: int) -> int:
        if isinstance(required_frames, bool) or not isinstance(required_frames, int) or required_frames < 1:
            raise ValueError("positive integer frame count required")
        n = max(124, required_frames)
        n += (5 - n % 17) % 17
        if n > 362:
            raise ValueError("Split into multiple render segments")
        return n

    def editorial_vs_generation_frames(editorial_frames: int) -> tuple[int, int]:
        editorial = int(editorial_frames)
        if editorial < 1:
            raise ValueError("editorial_frames must be >= 1")
        return editorial, h3_generation_frames(editorial)


# Accept chat/docs spellings too
CATEGORY_ALIASES = {
    "drone_high_kinematics": 'drone_high_kinematics',
    "drone_high_kinematics": 'drone_high_kinematics',
    "macro_nature": 'macro_nature',
    "macro_nature": 'macro_nature',
    "stylized_2d": 'stylized_2d',
    "stylized_2d": 'stylized_2d',
    "backrooms": 'backrooms',
    "backrooms": 'backrooms',
}
for _c in CATEGORIES:
    CATEGORY_ALIASES[_c] = _c

if str(LOCAL_AGENT) not in sys.path:
    sys.path.insert(0, str(LOCAL_AGENT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_apply_qa_gate(local_agent: Path):
    """Load gvd_qa/i2v_gate.py's apply_qa_gate by path (see fix note above)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_gvd_i2v_gate_direct", local_agent / "gvd_qa" / "i2v_gate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("_gvd_i2v_gate_direct", mod)
    spec.loader.exec_module(mod)
    return mod.apply_qa_gate

FEWSHOT = {
    'drone_high_kinematics': dict(
        user_intent=(
            "A cinematic drone shot flies in from the open ocean toward sheer "
            "Atlantic cliffs at golden hour, revealing nested seabirds and "
            "white spray against black basalt."
        ),
        category='drone_high_kinematics',
        vbench_focus="dynamic_degree, scene, motion_smoothness",
        duration_seconds=8.0,
        constraints="no text, no watermark, continuous aerial move",
        start_prompt=(
            "Golden-hour Atlantic cliff of wet black basalt, white spray frozen "
            "mid-air, nested seabirds as pale marks on ledges, low warm sidelight, "
            "anamorphic haze, ultra-detailed rock texture, no people, no text"
        ),
        video_prompt=(
            "smooth aerial push-in from open ocean toward the cliff, slight "
            "acceleration, large parallax on basalt columns, spray streaking past "
            "the lens, ending in a close approach to the nesting ledges"
        ),
        negative_prompt="text, watermark, HUD, tripod lock, still photo, people",
        cfg_scale=5.0,
        step_count=28.0,
    ),
    'macro_nature': dict(
        user_intent=(
            "Extreme close-up of a dew-covered moss tip at dawn, a single water "
            "droplet refracting a forest canopy as it slowly slips."
        ),
        category='macro_nature',
        vbench_focus="scene, motion_smoothness",
        duration_seconds=8.0,
        constraints="no text, no watermark, shallow DOF",
        start_prompt=(
            "macro photograph of emerald moss tip with a crystal dew drop, dawn "
            "backlight, soft bokeh forest canopy inside the droplet, velvet green "
            "filaments, 100mm macro look, no insects"
        ),
        video_prompt=(
            "ultra-slow drip: the dew drop elongates, refracted canopy warps, then "
            "slips off the tip with a soft micro-splash; camera locked, shallow DOF"
        ),
        negative_prompt="text, watermark, insects, camera shake, jump cuts",
        cfg_scale=6.5,
        step_count=32.0,
    ),
    'stylized_2d': dict(
        user_intent=(
            "Hand-painted watercolor anime street in rain, a red umbrella bobbing "
            "through puddles reflecting neon signs."
        ),
        category='stylized_2d',
        vbench_focus="scene, motion_smoothness",
        duration_seconds=8.0,
        constraints="lock 2D watercolor medium every frame, no text, no watermark",
        start_prompt=(
            "hand-painted watercolor anime alley at night, wet cobblestones, soft "
            "pigment blooms, red umbrella as focal color, neon as washed pigment "
            "streaks, paper texture visible, no photorealism"
        ),
        video_prompt=(
            "gentle tracking beside the red umbrella through puddles, pigment "
            "ripples in reflections, light rain strokes drifting down, umbrella "
            "turns a corner at the end"
        ),
        negative_prompt="photorealistic, 3d render, text, watermark, live-action",
        cfg_scale=7.0,
        step_count=24.0,
    ),
    'backrooms': dict(
        user_intent=(
            "First-person camcorder walk down an empty yellow-wallpaper hallway "
            "with damp carpet and flickering fluorescent lights."
        ),
        category='backrooms',
        vbench_focus="scene, motion_smoothness",
        duration_seconds=8.0,
        constraints="analog camcorder look, no text, no watermark, no people",
        start_prompt=(
            "liminal yellow wallpaper hallway, damp stained carpet, buzzing "
            "fluorescent panels with one dead tube, VHS soft focus, dusty air, "
            "empty, no people"
        ),
        video_prompt=(
            "first-person handheld camcorder slow walk forward, mild sway, "
            "fluorescent flicker, never turning around"
        ),
        negative_prompt="people, faces, readable text, watermark, digital sharpness",
        cfg_scale=5.5,
        step_count=28.0,
    ),
}


def configure_student_lm(*, max_tokens: int = 4096, temperature: float = 0.4):
    """Point DSPy at local Ollama qwen2.5:1.5b.

    keep_alive=0 unloads after each call so Comfy can claim VRAM.
    repeat_penalty=1.15 as requested for production.
    """
    import dspy
    from dspy_orchestrator import director_json_adapter

    stop = ["```\n", "<|im_end|>", "}\n}"]
    opts = {
        "num_predict": max_tokens,
        "repeat_penalty": 1.15,
        "stop": list(stop),
        "keep_alive": 0,
    }
    extra_body = {
        "keep_alive": 0,
        "num_predict": max_tokens,
        "repeat_penalty": 1.15,
        "stop": list(stop),
        "options": opts,
    }
    lm = dspy.LM(
        f"ollama_chat/{STUDENT_MODEL}",
        api_base="http://127.0.0.1:11434",
        cache=False,
        temperature=temperature,
        max_tokens=max_tokens,
        keep_alive=0,
        extra_body=extra_body,
    )
    try:
        dspy.configure(lm=lm, adapter=director_json_adapter())
    except TypeError:
        dspy.configure(lm=lm)
    return lm


def inject_fewshot(predict, category: str) -> None:
    import dspy

    row = FEWSHOT.get(category) or FEWSHOT['drone_high_kinematics']
    demo = dspy.Example(
        user_intent=row["user_intent"],
        category=row["category"],
        vbench_focus=row["vbench_focus"],
        duration_seconds=row["duration_seconds"],
        constraints=row["constraints"],
        start_prompt=row["start_prompt"],
        video_prompt=row["video_prompt"],
        negative_prompt=row["negative_prompt"],
        cfg_scale=row["cfg_scale"],
        step_count=row["step_count"],
    ).with_inputs(
        "user_intent",
        "category",
        "vbench_focus",
        "duration_seconds",
        "constraints",
    )
    predict.demos = [demo]


def harden_output_field_descs(predict) -> None:
    """Stop the 1.5B from parroting the original OutputField label text."""
    overrides = {
        "start_prompt": (
            "Concrete FLUX.1 T2I prompt for ONE still opening frame "
            "(lighting, materials, composition). Do not restate instructions."
        ),
        "video_prompt": (
            "Concrete MiniMax I2V motion prompt: camera move, subject motion, "
            "pace, ending energy. Do not restate instructions."
        ),
        "negative_prompt": "Short comma-separated failure modes to suppress.",
        "cfg_scale": "JSON float in [1.0, 8.0]",
        "step_count": "JSON float in [16, 40]",
    }
    for name, desc in overrides.items():
        field = predict.signature.output_fields.get(name)
        if field is None:
            continue
        try:
            field.json_schema_extra["desc"] = desc
        except Exception:
            pass


def load_director(compiled: Path, category: str):
    """Load Path B JSON, restore playbook, inject one few-shot demo."""
    from generalized_video_director import (
        DIRECTOR_SIGNATURE_INSTRUCTIONS,
        build_director_program,
    )

    if not compiled.is_file():
        raise FileNotFoundError(
            f"Compiled director not found: {compiled}\n"
            "Re-run Path B MIPRO or pass --compiled PATH."
        )

    director = build_director_program()
    director.load(str(compiled))

    playbook = str(DIRECTOR_SIGNATURE_INSTRUCTIONS).strip()
    predict = director.director.predict  # ChainOfThought.predict
    loaded = str(getattr(predict.signature, "instructions", "") or "").strip()
    predict.signature.instructions = playbook
    harden_output_field_descs(predict)
    inject_fewshot(predict, category)
    print(
        f"  playbook={len(playbook)} chars "
        f"(compiled had {len(loaded)}), demos={len(predict.demos)}"
    )
    return director


def run_director(
    director,
    *,
    intent: str,
    category: str,
    focus: str,
    duration: float,
    constraints: str,
):
    return director(
        user_intent=intent,
        category=category,
        vbench_focus=focus,
        duration_seconds=float(duration),
        constraints=constraints,
    )


def print_plan(pred, hparams: dict) -> None:
    start = str(getattr(pred, "start_prompt", "") or "").strip()
    video = str(getattr(pred, "video_prompt", "") or "").strip()
    neg = str(getattr(pred, "negative_prompt", "") or "").strip()
    # Honor explicit non-empty negatives; only default-empty when unset/blank.\n    if bool(getattr(pred, 'bypass_director', False) or getattr(pred, 'literal_prompt', False)\n            or getattr(pred, 'bypass_director', False) or getattr(pred, 'literal_prompt', False)):\n        if not neg:\n            neg = ''\n
    print("=" * 72)
    print("DIRECTOR PLAN")
    print("=" * 72)
    print("\n[start_prompt]  (FLUX.1 still)")
    print(start or "(empty)")
    print("\n[video_prompt]  (MiniMax I2V motion)")
    print(video or "(empty)")
    print("\n[negative_prompt]")
    print(neg or "(empty)")
    print("\n[hparams]")
    print(f"  cfg_scale   = {hparams.get('cfg_scale')}")
    print(f"  step_count  = {hparams.get('step_count')}")
    print("  denoise     = 1.0  (hardcoded for empty FLUX latent; not student-tuned)")
    print("=" * 72)


def caption_v4_listening(host: str = "127.0.0.1", port: int = 11436, timeout: float = 1.0) -> bool:
    """True when Caption V4 (llama.cpp) accepts TCP connections on port 11436."""
    import socket
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def load_literal_plan(raw: str | None) -> dict:
    """Load a literal prompt plan from inline JSON, an @file, or a filesystem path."""
    import json
    if not raw:
        return {}
    text = str(raw).strip()
    if text.startswith("@"):
        text = Path(text[1:]).read_text(encoding="utf-8")
    else:
        candidate = Path(text)
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit("literal plan must be a JSON object")
    return data


def pred_from_literal_plan(plan: dict):
    """Exact start/video strings. No DSPy rewrite and no style-token fill-in."""
    start = str(plan.get("start_prompt") or "").strip()
    video = str(plan.get("video_prompt") or "").strip()
    if not start or not video:
        raise SystemExit("literal plan missing start_prompt or video_prompt")
    if "negative_prompt" in plan and plan.get("negative_prompt") is not None:
        neg = str(plan.get("negative_prompt"))
    else:
        neg = ""
    cfg = float(plan.get("cfg_scale", 5.5))
    steps = float(plan.get("step_count", 28))
    denoise = float(plan.get("denoise", 1.0))
    pred = SimpleNamespace(
        start_prompt=start,
        video_prompt=video,
        negative_prompt=neg,
        bypass_director=True,
        literal_prompt=True,
        cfg_scale=cfg,
        step_count=steps,
        denoise=denoise,
    )
    hparams = {"cfg_scale": cfg, "step_count": steps, "denoise": denoise}
    return pred, hparams


def looks_like_meta_prompt(text: str) -> bool:
    t = (text or "").lower()
    needles = (
        "descriptive lighting",
        "opening frame only",
        "camera physics, subject motion",
        "do not restate",
        "concrete flux.1",
        "concrete minimax",
        "json float",
        "focus strictly on",
    )
    return any(n in t for n in needles)




def enforce_native_voice_cli(args) -> None:
    """Fail closed when native MiniMax voice is required but TTS provider selected."""
    native = bool(getattr(args, "native_minimax_voice", False))
    provider = getattr(args, "voice_provider", None)
    if not native:
        return
    if _nvc is None:
        raise RuntimeError("native_voice_continuity unavailable")
    _nvc.forbid_tts_fallback(provider, native_required=True)


def load_ref_binding_plan_from_args(args):
    """Optional RefBindingPlan for callers that mutate graphs post-director."""
    if _ggb is None:
        return None
    import json
    images = []
    audios = []
    if getattr(args, "image_ref_json", None):
        raw = args.image_ref_json
        data = json.loads(Path(raw).read_text(encoding="utf-8") if str(raw).endswith(".json") and Path(str(raw)).is_file() else raw)
        for item in data:
            images.append(_ggb.ImageRef(
                comfy_input_name=str(item["comfy_input_name"]),
                character_id=(str(item["character_id"]) if item.get("character_id") else None),
            ))
    if getattr(args, "voice_ref_json", None):
        raw = args.voice_ref_json
        data = json.loads(Path(raw).read_text(encoding="utf-8") if str(raw).endswith(".json") and Path(str(raw)).is_file() else raw)
        for item in data:
            audios.append(_ggb.AudioRef(
                comfy_input_name=str(item["comfy_input_name"]),
                character_id=str(item["character_id"]),
                exact_transcript=str(item.get("exact_transcript") or item.get("transcript") or ""),
            ))
    if not images and not audios:
        return None
    plan = _ggb.RefBindingPlan(images=images, audios=audios)
    plan.validate()
    return plan


def submit_comfy(
    pred,
    hparams: dict,
    *,
    clip_id: str = "cli",
    category: str = "",
    stills_only: bool = False,
    raw_dialogue: str = "",
    dialogue: list | None = None,
    start_frame_path: str | None = None,
    end_frame_path: str | None = None,
    editorial_frames: int | None = None,
    generation_frames: int | None = None,
    duration_seconds: float | None = None,
    voice_provider: str | None = None,
    refine_frame_path: str | None = None,
    refine_denoise: float | None = None,
    refine_sharpen_alpha: float = 0.0,
) -> Path:
    """Submit via generate_minimax_clip (MIPRO path; includes /free).

    Passes typed dialogue array and real frame paths (not prose-only constraints)
    into the orchestrator for MiniMaxH3ImageToVideo binding and voice routing.
    ``refine_frame_path`` (a Comfy input name) makes the FLUX still a low-denoise
    img2img refinement of that frame instead of a fresh T2I still.
    """
    import comfy_api
    import dspy_orchestrator as orch
    import vram_controller

    url = DEFAULT_COMFY
    if not comfy_api.ping(url):
        raise RuntimeError(
            f"ComfyUI is not listening on {url}. Start Rockernow, then re-run."
        )

    start = str(getattr(pred, "start_prompt", "") or "").strip()
    video = str(getattr(pred, "video_prompt", "") or "").strip()
    if not start or not video:
        raise ValueError("Director returned empty start_prompt or video_prompt.")
    if looks_like_meta_prompt(start) or looks_like_meta_prompt(video):
        raise ValueError(
            "Director returned instruction-echo instead of creative prompts; "
            "refusing to submit."
        )

    hp = dict(hparams)
    hp["denoise"] = 1.0
    example = SimpleNamespace(
        id=clip_id,
        clip_id=clip_id,
        category=category,
        user_intent="",
    )
    example.raw_dialogue = str(raw_dialogue or "")
    example.pack_dialogue = str(raw_dialogue or "")
    if dialogue is not None:
        example.dialogue = dialogue
        example.dialogue_lines = dialogue
    if start_frame_path:
        example.start_frame_path = str(start_frame_path)
        example.first_frame_path = str(start_frame_path)
    if end_frame_path:
        example.end_frame_path = str(end_frame_path)
        example.last_frame_path = str(end_frame_path)
    if editorial_frames is not None:
        example.editorial_frames = int(editorial_frames)
    if generation_frames is not None:
        example.generation_frames = int(generation_frames)
    if duration_seconds is not None:
        example.duration_seconds = float(duration_seconds)
    if voice_provider:
        example.voice_provider = str(voice_provider)

    print(f"\nSubmitting {'FLUX stills-only' if stills_only else 'fused FLUX+MiniMax'} graph to {url} ...")
    # P1-D: VRAM admission failure is BLOCKING — do not continue to submit.
    try:
        from production_store import prepare_vram_or_raise, VramAdmissionError
    except Exception:
        prepare_vram_or_raise = None
        VramAdmissionError = RuntimeError  # type: ignore
    if prepare_vram_or_raise is not None:
        prepare_vram_or_raise(
            lambda **kw: vram_controller.prepare_for_comfyui(**kw),
            reason="CLI generate_video",
        )
    else:
        try:
            vram_controller.prepare_for_comfyui(reason="CLI generate_video")
        except Exception as exc:
            raise RuntimeError(f"VRAM admission failed (CLI generate_video): {exc}") from exc

    # Keep explicit non-empty negatives (e.g. hardware bans); only default-empty when blank.
    if bool(
        getattr(pred, "bypass_director", False)
        or getattr(pred, "literal_prompt", False)
        or getattr(pred, "bypass_director", False)
        or getattr(pred, "literal_prompt", False)
    ):
        if not str(getattr(pred, "negative_prompt", "") or "").strip():
            try:
                pred.negative_prompt = ""
            except Exception:
                pass
    video_path = orch.generate_minimax_clip(
        example,
        pred,
        hp,
        stills_only=bool(stills_only),
        editorial_frames=editorial_frames,
        generation_frames=generation_frames,
        duration_seconds=duration_seconds if duration_seconds is not None else None,
        start_frame_path=start_frame_path,
        end_frame_path=end_frame_path,
        dialogue=dialogue,
        voice_provider=voice_provider,
        refine_frame_path=refine_frame_path,
        refine_denoise=refine_denoise,
        refine_sharpen_alpha=refine_sharpen_alpha,
    )
    print(f"  video = {video_path}")

    print("  POST /free (unload_models + free_memory) ...")
    # P1-D: cancel/reconcile then release lease; free_vram uses keyword contract only.
    try:
        from production_store import release_gpu_lease, free_vram_safe
    except Exception:
        release_gpu_lease = None
        free_vram_safe = None
    class _CliComfyLease:
        def cancel_prompt(self, prompt_id):
            # Offline-safe stub; live client may override via comfy_api
            if hasattr(comfy_api, "cancel_prompt"):
                comfy_api.cancel_prompt(url, prompt_id)
            elif hasattr(comfy_api, "interrupt"):
                comfy_api.interrupt(url)
        def reconcile(self, prompt_id=None):
            if hasattr(comfy_api, "reconcile"):
                comfy_api.reconcile(url, prompt_id=prompt_id)
        def release_lease(self, reason=""):
            try:
                vram_controller.release_after_comfyui(reason=reason or "CLI clip saved")
            except Exception:
                free_vram_safe(
                    vram_controller,
                    unload_models=True,
                    free_memory=True,
                ) if free_vram_safe else None
                try:
                    # Correct kwargs-only contract (no positional URL misuse)
                    free_vram_safe(
                        comfy_api,
                        unload_models=True,
                        free_memory=True,
                        base_url=url,
                    ) if free_vram_safe else None
                except Exception:
                    pass
    prompt_id = None  # filled by generate_minimax_clip callers when available
    if release_gpu_lease is not None:
        release_gpu_lease(
            _CliComfyLease(),
            prompt_id=prompt_id,
            reason="CLI clip saved",
        )
    else:
        try:
            vram_controller.comfy_free_memory(
                unload_models=True, free_memory=True, update_state=True
            )
        except Exception:
            try:
                # Prefer kwargs; pass base_url explicitly — never bare positional misuse
                if free_vram_safe is not None:
                    free_vram_safe(
                        comfy_api,
                        unload_models=True,
                        free_memory=True,
                        base_url=url,
                    )
                else:
                    comfy_api.free_vram(
                        unload_models=True,
                        free_memory=True,
                        # if signature requires URL, caller should use base_url=
                    )
            except TypeError:
                comfy_api.free_vram(url, unload_models=True, free_memory=True)
            except Exception as exc:
                print(f"  (/free warning: {exc})")
        try:
            vram_controller.release_after_comfyui(reason="CLI clip saved")
        except Exception:
            pass

    return Path(video_path)


def resolve_category(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key in CATEGORIES:
        return key
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    raise SystemExit(
        f"Unknown category {raw!r}. Choose one of: {', '.join(CATEGORIES)}"
    )


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Intent -> compiled GeneralizedVideoDirector -> FLUX.1 + MiniMax I2V "
            "on local ComfyUI."
        )
    )
    p.add_argument("--intent", required=True, help="Free-form creative brief.")
    p.add_argument(
        "--category",
        required=True,
        help=f"One of: {', '.join(CATEGORIES)}",
    )
    p.add_argument(
        "--focus",
        default="scene, motion_smoothness",
        help='VBench-style focus tags (default: "scene, motion_smoothness").',
    )
    p.add_argument(
        "--duration",
        type=float,
        default=8.0,
        help="Target clip length in seconds (default: 8.0).",
    )
    p.add_argument(
        "--constraints",
        default="no text, no watermark, high quality",
        help="Hard constraints for the director signature.",
    )
    p.add_argument(
        "--compiled",
        type=Path,
        default=DEFAULT_COMPILED,
        help="MIPRO-compiled director JSON (Path B artifact by default).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the director plan only; do not submit to ComfyUI.",
    )
    p.add_argument(
        "--clip-id",
        default="cli",
        help="Short id used in the Comfy filename prefix (default: cli).",
    )
    
    p.add_argument(
        "--backend-profile",
        default="h3_distilled",
        help="Deterministic backend sampling profile (not planner-invented CFG/steps).",
    )
    p.add_argument(
        "--quality-tier",
        default="standard",
        choices=["draft", "standard", "high", "hero"],
        help="Planner quality tier only; sampling comes from backend profile.",
    )
    p.add_argument(
        "--motion-complexity",
        default="moderate",
        choices=["static", "subtle", "moderate", "complex"],
        help="Planner motion complexity only; sampling comes from backend profile.",
    )
    p.add_argument(
        "--attempt-id",
        default=None,
        help="Optional production_store attempt id for lease/reconcile accounting.",
    )
    p.add_argument(
        "--start-frame-path",
        default=None,
        help="Comfy input-relative or absolute path bound to MiniMaxH3ImageToVideo.first_frame.",
    )
    p.add_argument(
        "--end-frame-path",
        default=None,
        help="Comfy input-relative or absolute path bound to MiniMaxH3ImageToVideo.last_frame.",
    )
    p.add_argument(
        "--first-frame-path",
        default=None,
        help="Alias for --start-frame-path.",
    )
    p.add_argument(
        "--last-frame-path",
        default=None,
        help="Alias for --end-frame-path.",
    )
    p.add_argument(
        "--editorial-frames",
        type=int,
        default=None,
        help="Editorial frame count (separate from H3 generation_frames).",
    )
    p.add_argument(
        "--generation-frames",
        type=int,
        default=None,
        help="Override H3 generation length (must satisfy congruent-to-5-mod-17 / 124–362).",
    )
    p.add_argument(
        "--dialogue-json",
        default=None,
        help='Typed dialogue JSON array: [{"speaker":"...","text":"..."}, ...] '
             "passed through to the voice path (not prose-only).",
    )
    p.add_argument(
        "--voice-provider",
        default=None,
        choices=["local_f5", "fish_audio", "minimax_native", "none"],
        help="Explicit voice provider (never silently call Fish as F5).",
    )
    p.add_argument(
        "--native-minimax-voice",
        action="store_true",
        default=False,
        help="Require native MiniMax voice path; refuse fish/f5 providers.",
    )
    p.add_argument(
        "--voice-ref-json",
        default=None,
        help="JSON file or inline JSON for AudioRef binding plan.",
    )
    p.add_argument(
        "--image-ref-json",
        default=None,
        help="JSON file or inline JSON for ImageRef binding plan.",
    )
    p.add_argument(
        "--qa-evaluate",
        action="store_true",
        default=False,
        help="After a successful clip, run GVD QA (WD14/CLIP/Caption V4 parse). Does not install nodes.",
    )
    p.add_argument(
        "--qa-expected-tags",
        default="",
        help="Comma-separated WD14 tags that must appear or the clip is nominated for reroll.",
    )
    p.add_argument(
        "--qa-history-json",
        default=None,
        help="Optional Comfy /history JSON path used by --qa-evaluate.",
    )
    p.add_argument(
        "--qa-receipt",
        default=None,
        help="accepted.json from generate_until_accepted. Required before I2V when --require-qa-receipt.",
    )
    p.add_argument(
        "--qa-policy-id",
        default=None,
        help="Policy ID that must match the QA receipt.",
    )
    p.add_argument(
        "--qa-requirements-json",
        default=None,
        help="Locked rubric JSON whose SHA-256 must match the QA receipt.",
    )
    p.add_argument(
        "--require-qa-receipt",
        action="store_true",
        default=True,
        help="Refuse I2V unless --qa-receipt is an accepted, hash-verified still (default on).",
    )
    p.add_argument(
        "--allow-ungated-i2v",
        action="store_true",
        default=False,
        help="Operator override: skip still QA receipt before I2V.",
    )
    p.add_argument("--qa-job-dir", default=None, help="Job directory for generate_until_accepted.")
    p.add_argument("--qa-policy-json", default=None,
                   help="Policy JSON (local_agent/gvd_qa/profiles/provisional_loop_labels_v1.json).")
    p.add_argument("--qa-generation-graph", default=None, help="Still generation API graph JSON.")
    p.add_argument("--qa-seed", type=int, default=1)
    p.add_argument("--qa-save-node", default="9")
    p.add_argument("--qa-image-node", default="8")
    p.add_argument("--qa-seed-node", default="3")
    p.add_argument("--qa-seed-input", default="seed")
    p.add_argument("--qa-width", type=int, default=1024)
    p.add_argument("--qa-height", type=int, default=1024)
    p.add_argument("--qa-resume", action="store_true", default=False)
    p.add_argument("--qa-object-info", default=None, help="Comfy /object_info JSON for fail-closed class checks.")
    p.add_argument("--qa-local", action="store_true", default=False,
                   help="Score stills with LocalQaClient (CPU CLIP/WD14/ImageReward + Caption V4).")
    p.add_argument("--qa-candidate", default=None,
                   help="Existing PNG to score instead of generating a new still.")
    p.add_argument("--qa-audit-caption", default="",
                   help="CLIP/ImageReward audit caption for local still QA.")
    p.add_argument(
        "--bypass-director",
        action="store_true",
        default=False,
        help="Skip the DSPy student and use --literal-plan-json prompts unchanged.",
    )
    p.add_argument(
        "--literal-prompt",
        action="store_true",
        default=False,
        help="Alias of --bypass-director. Prompts are not rewritten.",
    )
    p.add_argument(
        "--literal-plan-json",
        default=None,
        help="JSON object, @file, or path with start_prompt, video_prompt, negative_prompt.",
    )
    p.add_argument(
        "--skip-visual-qa",
        action="store_true",
        default=False,
        help="Do not call Caption V4 on 127.0.0.1:11436. Also set automatically when that port is closed.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    enforce_native_voice_cli(args)
    # When native MiniMax voice is required, refuse fish/f5 providers explicitly.
    if bool(getattr(args, "native_minimax_voice", False)):
        provider = str(getattr(args, "voice_provider", None) or "").lower()
        if provider in {"local_f5", "fish_audio", "f5", "fish"}:
            raise SystemExit(
                f"native MiniMax voice required; refusing TTS provider {provider!r}"
            )
        if not provider:
            args.voice_provider = "minimax_native"
    category = resolve_category(args.category)

    literal = bool(
        getattr(args, "bypass_director", False)
        or getattr(args, "literal_prompt", False)
        or getattr(args, "literal_plan_json", None)
    )
    if literal:
        plan = load_literal_plan(getattr(args, "literal_plan_json", None))
        print("LITERAL OVERRIDE: DSPy student not loaded")
        pred, hparams = pred_from_literal_plan(plan)
        print_plan(pred, hparams)
    else:
        print(f"Loading student LM  ollama/{STUDENT_MODEL} ...")
        configure_student_lm()

        print(f"Loading compiled director\n  {args.compiled}")
        director = load_director(Path(args.compiled), category)

        print(
            f"Running director  category={category}  "
            f"focus={args.focus!r}  duration={args.duration}s"
        )
        pred = run_director(
            director,
            intent=args.intent,
            category=category,
            focus=args.focus,
            duration=args.duration,
            constraints=args.constraints,
        )

        import dspy_orchestrator as orch

        if not hasattr(pred, "denoise") or getattr(pred, "denoise", None) in (None, ""):
            try:
                pred.denoise = 1.0
            except Exception:
                pass

        hparams, notes = orch.parse_director_hparams(pred)
        hparams["denoise"] = 1.0
        notes = [n for n in (notes or []) if "denoise" not in str(n).lower()]
        if notes:
            print("hparam notes:", "; ".join(notes))
        print_plan(pred, hparams)

        if looks_like_meta_prompt(str(getattr(pred, "start_prompt", ""))) or looks_like_meta_prompt(
            str(getattr(pred, "video_prompt", ""))
        ):
            print(
                "\nWARNING: prompts look like instruction-echo. "
                "Try again or use a stronger student LM."
            )
            if not args.dry_run:
                return 2

    if not getattr(args, "skip_visual_qa", False) and not caption_v4_listening():
        # Fix 2026-09-23 (readiness-audit finding 1.1 / 1.2): the VLM being
        # offline is a routine ops condition, not an operator decision, and
        # must not silently disable the QA/approval gate for an unattended
        # run. Only an explicit operator choice (--skip-visual-qa or
        # --allow-ungated-i2v) may proceed ungated; otherwise refuse.
        if getattr(args, "allow_ungated_i2v", False):
            print(
                "VISUAL QA SKIPPED: 127.0.0.1:11436 is not accepting connections "
                "(--allow-ungated-i2v set; proceeding ungated by explicit operator choice)"
            )
            args.skip_visual_qa = True
        else:
            print(
                "VISUAL QA UNAVAILABLE: 127.0.0.1:11436 is not accepting connections. "
                "Refusing to submit ungated. Start Caption V4, pass --skip-visual-qa or "
                "--allow-ungated-i2v to explicitly accept ungated I2V, or supply "
                "--qa-receipt / --qa-candidate evidence."
            )
            return 5
    elif getattr(args, "skip_visual_qa", False):
        print("VISUAL QA SKIPPED: --skip-visual-qa")

    # Resolve frame paths and typed dialogue for real binding (P0-1 / P0-3).
    start_frame_path = args.start_frame_path or args.first_frame_path
    end_frame_path = args.end_frame_path or args.last_frame_path
    dialogue = None
    raw_dialogue = ""
    if args.dialogue_json:
        import json as _json
        raw = str(args.dialogue_json).strip()
        # Allow inline JSON or @path
        if raw.startswith("@"):
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        dialogue = _json.loads(raw)
        if isinstance(dialogue, dict):
            dialogue = [dialogue]
        try:
            from dynamic_voice import dialogue_to_speech_text, normalize_dialogue_array
            raw_dialogue = dialogue_to_speech_text(normalize_dialogue_array(dialogue))
        except Exception:
            raw_dialogue = _json.dumps(dialogue)

    # Carry separate editorial vs generation frames (P0-2).
    editorial_frames = args.editorial_frames
    generation_frames = args.generation_frames
    if editorial_frames is None and generation_frames is None:
        try:
            from gvd_core import editorial_vs_generation_frames
            editorial_frames = max(1, int(round(float(args.duration) * 24)))
            editorial_frames, generation_frames = editorial_vs_generation_frames(editorial_frames)
        except Exception:
            editorial_frames = max(1, int(round(float(args.duration) * 24)))
            generation_frames = None
    print(
        f"  frames: editorial={editorial_frames} generation={generation_frames} "
        f"start_frame={start_frame_path!r} end_frame={end_frame_path!r}"
    )

    # Fix 2026-09-23 (readiness-audit follow-up): `import gvd_qa` is ambiguous
    # in this process — ROOT (containing the standalone gvd_qa.py) and
    # LOCAL_AGENT (containing the gvd_qa/ package) are both on sys.path, and
    # whichever was inserted last wins the bare name, which silently breaks
    # `from gvd_qa.i2v_gate import apply_qa_gate` (raises "gvd_qa is not a
    # package") depending on process/import order. Load i2v_gate.py directly
    # by path instead of depending on that ambient package resolution.
    apply_qa_gate = _load_apply_qa_gate(LOCAL_AGENT)
    gate_code, accepted_still = apply_qa_gate(args, root=ROOT, local_agent=LOCAL_AGENT)
    if gate_code is not None:
        return gate_code
    if accepted_still is not None:
        start_frame_path = str(accepted_still)

    if args.dry_run:
        print(f"\n--dry-run set; skipping Comfy submit. start_frame={start_frame_path!r}")
        return 0

    video_path = submit_comfy(
        pred,
        hparams,
        clip_id=args.clip_id,
        category=category,
        raw_dialogue=raw_dialogue,
        dialogue=dialogue,
        start_frame_path=start_frame_path,
        end_frame_path=end_frame_path,
        editorial_frames=editorial_frames,
        generation_frames=generation_frames,
        duration_seconds=float(args.duration),
        voice_provider=args.voice_provider,
    )
    print(f"\nDone. Clip at:\n  {video_path}")
    if getattr(args, "qa_evaluate", False) and not getattr(args, "skip_visual_qa", False):
        import json as _qa_json
        history = None
        hist_path = getattr(args, "qa_history_json", None)
        if hist_path:
            history = _qa_json.loads(Path(hist_path).read_text(encoding="utf-8"))
        expected = [
            p.strip()
            for p in str(getattr(args, "qa_expected_tags", "") or "").split(",")
            if p.strip()
        ]
        from gvd_qa.evaluate import evaluate_artifact

        report = evaluate_artifact(
            prompt=str(getattr(pred, "start_prompt", "") or args.intent),
            artifact_path=video_path,
            history=history,
            expected_tags=expected,
            installed_nodes=["comfyui-wd14-tagger"],
        )
        print("QA:", _qa_json.dumps({k: report[k] for k in ("passed", "action", "reasons", "wd14_tags", "ignored_keywords") if k in report}, indent=2))
        if not report.get("passed"):
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
