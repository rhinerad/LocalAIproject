from __future__ import annotations
import ast, hashlib, inspect, re, sys, time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
TS = time.strftime("%Y%m%dT%H%M%S")

def read_no_bom(p: Path) -> str:
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8")

def write_no_bom(p: Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8"))

# --- Fix signature return if still broken ---
gpath = BASE / "generalized_video_director.py"
gt = read_no_bom(gpath)
if "return GeneralizedVideoDirectorSignature" not in gt.split("def director_signature_class()")[1].split("\ndef ")[0]:
    gt2, n = re.subn(
        r"(def director_signature_class\(\):[\s\S]*?)(\n\ndef |\nclass )",
        r"\1\n    return GeneralizedVideoDirectorSignature\n\2",
        gt,
        count=1,
    )
    print("sig return inject", n)
    gt = gt2
    write_no_bom(gpath, gt)
    ast.parse(gt)
else:
    print("sig return OK")

# --- Rewrite extract_eval_frames in dspy_optimizer ---
opt = BASE / "dspy_optimizer.py"
ot = read_no_bom(opt)
backup = opt.with_name(opt.name + f".bak_framecap_{TS}")
backup.write_bytes(ot.encode("utf-8"))

new_fn = '''def extract_eval_frames(video_path: Path, count: int = 10) -> list[Path]:
    """Uniformly sample 8-12 PNG frames for the VLM.

    MiniMax I2V emits ~192 frames (8s @ 24fps). Feeding the full clip to
    Qwen-VL OOMs an RTX 5080, so we always cap to [8, 12] frames.
    """
    import subprocess

    # NEVER send the full 192-frame MiniMax clip to Qwen-VL.
    try:
        _requested = int(count)
    except Exception:
        _requested = 10
    count = int(max(8, min(12, _requested)))

    out_dir = HERE / "runtime" / "dspy_opt" / "eval_frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(video_path).encode()).hexdigest()[:10]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    duration = 2.0
    try:
        raw = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            text=True,
            encoding="utf-8",
            timeout=15,
            creationflags=flags,
        )
        duration = max(0.5, float(raw.strip() or 2.0))
    except Exception:
        pass

    # Uniform sample across the full duration (inclusive endpoints inset slightly).
    if count == 1:
        fracs = (0.5,)
    else:
        fracs = tuple(i / (count - 1) for i in range(count))
        # inset endpoints a hair so we avoid black first/last frames
        fracs = tuple(0.02 + 0.96 * f for f in fracs)

    frames: list[Path] = []
    for i, frac in enumerate(fracs):
        sec = max(0.0, min(duration - 0.05, duration * frac))
        target = out_dir / f"{video_path.stem}_{digest}_{i:02d}_{sec:.3f}s.png"
        if not target.exists():
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(video_path),
                    "-ss",
                    f"{sec:.3f}",
                    "-frames:v",
                    "1",
                    "-c:v",
                    "png",
                    "-y",
                    str(target),
                ],
                check=True,
                capture_output=True,
                timeout=60,
                creationflags=flags,
            )
        frames.append(target)
    return frames


'''

m = re.search(r"def extract_eval_frames\([\s\S]*?\n(?=def )", ot)
assert m, "extract_eval_frames not found"
ot2 = ot[: m.start()] + new_fn + ot[m.end() :]
write_no_bom(opt, ot2)
ast.parse(ot2)
print("optimizer rewrite OK")

# --- Force clamp denoise=1.0 ---
gt = read_no_bom(gpath)
if 'out["denoise"] = 1.0  # FLUX Empty Latent lock' not in gt:
    gt2, n = re.subn(
        r"(def clamp_director_hparams\([\s\S]*?)(\n    return out\n)",
        r'\1\n    out["denoise"] = 1.0  # FLUX Empty Latent lock\n\2',
        gt,
        count=1,
    )
    print("clamp lock", n)
    if n:
        write_no_bom(gpath, gt2)
        ast.parse(gt2)

# --- Verify ---
sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if any(x in mod for x in ("generalized_video_director", "dspy_orchestrator", "dspy_optimizer")):
        del sys.modules[mod]

import generalized_video_director as gvd
import dspy_orchestrator as o
import dspy_optimizer as optm

sig = gvd.director_signature_class()
assert sig is not None
outs = list(sig.output_fields.keys())
print("outputs", outs)
assert "denoise" not in outs
assert "end_prompt" not in outs
assert "start_prompt" in outs and "video_prompt" in outs
assert "cfg_scale" in outs and "step_count" in outs
instr = gvd.DIRECTOR_SIGNATURE_INSTRUCTIONS
print("instr has FLUX", "FLUX" in instr, "has MiniMax video", "video_prompt" in instr and "MiniMax" in instr)
assert "start_prompt" in instr and "video_prompt" in instr
assert "denoise" in instr.lower()

hp = gvd.clamp_director_hparams({"cfg_scale": 4.0, "step_count": 24, "denoise": 0.2})
print("clamped", hp)
assert float(hp.get("denoise", 1.0)) == 1.0

g = o.build_minimax_graph(
    "a",
    "b",
    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 24},
    negative="x",
    prefix="dspy_opt/s",
)
print("node3", {k: g["3"]["inputs"][k] for k in ("denoise", "cfg", "steps")})
assert float(g["3"]["inputs"]["denoise"]) == 1.0
assert float(g["3"]["inputs"]["cfg"]) == 4.0
assert int(g["3"]["inputs"]["steps"]) == 24

src = inspect.getsource(optm.extract_eval_frames)
assert "max(8, min(12" in src
assert "count: int = 10" in src
print("framecap OK")

live = []
for comp in [ROOT / "models" / "dspy_compiled", BASE / "models" / "dspy_compiled"]:
    if comp.exists():
        live += [p.name for p in comp.glob("*.json")]
print("live compiled", live)
assert not live
print("ALL PHASES VERIFIED")
