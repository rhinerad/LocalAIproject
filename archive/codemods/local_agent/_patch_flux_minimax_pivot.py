"""Apply FLUX.1 + MiniMax I2V architectural pivot across GVD orchestrator files."""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
TS = time.strftime("%Y%m%dT%H%M%S")
BAK_SUFFIX = f".bak_flux_minimax_{TS}"


def bak(path: Path) -> None:
    shutil.copy2(path, path.with_name(path.name + BAK_SUFFIX))
    print("backup", path.name)


def must_replace(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"FAIL {label}: old block not found")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# PHASE 1 — generalized_video_director.py signature
# ---------------------------------------------------------------------------
gvd_path = BASE / "generalized_video_director.py"
bak(gvd_path)
gvd = gvd_path.read_text(encoding="utf-8")

old_instr = '''DIRECTOR_SIGNATURE_INSTRUCTIONS = (
    "You are a Generalized Video Director for Wan 2.1 first-last-frame / "
    "image-to-video on a 16 GB GPU. Rewrite user_intent into one dense "
    "positive_prompt paragraph and a comma-separated negative_prompt, then "
    "choose numeric ComfyUI hyperparameters for this clip only.\\n"
    "Keep the original request as the first sentence of positive_prompt. "
    "Name the camera move, subject, setting, lighting, and one motion arc "
    "that can complete in duration_seconds. Honor category:\\n"
    "- drone_high_kinematics: aerial or high-speed camera, large parallax, "
    "continuous travel; prefer cfg_scale 4.0-5.5 so motion does not collapse; "
    "denoise 0.75-1.00; step_count 24-32.\\n"
    "- macro_nature: extreme close-up, shallow depth of field, slow organic "
    "motion; prefer cfg_scale 5.5-7.0 for micro-detail; denoise 0.55-0.85; "
    "step_count 28-36.\\n"
    "- stylized_2d: lock the named 2D medium for every frame (ukiyo-e, cel, "
    "watercolor, pixel art, graphic novel); prefer cfg_scale 6.0-7.5; "
    "denoise 0.85-1.00; step_count 20-30.\\n"
    "- backrooms: first-person analog camcorder unless the intent locks the "
    "camera; prefer cfg_scale 5.0-6.5; denoise 0.80-1.00; step_count 24-32. "
    "When the camera is unlocked, copy these exact tokens: first-person "
    "camcorder tracking, heavy VHS artifacting, handheld walking momentum, "
    "continuous unbroken shot, realistic camera shake, 1990s home video "
    "aesthetic.\\n"
    "Those CFG bands are preferences, not clamps — explore inside the legal "
    "ranges. Emphasize the VBench axes in vbench_focus. Do not mention "
    "MiniMax, Backrooms LoRA, sampler name, or scheduler. cfg_scale, denoise, "
    "and step_count MUST be JSON numbers (floats), never words like "
    "'around 30'. cfg_scale in [1.0, 8.0], denoise in [0.35, 1.0], "
    "step_count in [16, 40]."
)'''

# Flexible: find the assignment and replace whole string
m = re.search(
    r"DIRECTOR_SIGNATURE_INSTRUCTIONS\s*=\s*\([\s\S]*?\)\n\n",
    gvd,
)
if not m:
    raise SystemExit("DIRECTOR_SIGNATURE_INSTRUCTIONS not found")

new_instr = '''DIRECTOR_SIGNATURE_INSTRUCTIONS = (
    "You are a Generalized Video Director for FLUX.1 (start frame) + MiniMax "
    "Image-to-Video on an RTX 5080. Emit a start_prompt for FLUX, a "
    "video_motion_prompt for MiniMax I2V, a comma-separated negative_prompt, "
    "and numeric ComfyUI hyperparameters (hparams: cfg_scale, denoise, "
    "step_count).\\n"
    "start_prompt: one dense still-image paragraph describing the opening "
    "frame only (subject, setting, lighting, style). No camera motion verbs.\\n"
    "video_motion_prompt: one dense paragraph describing ONLY the camera and "
    "subject motion MiniMax should apply for an 8-second / 192-frame clip. "
    "Name the move, pace, and ending energy. Do not invent a separate end "
    "still — there is no end_prompt in this architecture.\\n"
    "Honor category:\\n"
    "- drone_high_kinematics: aerial / high-speed travel, large parallax; "
    "prefer cfg_scale 4.0-5.5; denoise 0.75-1.00; step_count 24-32.\\n"
    "- macro_nature: extreme close-up, shallow DOF, slow organic motion; "
    "prefer cfg_scale 5.5-7.0; denoise 0.55-0.85; step_count 28-36.\\n"
    "- stylized_2d: lock the named 2D medium every frame; prefer cfg_scale "
    "6.0-7.5; denoise 0.85-1.00; step_count 20-30.\\n"
    "- backrooms: first-person analog camcorder unless locked; prefer "
    "cfg_scale 5.0-6.5; denoise 0.80-1.00; step_count 24-32. Put camera nouns "
    "(handheld, camcorder, first-person) AND motion verbs (walk, tracking "
    "forward, push in) in video_motion_prompt; put VHS / liminal look in "
    "start_prompt.\\n"
    "cfg_scale, denoise, and step_count MUST be JSON numbers (floats). "
    "cfg_scale in [1.0, 8.0], denoise in [0.35, 1.0], step_count in [16, 40]. "
    "Never emit an end_prompt field."
)

'''
gvd = gvd[: m.start()] + new_instr + gvd[m.end() :]

old_sig = '''    class GeneralizedVideoDirectorSignature(dspy.Signature):
        """Direct a Wan clip: dense prompts plus CFG, denoise, and step count."""

        user_intent: str = dspy.InputField(
            desc="The user's scene, subject, and motion request"
        )
        category: str = dspy.InputField(
            desc="One of drone_high_kinematics, macro_nature, stylized_2d, backrooms"
        )
        vbench_focus: str = dspy.InputField(
            desc="Comma-separated VBench axes this clip must satisfy"
        )
        duration_seconds: float = dspy.InputField(
            desc="Clip length in seconds (typically 4, 6, or 8)"
        )
        constraints: str = dspy.InputField(
            desc="Hard rejection clauses the prompt must honor"
        )
        positive_prompt: str = dspy.OutputField(
            desc="One dense Wan paragraph; first sentence restates the request"
        )
        negative_prompt: str = dspy.OutputField(
            desc="Comma-separated failure modes to suppress"
        )
        cfg_scale: float = dspy.OutputField(
            desc="Classifier-free guidance, JSON float in [1.0, 8.0]"
        )
        denoise: float = dspy.OutputField(
            desc="Wan denoise / FLF strength, JSON float in [0.35, 1.0]"
        )
        step_count: float = dspy.OutputField(
            desc="Sampler steps as a float in [16, 40]; Phase 2 rounds to int"
        )'''

new_sig = '''    class GeneralizedVideoDirectorSignature(dspy.Signature):
        """Direct FLUX.1 start frame + MiniMax I2V motion (no end_prompt)."""

        user_intent: str = dspy.InputField(
            desc="The user's scene, subject, and motion request"
        )
        category: str = dspy.InputField(
            desc="One of drone_high_kinematics, macro_nature, stylized_2d, backrooms"
        )
        vbench_focus: str = dspy.InputField(
            desc="Comma-separated VBench axes this clip must satisfy"
        )
        duration_seconds: float = dspy.InputField(
            desc="Clip length in seconds (typically 8 for MiniMax 192 frames)"
        )
        constraints: str = dspy.InputField(
            desc="Hard rejection clauses the prompt must honor"
        )
        start_prompt: str = dspy.OutputField(
            desc="FLUX.1 still prompt for the opening frame only (no motion verbs)"
        )
        video_motion_prompt: str = dspy.OutputField(
            desc="MiniMax I2V motion prompt: camera/subject move for the full clip"
        )
        negative_prompt: str = dspy.OutputField(
            desc="Comma-separated failure modes to suppress"
        )
        cfg_scale: float = dspy.OutputField(
            desc="Classifier-free guidance hparam, JSON float in [1.0, 8.0]"
        )
        denoise: float = dspy.OutputField(
            desc="Sampler denoise hparam, JSON float in [0.35, 1.0]"
        )
        step_count: float = dspy.OutputField(
            desc="Sampler steps hparam as a float in [16, 40]; rounded to int later"
        )'''

gvd = must_replace(gvd, old_sig, new_sig, "signature class")

# Drop end_prompt from dataset Example wrap; keep start_prompt as optional override
old_ex = '''                start_prompt=str(row.get("start_prompt") or ""),
                end_prompt=str(row.get("end_prompt") or ""),'''
new_ex = '''                start_prompt=str(row.get("start_prompt") or ""),
                # end_prompt removed: FLUX+MiniMax I2V has no FLF end still'''
if old_ex in gvd:
    gvd = gvd.replace(old_ex, new_ex, 1)
else:
    print("WARN: load_beta end_prompt lines not exact; scanning")
    gvd2, n = re.subn(
        r"\n\s*end_prompt=str\(row\.get\(\"end_prompt\"\) or \"\"\),",
        "\n",
        gvd,
        count=1,
    )
    if n != 1:
        raise SystemExit("could not strip end_prompt from load_beta_trainset")
    gvd = gvd2

gvd_path.write_text(gvd, encoding="utf-8")
compile(gvd, str(gvd_path), "exec")
print("PHASE1 OK generalized_video_director.py")

# ---------------------------------------------------------------------------
# PHASE 2+3+4 — dspy_orchestrator.py
# ---------------------------------------------------------------------------
orch_path = BASE / "dspy_orchestrator.py"
bak(orch_path)
orch = orch_path.read_text(encoding="utf-8")

# Expand camera/motion keywords near existing constants
old_kw = '''_CAMERA_KEYWORDS = ("handheld", "camcorder", "first-person", "first person")
_MOTION_KEYWORDS = ("walk", "walking", "momentum")'''
new_kw = '''_CAMERA_KEYWORDS = (
    "handheld",
    "camcorder",
    "first-person",
    "first person",
    "fpv",
    "pov",
    "point-of-view",
)
_MOTION_KEYWORDS = (
    "walk",
    "walking",
    "momentum",
    "push in",
    "push-in",
    "tracking forward",
    "track forward",
    "dolly",
    "glide",
    "advance",
    "move forward",
)
_DRONE_OR_CINEMATIC_CATEGORIES = frozenset(
    {
        "drone",
        "drone_high_kinematics",
        "cinematic",
        "cinematic_drone",
    }
)
# MiniMax I2V: 8 seconds at 24 fps.
MINIMAX_NUM_FRAMES = 192
MINIMAX_GRAPH_TEMPLATE = Path(__file__).resolve().parent / "graphs" / "flux_minimax_i2v_api.json"'''
orch = must_replace(orch, old_kw, new_kw, "keyword constants")

# Ensure Path imported — usually already
if "from pathlib import Path" not in orch and "import Path" not in orch:
    orch = orch.replace("import json\n", "import json\nfrom pathlib import Path\n", 1)

# Replace build_wan_graph with build_minimax_graph + keep thin deprecated wrapper
old_build = None
m = re.search(r"\ndef build_wan_graph\([\s\S]*?\n    return graph\n", orch)
if not m:
    raise SystemExit("build_wan_graph block not found")

new_build = '''

def _force_frame_length(graph: dict, num_frames: int = MINIMAX_NUM_FRAMES) -> dict:
    """Hard-set MiniMax / I2V length fields to 192 frames (8s @ 24fps)."""
    length_keys = {
        "num_frames",
        "frame_count",
        "frames",
        "length",
        "video_length",
        "num_frames_total",
        "total_frames",
        "duration_frames",
    }
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key in list(inputs.keys()):
            lk = str(key).lower()
            if lk in length_keys or "frame" in lk and "rate" not in lk:
                inputs[key] = int(num_frames)
    return graph


def _inject_prompt_fields(
    graph: dict,
    *,
    start_prompt: str,
    video_prompt: str,
    negative: str,
    hparams: dict[str, float],
) -> dict:
    """Fill placeholder / known text+hparam slots in a FLUX+MiniMax API graph."""
    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        if str(node_id).startswith("_"):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        ctype = str(node.get("class_type") or "")
        # Heuristic text injection until the real template maps exact node IDs.
        if "text" in inputs and isinstance(inputs["text"], str):
            marker = inputs["text"].strip().upper()
            if marker in {"{{START_PROMPT}}", "{{FLUX_PROMPT}}", "START_PROMPT"}:
                inputs["text"] = start_prompt
            elif marker in {"{{VIDEO_PROMPT}}", "{{MOTION_PROMPT}}", "VIDEO_PROMPT"}:
                inputs["text"] = video_prompt
            elif marker in {"{{NEGATIVE}}", "NEGATIVE_PROMPT"}:
                inputs["text"] = negative
        for cfg_key in ("cfg", "cfg_scale", "guidance"):
            if cfg_key in inputs:
                inputs[cfg_key] = float(hparams.get("cfg_scale", inputs[cfg_key]))
        for step_key in ("steps", "step_count", "num_inference_steps"):
            if step_key in inputs:
                inputs[step_key] = int(round(hparams.get("step_count", inputs[step_key])))
        if "denoise" in inputs:
            inputs["denoise"] = float(hparams.get("denoise", inputs["denoise"]))
        # MiniMax-style prompt fields
        for pk in ("prompt", "positive", "motion_prompt", "video_prompt"):
            if pk in inputs and isinstance(inputs[pk], str):
                marker = inputs[pk].strip().upper()
                if marker in {"{{VIDEO_PROMPT}}", "{{MOTION_PROMPT}}", "VIDEO_PROMPT", ""}:
                    inputs[pk] = video_prompt
        if ctype.lower().startswith("minimax") or "minimax" in ctype.lower():
            for pk in ("prompt", "text", "positive"):
                if pk in inputs:
                    inputs[pk] = video_prompt
    return graph


def build_minimax_graph(
    start_prompt: str,
    video_prompt: str,
    hparams: dict[str, float],
    *,
    negative: str = "",
    prefix: str = "dspy_opt/gvd_minimax",
) -> dict:
    """FLUX.1 start frame piped into MiniMax I2V (192 frames / 8s).

    Until ``graphs/flux_minimax_i2v_api.json`` is provided, returns a scaffold
    graph with placeholder class_types. Node IDs and class_types must be
    replaced by the real ComfyUI API export; frame length is already forced
    to ``MINIMAX_NUM_FRAMES`` (192).
    """
    if MINIMAX_GRAPH_TEMPLATE.exists():
        graph = json.loads(MINIMAX_GRAPH_TEMPLATE.read_text(encoding="utf-8"))
        if not isinstance(graph, dict):
            raise RuntimeError(f"MiniMax template must be a dict: {MINIMAX_GRAPH_TEMPLATE}")
    else:
        # Scaffold awaiting user-supplied ComfyUI API JSON.
        graph = {
            "_meta": {
                "architecture": "flux1_fp8_gguf_to_minimax_i2v",
                "status": "AWAITING_COMFY_API_JSON",
                "template_path": str(MINIMAX_GRAPH_TEMPLATE),
                "num_frames": MINIMAX_NUM_FRAMES,
                "filename_prefix": prefix,
            },
            "flux_clip": {
                "class_type": "CLIPTextEncodeFluxPLACEHOLDER",
                "inputs": {"text": "{{START_PROMPT}}", "clip": ["flux_loader", 0]},
            },
            "flux_loader": {
                "class_type": "UNETLoaderGGUFPLACEHOLDER",
                "inputs": {"unet_name": "flux1-dev-fp8-gguf-PLACEHOLDER.gguf"},
            },
            "flux_sampler": {
                "class_type": "KSamplerPLACEHOLDER",
                "inputs": {
                    "seed": 42,
                    "steps": int(round(hparams.get("step_count", 28))),
                    "cfg": float(hparams.get("cfg_scale", 5.5)),
                    "denoise": float(hparams.get("denoise", 1.0)),
                    "model": ["flux_loader", 0],
                    "positive": ["flux_clip", 0],
                    "latent_image": ["flux_empty", 0],
                },
            },
            "flux_empty": {
                "class_type": "EmptyLatentImagePLACEHOLDER",
                "inputs": {"width": 1280, "height": 720, "batch_size": 1},
            },
            "flux_decode": {
                "class_type": "VAEDecodePLACEHOLDER",
                "inputs": {"samples": ["flux_sampler", 0], "vae": ["flux_vae", 0]},
            },
            "flux_vae": {
                "class_type": "VAELoaderPLACEHOLDER",
                "inputs": {"vae_name": "ae.safetensors"},
            },
            "minimax_i2v": {
                "class_type": "MiniMaxImageToVideoPLACEHOLDER",
                "inputs": {
                    "image": ["flux_decode", 0],
                    "prompt": "{{VIDEO_PROMPT}}",
                    "negative_prompt": negative or "",
                    "num_frames": MINIMAX_NUM_FRAMES,
                    "cfg": float(hparams.get("cfg_scale", 5.5)),
                    "seed": 42,
                },
            },
            "save_mp4": {
                "class_type": "SaveVideoPLACEHOLDER",
                "inputs": {
                    "video": ["minimax_i2v", 0],
                    "filename_prefix": prefix,
                },
            },
        }

    graph = _inject_prompt_fields(
        graph,
        start_prompt=start_prompt,
        video_prompt=video_prompt,
        negative=negative or "",
        hparams=hparams,
    )
    graph = _force_frame_length(graph, MINIMAX_NUM_FRAMES)
    # Always stamp meta
    meta = graph.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["num_frames"] = MINIMAX_NUM_FRAMES
        meta["architecture"] = meta.get("architecture") or "flux1_to_minimax_i2v"
    return graph


def build_wan_graph(
    start_name: str,
    end_name: str,
    prompt: str,
    negative: str,
    prefix: str,
    *,
    cfg_scale: float,
    denoise: float,
    step_count: float,
) -> dict:
    """DEPRECATED: Wan FLF path retired. Raises to catch stale callers."""
    raise RuntimeError(
        "build_wan_graph is retired. Use build_minimax_graph(start_prompt, "
        "video_motion_prompt, hparams) for FLUX.1 + MiniMax I2V."
    )

'''
orch = orch[: m.start()] + new_build + orch[m.end() :]

# Replace generate_wan_clip with generate_minimax_clip
m = re.search(r"\ndef generate_wan_clip\([\s\S]*?\n    return wait_for_video\([^\)]*\)\n", orch)
if not m:
    # try alternate ending
    m = re.search(r"\ndef generate_wan_clip\([\s\S]*?(?=\ndef [a-z_]+)", orch)
if not m:
    raise SystemExit("generate_wan_clip not found")

new_gen = '''
def _director_start_prompt(example: Any, pred: Any) -> str:
    """FLUX still text: dataset override, then pred.start_prompt, then legacy."""
    return str(
        _field(example, "start_prompt")
        or _field(pred, "start_prompt")
        or _field(pred, "positive_prompt")
        or ""
    ).strip()


def _director_motion_prompt(pred: Any) -> str:
    """MiniMax motion text: pred.video_motion_prompt, then legacy positive."""
    return str(
        _field(pred, "video_motion_prompt")
        or _field(pred, "positive_prompt")
        or ""
    ).strip()


def generate_minimax_clip(
    example: Any,
    pred: Any,
    hparams: dict[str, float],
    *,
    timeout_s: float = WAN_TIMEOUT_S,
) -> Path:
    """FLUX.1 start frame → MiniMax I2V (192 frames). Caller owns VRAM.

    After the MP4 is on disk, immediately POST Comfy ``/free`` so the RTX 5080
    can load Qwen-VL. The graph template may still be a scaffold until the
    user drops the real API JSON at ``graphs/flux_minimax_i2v_api.json``.
    """
    import comfy_api
    from dispatcher import DEFAULT_COMFY_URL as orch_url
    from dispatcher import PipelineOrchestrator
    from live_vram_test import JOB_TIMEOUT_S, wait_for_video
    import vram_controller

    url = orch_url or DEFAULT_COMFY_URL
    if not comfy_api.ping(url):
        raise TimeoutError("ComfyUI is not listening on 127.0.0.1:8188")

    start_prompt = _director_start_prompt(example, pred)
    video_prompt = _director_motion_prompt(pred)
    negative = str(_field(pred, "negative_prompt") or "").strip()
    clip_id = str(_field(example, "id") or _field(example, "clip_id") or "gvd")
    if not start_prompt:
        raise ValueError("start_prompt is empty; FLUX still skipped")
    if not video_prompt:
        raise ValueError("video_motion_prompt is empty; MiniMax I2V skipped")

    key = hashlib.sha256(
        json.dumps(
            {
                "start": start_prompt,
                "motion": video_prompt,
                "cfg": hparams["cfg_scale"],
                "denoise": hparams["denoise"],
                "steps": hparams["step_count"],
                "clip": clip_id,
                "frames": MINIMAX_NUM_FRAMES,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:10]
    prefix = f"dspy_opt/gvd_{clip_id}_{key}"
    graph = build_minimax_graph(
        start_prompt,
        video_prompt,
        hparams,
        negative=negative,
        prefix=prefix,
    )
    if str((graph.get("_meta") or {}).get("status") or "") == "AWAITING_COMFY_API_JSON":
        raise RuntimeError(
            "FLUX+MiniMax Comfy API JSON not installed yet. Save the workflow "
            f"export to {MINIMAX_GRAPH_TEMPLATE} then re-run."
        )

    orch = PipelineOrchestrator(comfy_url=url)
    queued = orch.submit_prompt(graph)
    pid = queued["prompt_id"]
    tracked = orch.track_prompt_id(pid, timeout_s=min(float(JOB_TIMEOUT_S), float(timeout_s)))
    if tracked.get("state") != "complete":
        raise TimeoutError(f"FLUX+MiniMax job did not complete: {tracked}")
    video_path = wait_for_video(pid, orch.comfy_url, timeout_s=60)

    # CRITICAL: free Comfy / FLUX / MiniMax VRAM before Qwen-VL.
    try:
        vram_controller.comfy_free_memory(
            unload_models=True, free_memory=True, update_state=True
        )
    except Exception:
        try:
            vram_controller.release_after_comfyui(reason="MiniMax MP4 saved; /free")
        except Exception:
            pass
    return video_path


def generate_wan_clip(
    example: Any,
    pred: Any,
    hparams: dict[str, float],
    *,
    timeout_s: float = WAN_TIMEOUT_S,
) -> Path:
    """DEPRECATED alias — routes to MiniMax I2V path."""
    return generate_minimax_clip(
        example, pred, hparams, timeout_s=timeout_s
    )

'''
orch = orch[: m.start()] + "\n" + new_gen + orch[m.end() :]

# Phase 3 — mechanical_director_gate category-aware
old_gate = '''def mechanical_director_gate(example: Any, pred: Any, video_path: Path | None = None) -> dict:
    """Category-aware mechanical check. Does not load the VLM."""
    prompt = str(_field(pred, "positive_prompt") or "").strip()
    reasons: list[str] = []
    if not prompt:
        reasons.append("positive_prompt is empty")
    duration_raw = _field(example, "duration_seconds")
    if duration_raw is None or duration_raw == "":
        duration = 8.0
    else:
        try:
            duration = float(duration_raw)
        except (TypeError, ValueError):
            duration = 0.0
            reasons.append("duration_seconds is not a number")
    if duration <= 0:
        reasons.append("duration_seconds must be positive")
    if is_backrooms_example(example):
        lowered = prompt.lower()
        if not any(token in lowered for token in _CAMERA_KEYWORDS):
            reasons.append(
                "backrooms clip missing a camera keyword (handheld, camcorder, first-person)"
            )
        if not any(token in lowered for token in _MOTION_KEYWORDS):
            reasons.append(
                "backrooms clip missing a motion keyword (walk, walking, momentum)"
            )
    return {"status": "pass" if not reasons else "fail", "reasons": reasons}'''

new_gate = '''def _example_category(example: Any) -> str:
    return str(_field(example, "category") or "").strip().lower()


def _is_drone_or_cinematic(example: Any) -> bool:
    cat = _example_category(example)
    if cat in _DRONE_OR_CINEMATIC_CATEGORIES:
        return True
    if "drone" in cat or "cinematic" in cat:
        return True
    return False


def mechanical_director_gate(example: Any, pred: Any, video_path: Path | None = None) -> dict:
    """Category-aware mechanical check. Does not load the VLM.

    drone / cinematic: only require non-empty prompts + positive duration
    (skip VHS / liminal / handheld checks).
    backrooms: any camera noun AND any motion verb (no exact-phrase lock).
    """
    start_prompt = _director_start_prompt(example, pred)
    motion_prompt = _director_motion_prompt(pred)
    # Combined text for keyword scans; prefer motion prompt for camera/motion.
    prompt = motion_prompt or start_prompt
    reasons: list[str] = []
    if not start_prompt:
        reasons.append("start_prompt is empty")
    if not motion_prompt:
        reasons.append("video_motion_prompt is empty")
    duration_raw = _field(example, "duration_seconds")
    if duration_raw is None or duration_raw == "":
        duration = 8.0
    else:
        try:
            duration = float(duration_raw)
        except (TypeError, ValueError):
            duration = 0.0
            reasons.append("duration_seconds is not a number")
    if duration <= 0:
        reasons.append("duration_seconds must be positive")

    if _is_drone_or_cinematic(example):
        # Bypass VHS / liminal / handheld requirements entirely.
        return {"status": "pass" if not reasons else "fail", "reasons": reasons}

    if is_backrooms_example(example):
        lowered = (motion_prompt or prompt).lower()
        if not any(token in lowered for token in _CAMERA_KEYWORDS):
            reasons.append(
                "backrooms clip missing a camera keyword "
                "(handheld, camcorder, first-person, fpv, pov)"
            )
        if not any(token in lowered for token in _MOTION_KEYWORDS):
            reasons.append(
                "backrooms clip missing a motion keyword "
                "(walk, push in, tracking forward, dolly, ...)"
            )
    return {"status": "pass" if not reasons else "fail", "reasons": reasons}


def passes_curriculum(
    example: Any,
    pred: Any,
    parsed: dict | None = None,
    iteration: int = 0,
    *,
    video_path: Path | None = None,
) -> dict:
    """Category-aware curriculum entrypoint used by live eval.

    Mechanical gate first (drone/cinematic bypass of VHS checks); then the
    progressive VLM score bar when ``parsed`` is provided.
    """
    mech = mechanical_director_gate(example, pred, video_path)
    if mech.get("status") != "pass":
        return {
            "pass": False,
            "threshold": None,
            "iteration": int(iteration or 0),
            "compared": None,
            "reasons": list(mech.get("reasons") or []),
            "mechanical": mech,
        }
    if parsed is None:
        return {
            "pass": True,
            "threshold": None,
            "iteration": int(iteration or 0),
            "compared": None,
            "reasons": [],
            "mechanical": mech,
        }
    scored = video_director_passes_curriculum(parsed, iteration, use_minimum=True)
    scored["mechanical"] = mech
    return scored'''

orch = must_replace(orch, old_gate, new_gate, "mechanical_director_gate")

# Phase 4 — evaluate_live_candidate: use motion prompt, default render=minimax, /free already in generate
old_eval_head = '''    hparams, hparam_notes = parse_director_hparams(pred)
    prompt = str(_field(pred, "positive_prompt") or "").strip()
    if not prompt:
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error="positive_prompt is empty; skipped GPU",
        )

    prepare_comfy = prepare_comfy or vram_controller.prepare_for_comfyui
    release_comfy = release_comfy or vram_controller.release_after_comfyui
    prepare_vlm = prepare_vlm or vram_controller.prepare_for_vlm
    release_vlm = release_vlm or vram_controller.release_after_vlm
    render = render_fn or generate_wan_clip
    extract = extract_fn or extract_eval_frames
    judge = vlm_fn or run_qwen_director_scores

    video_path: Path | None = None
    vram_trace: list[dict[str, Any]] = []
    try:
        prepare_comfy(reason="Wan 2.1 generation")
        vram_trace.append(_vram_snapshot("after_prepare_comfy"))
        video_path = render(example, pred, hparams)
        vram_trace.append(_vram_snapshot("after_wan"))'''

new_eval_head = '''    hparams, hparam_notes = parse_director_hparams(pred)
    start_prompt = _director_start_prompt(example, pred)
    motion_prompt = _director_motion_prompt(pred)
    # VLM judges motion execution against video_motion_prompt; start_prompt is baseline.
    prompt = motion_prompt
    if not start_prompt or not motion_prompt:
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error="start_prompt or video_motion_prompt is empty; skipped GPU",
        )

    prepare_comfy = prepare_comfy or vram_controller.prepare_for_comfyui
    release_comfy = release_comfy or vram_controller.release_after_comfyui
    prepare_vlm = prepare_vlm or vram_controller.prepare_for_vlm
    release_vlm = release_vlm or vram_controller.release_after_vlm
    render = render_fn or generate_minimax_clip
    extract = extract_fn or extract_eval_frames
    judge = vlm_fn or run_qwen_director_scores

    video_path: Path | None = None
    vram_trace: list[dict[str, Any]] = []
    try:
        prepare_comfy(reason="FLUX.1 + MiniMax I2V generation")
        vram_trace.append(_vram_snapshot("after_prepare_comfy"))
        video_path = render(example, pred, hparams)
        # /free already fired inside generate_minimax_clip after MP4 save.
        try:
            vram_controller.comfy_free_memory(
                unload_models=True, free_memory=True, update_state=True
            )
        except Exception:
            pass
        vram_trace.append(_vram_snapshot("after_minimax_and_free"))'''

orch = must_replace(orch, old_eval_head, new_eval_head, "evaluate_live head")

# Fix remaining Wan wording in evaluate finally/error strings (best-effort)
orch = orch.replace('release_comfy(reason="Wan 2.1 complete")', 'release_comfy(reason="FLUX+MiniMax complete; VRAM free for VLM")')
orch = orch.replace(
    'error="Wan 2.1 produced no video path"',
    'error="FLUX+MiniMax produced no video path"',
)

# VLM judge should receive composite instruction context
old_judge_call = "        parsed = judge(frames, prompt)"
new_judge_call = '''        vlm_prompt = (
            f"START_FRAME_BASELINE: {start_prompt}\\n"
            f"VIDEO_MOTION_PROMPT: {motion_prompt}"
        )
        parsed = judge(frames, vlm_prompt)'''
if old_judge_call in orch:
    orch = orch.replace(old_judge_call, new_judge_call, 1)
else:
    print("WARN: judge(frames, prompt) call not found")

orch_path.write_text(orch, encoding="utf-8")
compile(orch, str(orch_path), "exec")
print("PHASE2-4 OK dspy_orchestrator.py")

# ---------------------------------------------------------------------------
# PHASE 4 — VLM system prompt in media_accuracy_gate.py
# ---------------------------------------------------------------------------
gate_path = BASE / "media_accuracy_gate.py"
bak(gate_path)
gate = gate_path.read_text(encoding="utf-8")
m = re.search(
    r"VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT\s*=\s*[\"\']{3}([\s\S]*?)[\"\']{3}",
    gate,
)
if not m:
    raise SystemExit("VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT not found")

new_vlm = '''VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT = """You are a strict video-quality judge for a local FLUX.1 + MiniMax I2V director.

You will receive (1) a START_FRAME_BASELINE still description, (2) a VIDEO_MOTION_PROMPT, and (3) sampled frames in chronological order from a single clip.

There is NO end_prompt. Score text_video_alignment solely on how well the video executes the motion and camera behavior described in VIDEO_MOTION_PROMPT, using START_FRAME_BASELINE only as the expected opening look (subject, setting, style).

Score ONLY what is visible in the frames. Do not reward the prompt's poetry. Do not invent unseen motion. Do not average in how hard the prompt was.

Return ONE JSON object and nothing else. No markdown fences. No preface. No trailing commentary.

Required schema:
{
  "text_video_alignment": <float 0.00 to 1.00>,
  "temporal_consistency": <float 0.00 to 1.00>,
  "aesthetic_quality": <float 0.00 to 1.00>,
  "rationale": {
    "text_video_alignment": "<one sentence>",
    "temporal_consistency": "<one sentence>",
    "aesthetic_quality": "<one sentence>"
  }
}

Scoring rules:
- Every score is a JSON number, not a string. Use two decimal places.
- 0.00 = total failure of that axis. 0.50 = mixed or partial. 1.00 = excellent and unambiguous.
- text_video_alignment: the camera move, subject motion, pace, and actions named in VIDEO_MOTION_PROMPT appear across the frames; the opening look should be compatible with START_FRAME_BASELINE. Penalize frozen stills when motion was requested, wrong direction/pace, and missing camera behavior.
- temporal_consistency: identity, geometry, and lighting hold across frames; motion is physically plausible; no flicker, morph, teleport, identity swap, or random scene change.
- aesthetic_quality: composition, color, focus, and artifact load. Penalize watermarks, burned-in text, crushed detail, muddy frames, and plastic over-smoothing.

Do not include a boolean pass field. Do not include cfg, denoise, or step counts. Downstream Python applies a progressive threshold (0.60 early, tightening to 0.85).
"""'''

gate = gate[: m.start()] + new_vlm + "\n" + gate[m.end() :]
gate_path.write_text(gate, encoding="utf-8")
compile(gate, str(gate_path), "exec")
print("PHASE4 VLM OK media_accuracy_gate.py")

# graphs dir placeholder
graphs = BASE / "graphs"
graphs.mkdir(exist_ok=True)
readme = graphs / "README_flux_minimax.md"
readme.write_text(
    "# FLUX.1 + MiniMax I2V template\\n\\n"
    "Drop the ComfyUI API-format workflow export here as:\\n\\n"
    "  `flux_minimax_i2v_api.json`\\n\\n"
    "Required placeholders (string values Comfy will replace via orchestrator):\\n"
    "- `{{START_PROMPT}}` on the FLUX text-encode node\\n"
    "- `{{VIDEO_PROMPT}}` on the MiniMax I2V prompt field\\n"
    "- frame/length input will be forced to **192** (8s @ 24fps)\\n",
    encoding="utf-8",
)
print("wrote", readme)

print("ALL DONE", TS)
