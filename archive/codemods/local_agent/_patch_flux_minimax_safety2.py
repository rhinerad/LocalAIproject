from __future__ import annotations

import ast
import re
import shutil
import sys
import time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
TS = time.strftime("%Y%m%dT%H%M%S")


def wipe_compiled() -> list[str]:
    wiped = []
    for comp in [ROOT / "models" / "dspy_compiled", BASE / "models" / "dspy_compiled"]:
        if not comp.exists():
            continue
        for p in list(comp.glob("*.json")):
            if ".bak_wipe_" in p.name:
                continue
            dest = p.with_name(p.name + f".bak_wipe_{TS}")
            p.rename(dest)
            wiped.append(str(dest))
    return wiped


def patch_gvd() -> None:
    path = BASE / "generalized_video_director.py"
    shutil.copy2(path, path.with_name(path.name + f".bak_flux_safety2_{TS}"))
    text = path.read_text(encoding="utf-8")

    # Build instructions with real newlines in the Python source as adjacent string literals
    # that each end cleanly (no embedded raw newlines inside quotes).
    parts = [
        "You are a Generalized Video Director for FLUX.1 (start frame) + MiniMax ",
        "Image-to-Video on an RTX 5080. Emit start_prompt, video_prompt, ",
        "negative_prompt, and numeric hparams cfg_scale and step_count only.\\n",
        "start_prompt (FLUX.1 T2I): highly descriptive natural language for a SINGLE ",
        "still opening frame. Focus on lighting, texture, materials, composition, ",
        "lens/look. No camera-move verbs.\\n",
        "video_prompt (MiniMax I2V): focus STRICTLY on camera physics, subject motion, ",
        "and temporal change across an 8-second / 192-frame clip. Name move, pace, ",
        "and ending energy. Do not rewrite the whole scene from scratch.\\n",
        "Do NOT emit denoise — FLUX Empty Latent T2I always uses denoise=1.0.\\n",
        "Do NOT emit end_prompt.\\n",
        "Honor category:\\n",
        "- drone_high_kinematics: aerial/high-speed travel, large parallax; prefer ",
        "cfg_scale 4.0-5.5; step_count 24-32.\\n",
        "- macro_nature: extreme close-up, shallow DOF, slow organic motion; prefer ",
        "cfg_scale 5.5-7.0; step_count 28-36.\\n",
        "- stylized_2d: lock the named 2D medium every frame; prefer cfg_scale 6.0-7.5; ",
        "step_count 20-30.\\n",
        "- backrooms: first-person analog camcorder unless locked; prefer cfg_scale ",
        "5.0-6.5; step_count 24-32. Put camera nouns AND motion verbs in video_prompt; ",
        "put VHS/liminal look in start_prompt.\\n",
        "cfg_scale and step_count MUST be JSON numbers (floats). cfg_scale in [1.0, 8.0], ",
        "step_count in [16, 40].",
    ]
    body = "\n".join(f'    "{p}"' for p in parts)
    new_instr = f"DIRECTOR_SIGNATURE_INSTRUCTIONS = (\n{body}\n)\n"
    if not re.search(r"DIRECTOR_SIGNATURE_INSTRUCTIONS\s*=\s*\(", text):
        raise SystemExit("instructions missing")
    text = re.sub(
        r"DIRECTOR_SIGNATURE_INSTRUCTIONS\s*=\s*\([\s\S]*?\)\n",
        new_instr + "\n",
        text,
        count=1,
    )

    # Replace signature class (nested under director_signature_class)
    sig_pat = re.compile(
        r"    class GeneralizedVideoDirectorSignature\(dspy\.Signature\):[\s\S]*?"
        r"(?=\n    GeneralizedVideoDirectorSignature\.instructions=|\n\n    return |\n\ndef )"
    )
    new_sig = '''    class GeneralizedVideoDirectorSignature(dspy.Signature):
        """Direct FLUX.1 start frame + MiniMax I2V motion (no end_prompt, no denoise)."""

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
            desc="Clip length in seconds (8 for MiniMax 192 frames)"
        )
        constraints: str = dspy.InputField(
            desc="Hard rejection clauses the prompt must honor"
        )
        start_prompt: str = dspy.OutputField(
            desc="FLUX.1 still prompt: descriptive lighting/texture/composition for the opening frame only"
        )
        video_prompt: str = dspy.OutputField(
            desc="MiniMax I2V prompt: camera physics, subject motion, temporal change only"
        )
        negative_prompt: str = dspy.OutputField(
            desc="Comma-separated failure modes to suppress"
        )
        cfg_scale: float = dspy.OutputField(
            desc="FLUX KSampler CFG, JSON float in [1.0, 8.0]"
        )
        step_count: float = dspy.OutputField(
            desc="FLUX KSampler steps as a float in [16, 40]; rounded to int later"
        )
'''
    if not sig_pat.search(text):
        raise SystemExit("signature class not found")
    text = sig_pat.sub(new_sig, text, count=1)
    text = text.replace("video_motion_prompt", "video_prompt")
    text = re.sub(
        r"\n\s*denoise:\s*float\s*=\s*dspy\.OutputField\([\s\S]*?\)\n",
        "\n",
        text,
    )
    path.write_text(text, encoding="utf-8")
    ast.parse(text)
    print("PHASE1 gvd OK")


def patch_orch() -> None:
    path = BASE / "dspy_orchestrator.py"
    shutil.copy2(path, path.with_name(path.name + f".bak_flux_safety2_{TS}"))
    text = path.read_text(encoding="utf-8")
    text = text.replace("video_motion_prompt", "video_prompt")

    # Hardcode denoise on every node3 assignment
    text, n = re.subn(
        r'node3\["inputs"\]\["denoise"\]\s*=\s*[^\n]+',
        'node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
        text,
    )
    print("denoise replacements", n)
    if n == 0:
        text, n2 = re.subn(
            r'(node3\["inputs"\]\["steps"\]\s*=\s*int\([^\n]+\))',
            r'\1\n        node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
            text,
            count=1,
        )
        print("denoise inject", n2)

    # Also force in template graph JSON if denoise is there via Python dict write
    # Safety helper
    if "def _flux_safe_hparams" not in text:
        helper = '''

def _flux_safe_hparams(hparams: dict[str, float]) -> dict[str, float]:
    """FLUX Empty-Latent T2I safety: denoise locked at 1.0; only cfg/steps are tunable."""
    out = dict(hparams or {})
    out["denoise"] = 1.0
    if "cfg_scale" in out:
        out["cfg_scale"] = float(out["cfg_scale"])
    if "step_count" in out:
        out["step_count"] = float(out["step_count"])
    return out

'''
        if "\ndef build_minimax_graph(" in text:
            text = text.replace("\ndef build_minimax_graph(", helper + "\ndef build_minimax_graph(", 1)
        elif "\ndef build_wan_graph(" in text:
            text = text.replace("\ndef build_wan_graph(", helper + "\ndef build_wan_graph(", 1)
        else:
            text = helper + "\n" + text

    if "hparams = _flux_safe_hparams(hparams)" not in text:
        text, n = re.subn(
            r'(def generate_minimax_clip\([^\)]*\):\n(?:\s+"""[\s\S]*?"""\n)?)',
            r"\1    hparams = _flux_safe_hparams(hparams)\n",
            text,
            count=1,
        )
        print("safe hparams inject", n)
        if n == 0 and "def generate_wan_clip(" in text:
            text, n = re.subn(
                r'(def generate_wan_clip\([^\)]*\):\n(?:\s+"""[\s\S]*?"""\n)?)',
                r"\1    hparams = _flux_safe_hparams(hparams)\n",
                text,
                count=1,
            )
            print("safe hparams on wan alias", n)

    # Also call inside build_minimax_graph
    if "hparams = _flux_safe_hparams(hparams)" not in text.split("def build_minimax_graph")[1][:800] if "def build_minimax_graph" in text else True:
        text, n = re.subn(
            r'(def build_minimax_graph\([^\)]*\):\n(?:\s+"""[\s\S]*?"""\n)?)',
            r"\1    hparams = _flux_safe_hparams(hparams)\n",
            text,
            count=1,
        )
        print("safe hparams in build_minimax_graph", n)

    # Remove denoise from HPARAM ranges if present as learner field
    # Keep denoise key in fallbacks as 1.0 constant

    # PHASE 3: frame cap
    if "def extract_eval_frames" in text:
        m = re.search(r"def extract_eval_frames\([\s\S]*?\n(?=def )", text)
        if m:
            fn = m.group(0)
            fn2 = re.sub(r"(count:\s*int\s*=\s*)\d+", r"\g<1>10", fn, count=1)
            if "cap VLM input" not in fn2 and "never send the full clip" not in fn2.lower():
                fn2 = re.sub(
                    r"(def extract_eval_frames\([^\)]*\):\n(?:\s+\"\"\"[\s\S]*?\"\"\"\n)?)",
                    r"\1"
                    r"    # MiniMax emits ~192 frames; NEVER feed the full clip to Qwen-VL.\n"
                    r"    try:\n"
                    r"        _requested = int(count)\n"
                    r"    except Exception:\n"
                    r"        _requested = 10\n"
                    r"    count = int(max(8, min(12, _requested)))\n",
                    fn2,
                    count=1,
                )
            text = text[: m.start()] + fn2 + text[m.end() :]
            print("patched extract_eval_frames")
    else:
        print("WARN no extract_eval_frames")

    # Also patch media_accuracy_gate / other modules
    path.write_text(text, encoding="utf-8")
    ast.parse(text)
    print("PHASE2/3 orch OK")


def patch_media_gate_and_others() -> None:
    for name in ["media_accuracy_gate.py", "live_vram_test.py", "vlm_judge.py"]:
        p = BASE / name
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        changed = False
        if "video_motion_prompt" in t:
            t = t.replace("video_motion_prompt", "video_prompt")
            changed = True
        if "def extract_eval_frames" in t and "max(8, min(12" not in t:
            t2 = re.sub(r"(count:\s*int\s*=\s*)\d+", r"\g<1>10", t, count=1)
            t2 = re.sub(
                r"(def extract_eval_frames\([^\)]*\):\n(?:\s+\"\"\"[\s\S]*?\"\"\"\n)?)",
                r"\1"
                r"    # Cap VLM frames to 8-12 for 192-frame MiniMax clips.\n"
                r"    try:\n"
                r"        _requested = int(count)\n"
                r"    except Exception:\n"
                r"        _requested = 10\n"
                r"    count = int(max(8, min(12, _requested)))\n",
                t2,
                count=1,
            )
            if t2 != t:
                t = t2
                changed = True
        # Also look for frame sampling constants
        if re.search(r"MAX_.*FRAMES\s*=\s*\d+", t) or "num_frames" in t and "192" in t:
            # Soft: force any default of 192 for VLM down
            t2 = re.sub(r"(VLM_.*FRAMES\s*=\s*)\d+", r"\g<1>10", t)
            t2 = re.sub(r"(MAX_VLM_FRAMES\s*=\s*)\d+", r"\g<1>10", t2)
            if t2 != t:
                t = t2
                changed = True
        if changed:
            shutil.copy2(p, p.with_name(p.name + f".bak_flux_safety2_{TS}"))
            p.write_text(t, encoding="utf-8")
            ast.parse(t)
            print("patched", name)


def find_frame_funcs() -> None:
    for p in BASE.glob("*.py"):
        t = p.read_text(encoding="utf-8", errors="replace")
        hits = []
        for key in ["extract_eval_frames", "VideoReader", "cv2.VideoCapture", "sample_frames", "decode_video"]:
            if key in t:
                hits.append(key)
        if hits:
            print("FRAME", p.name, hits)


def verify() -> None:
    sys.path.insert(0, str(BASE))
    for mod in list(sys.modules):
        if mod in {"dspy_orchestrator", "generalized_video_director", "media_accuracy_gate"} or mod.startswith(
            ("dspy_orchestrator.", "generalized_video_director.")
        ):
            del sys.modules[mod]
    import generalized_video_director as gvd
    import dspy_orchestrator as o

    sig = gvd.director_signature_class()
    outs = list(sig.output_fields.keys())
    print("signature outputs", outs)
    assert "denoise" not in outs, outs
    assert "end_prompt" not in outs, outs
    assert "start_prompt" in outs
    assert "video_prompt" in outs
    assert "cfg_scale" in outs and "step_count" in outs
    instr = gvd.DIRECTOR_SIGNATURE_INSTRUCTIONS
    assert "start_prompt (FLUX.1" in instr
    assert "video_prompt (MiniMax" in instr
    assert "Do NOT emit denoise" in instr

    g = o.build_minimax_graph(
        "start hall",
        "walk forward handheld",
        {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 24},
        negative="blur",
        prefix="dspy_opt/safety",
    )
    assert float(g["3"]["inputs"]["denoise"]) == 1.0, g["3"]["inputs"]
    assert float(g["3"]["inputs"]["cfg"]) == 4.0
    assert int(g["3"]["inputs"]["steps"]) == 24
    print("node3", g["3"]["inputs"]["denoise"], g["3"]["inputs"]["cfg"], g["3"]["inputs"]["steps"])

    import inspect
    src = inspect.getsource(o.extract_eval_frames)
    assert "max(8, min(12" in src, src[:500]
    print("VLM frame cap OK")

    live = []
    for comp in [ROOT / "models" / "dspy_compiled", BASE / "models" / "dspy_compiled"]:
        if comp.exists():
            live.extend([p.name for p in comp.glob("*.json")])
    print("live compiled", live)
    assert not live
    print("VERIFY ALL OK")


if __name__ == "__main__":
    print("WIPED", wipe_compiled())
    patch_gvd()
    patch_orch()
    patch_media_gate_and_others()
    find_frame_funcs()
    verify()
