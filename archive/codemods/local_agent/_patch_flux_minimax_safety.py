from __future__ import annotations

import ast
import re
import shutil
import time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
TS = time.strftime("%Y%m%dT%H%M%S")


def bak(path: Path) -> None:
    shutil.copy2(path, path.with_name(path.name + f".bak_flux_safety_{TS}"))


def wipe_compiled() -> list[str]:
    wiped: list[str] = []
    for comp in [
        ROOT / "models" / "dspy_compiled",
        BASE / "models" / "dspy_compiled",
    ]:
        comp.mkdir(parents=True, exist_ok=True)
        for p in list(comp.glob("*.json")):
            if ".bak_wipe_" in p.name:
                continue
            dest = p.with_name(p.name + f".bak_wipe_{TS}")
            p.rename(dest)
            wiped.append(str(dest))
    return wiped


def patch_gvd() -> None:
    path = BASE / "generalized_video_director.py"
    bak(path)
    text = path.read_text(encoding="utf-8")

    new_instr = (
        "DIRECTOR_SIGNATURE_INSTRUCTIONS = (\n"
        "    \"You are a Generalized Video Director for FLUX.1 (start frame) + MiniMax \"\n"
        "    \"Image-to-Video on an RTX 5080. Emit start_prompt, video_prompt, \"\n"
        "    \"negative_prompt, and numeric hparams cfg_scale and step_count only.\\n\"\n"
        "    \"start_prompt (FLUX.1 T2I): highly descriptive natural language for a SINGLE \"\n"
        "    \"still opening frame. Focus on lighting, texture, materials, composition, \"\n"
        "    \"lens/look. No camera-move verbs.\\n\"\n"
        "    \"video_prompt (MiniMax I2V): focus STRICTLY on camera physics, subject motion, \"\n"
        "    \"and temporal change across an 8-second / 192-frame clip. Name move, pace, \"\n"
        "    \"and ending energy. Do not rewrite the whole scene from scratch.\\n\"\n"
        "    \"Do NOT emit denoise — FLUX Empty Latent T2I always uses denoise=1.0.\\n\"\n"
        "    \"Do NOT emit end_prompt.\\n\"\n"
        "    \"Honor category:\\n\"\n"
        "    \"- drone_high_kinematics: aerial/high-speed travel, large parallax; prefer \"\n"
        "    \"cfg_scale 4.0-5.5; step_count 24-32.\\n\"\n"
        "    \"- macro_nature: extreme close-up, shallow DOF, slow organic motion; prefer \"\n"
        "    \"cfg_scale 5.5-7.0; step_count 28-36.\\n\"\n"
        "    \"- stylized_2d: lock the named 2D medium every frame; prefer cfg_scale 6.0-7.5; \"\n"
        "    \"step_count 20-30.\\n\"\n"
        "    \"- backrooms: first-person analog camcorder unless locked; prefer cfg_scale \"\n"
        "    \"5.0-6.5; step_count 24-32. Put camera nouns AND motion verbs in video_prompt; \"\n"
        "    \"put VHS/liminal look in start_prompt.\\n\"\n"
        "    \"cfg_scale and step_count MUST be JSON numbers (floats). cfg_scale in [1.0, 8.0], \"\n"
        "    \"step_count in [16, 40].\"\n"
        ")\n"
    )
    if re.search(r"DIRECTOR_SIGNATURE_INSTRUCTIONS\s*=\s*\(", text):
        text = re.sub(
            r"DIRECTOR_SIGNATURE_INSTRUCTIONS\s*=\s*\([\s\S]*?\)\n",
            new_instr + "\n",
            text,
            count=1,
        )
    else:
        raise SystemExit("DIRECTOR_SIGNATURE_INSTRUCTIONS missing")

    # Replace nested signature class
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
    # Drop denoise from any remaining output field definitions if present
    text = re.sub(
        r"\n\s*denoise:\s*float\s*=\s*dspy\.OutputField\([\s\S]*?\)\n",
        "\n",
        text,
    )
    path.write_text(text, encoding="utf-8")
    ast.parse(text)
    print("PHASE1 gvd OK")


def patch_orchestrator() -> None:
    path = BASE / "dspy_orchestrator.py"
    bak(path)
    text = path.read_text(encoding="utf-8")
    text = text.replace("video_motion_prompt", "video_prompt")

    # Hardcode denoise=1.0 on node 3 mapping
    text2, n = re.subn(
        r"node3\[\"inputs\"\]\[\"denoise\"\]\s*=\s*[^\n]+",
        'node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
        text,
        count=0,
    )
    text = text2
    print("denoise hardcodes", n)
    if n == 0:
        # inject after steps assignment inside mapper
        text, n2 = re.subn(
            r"(node3\[\"inputs\"\]\[\"steps\"\]\s*=\s*int\([^\n]+\))",
            r"\1\n        node3[\"inputs\"][\"denoise\"] = 1.0  # FLUX Empty Latent T2I: always full denoise",
            text,
            count=1,
        )
        print("denoise inject", n2)

    # Ensure cfg/steps still mapped from hparams (already present). Add safety helper.
    if "def _flux_safe_hparams" not in text:
        helper = '''

def _flux_safe_hparams(hparams: dict[str, float]) -> dict[str, float]:
    """FLUX Empty-Latent T2I safety: denoise locked at 1.0; optimizer may tune cfg/steps only."""
    out = dict(hparams or {})
    out["denoise"] = 1.0
    if "cfg_scale" in out:
        out["cfg_scale"] = float(out["cfg_scale"])
    if "step_count" in out:
        out["step_count"] = float(out["step_count"])
    # Ignore any learner-emitted denoise.
    return out

'''
        # place before build_minimax_graph
        if "\ndef build_minimax_graph(" in text:
            text = text.replace("\ndef build_minimax_graph(", helper + "\ndef build_minimax_graph(", 1)
        else:
            text = helper + text

    if "hparams = _flux_safe_hparams(hparams)" not in text:
        text, n = re.subn(
            r"(def generate_minimax_clip\([\s\S]*?\):\n(?:\s+\"\"\"[\s\S]*?\"\"\"\n)?)",
            r"\1    hparams = _flux_safe_hparams(hparams)\n",
            text,
            count=1,
        )
        print("safe hparams inject", n)

    # parse_director_hparams: remove denoise from required learner fields if listed
    text = re.sub(
        r"[\'\"]denoise[\'\"]\s*:\s*\([^\)]*\),?\n",
        "",
        text,
    )

    # VLM frame cap
    if "def extract_eval_frames" in text:
        m = re.search(r"def extract_eval_frames\([\s\S]*?\n(?=def )", text)
        if not m:
            raise SystemExit("extract_eval_frames body not isolated")
        fn = m.group(0)
        fn2 = re.sub(r"(count:\s*int\s*=\s*)\d+", r"\g<1>10", fn, count=1)
        if "never send the full clip to Qwen-VL" not in fn2 and "cap VLM input" not in fn2:
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
        # Also force any OpenCV/decord full-scan paths to subsample
        if "np.linspace" not in fn2 and "uniform" not in fn2.lower():
            # add note; existing implementations often already index by linspace
            pass
        text = text[: m.start()] + fn2 + text[m.end() :]
        print("patched extract_eval_frames")
    else:
        print("WARN: extract_eval_frames missing in orchestrator")

    path.write_text(text, encoding="utf-8")
    ast.parse(text)
    print("PHASE2/3 orchestrator OK")


def patch_other_frame_readers() -> None:
    for p in BASE.glob("*.py"):
        if p.name == "dspy_orchestrator.py":
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if "def extract_eval_frames" not in t and "VideoReader" not in t:
            continue
        if "def extract_eval_frames" in t and "max(8, min(12" not in t:
            bak(p)
            t2 = t
            t2 = re.sub(r"(count:\s*int\s*=\s*)\d+", r"\g<1>10", t2, count=1)
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
            p.write_text(t2, encoding="utf-8")
            ast.parse(t2)
            print("patched frames in", p.name)


def verify() -> None:
    import sys

    sys.path.insert(0, str(BASE))
    for mod in list(sys.modules):
        if mod in {"dspy_orchestrator", "generalized_video_director"} or mod.startswith(
            "dspy_orchestrator."
        ) or mod.startswith("generalized_video_director."):
            del sys.modules[mod]
    import generalized_video_director as gvd
    import dspy_orchestrator as o

    sig = gvd.director_signature_class()
    outs = list(sig.output_fields.keys())
    print("signature outputs", outs)
    assert "denoise" not in outs
    assert "end_prompt" not in outs
    assert "start_prompt" in outs
    assert "video_prompt" in outs
    assert "cfg_scale" in outs and "step_count" in outs

    # denoise hard lock in graph map
    g = o.build_minimax_graph(
        "start hall",
        "walk forward handheld",
        {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 24},
        negative="blur",
        prefix="dspy_opt/safety",
    )
    assert g["3"]["inputs"]["denoise"] == 1.0
    assert g["3"]["inputs"]["cfg"] == 4.0
    assert g["3"]["inputs"]["steps"] == 24
    print("node3 denoise locked", g["3"]["inputs"]["denoise"])

    # frame cap
    import inspect

    src = inspect.getsource(o.extract_eval_frames)
    assert "max(8, min(12" in src
    print("VLM frame cap present")

    comp = ROOT / "models" / "dspy_compiled"
    live = [p.name for p in comp.glob("*.json")]
    print("live compiled json", live)
    assert not live
    print("VERIFY ALL OK")


if __name__ == "__main__":
    print("wipe", wipe_compiled())
    patch_gvd()
    patch_orchestrator()
    patch_other_frame_readers()
    verify()
