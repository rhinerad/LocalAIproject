from __future__ import annotations
import ast, inspect, re, sys, time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")

def read_no_bom(p: Path) -> str:
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8")

def write_no_bom(p: Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8"))

gpath = BASE / "generalized_video_director.py"
gt = read_no_bom(gpath)
# Show clamp function
m = re.search(r"def clamp_director_hparams\([\s\S]*?\n(?=def |\nclass )", gt)
print("--- clamp ---")
print(m.group(0) if m else "MISSING")
assert m
fn = m.group(0)
if 'out["denoise"] = 1.0' not in fn and "out['denoise'] = 1.0" not in fn:
    # insert before every return out
    fn2 = re.sub(
        r"(\n    return out\n)",
        '\n    out["denoise"] = 1.0  # FLUX Empty Latent lock — never learner-tunable\n\\1',
        fn,
        count=1,
    )
    # also if return { ... }
    if fn2 == fn:
        fn2 = fn.rstrip() + '\n    # unreachable fallback\n'
    gt = gt[: m.start()] + fn2 + gt[m.end() :]
    write_no_bom(gpath, gt)
    ast.parse(gt)
    print("clamp patched")
else:
    print("clamp already locked")

# Also bump DENOISE_RANGE to (1.0, 1.0) so any clamp to range stays at 1.0
gt = read_no_bom(gpath)
gt2, n = re.subn(
    r"DENOISE_RANGE\s*=\s*\([^)]*\)",
    "DENOISE_RANGE = (1.0, 1.0)  # FLUX Empty Latent: fixed full denoise",
    gt,
    count=1,
)
print("DENOISE_RANGE lock", n)
if n:
    write_no_bom(gpath, gt2)
    ast.parse(gt2)

sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if any(x in mod for x in ("generalized_video_director", "dspy_orchestrator", "dspy_optimizer")):
        del sys.modules[mod]

import generalized_video_director as gvd
import dspy_orchestrator as o
import dspy_optimizer as optm

sig = gvd.director_signature_class()
outs = list(sig.output_fields.keys())
print("outputs", outs)
assert outs == ["start_prompt", "video_prompt", "negative_prompt", "cfg_scale", "step_count"] or (
    "denoise" not in outs and "start_prompt" in outs and "video_prompt" in outs and "cfg_scale" in outs and "step_count" in outs
)

hp = gvd.clamp_director_hparams({"cfg_scale": 4.0, "step_count": 24, "denoise": 0.2})
print("clamped", hp)
assert float(hp["denoise"]) == 1.0

g = o.build_minimax_graph(
    "a", "b",
    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 24},
    negative="x", prefix="dspy_opt/s",
)
assert float(g["3"]["inputs"]["denoise"]) == 1.0
assert float(g["3"]["inputs"]["cfg"]) == 4.0
assert int(g["3"]["inputs"]["steps"]) == 24
print("node3 OK", g["3"]["inputs"]["denoise"], g["3"]["inputs"]["cfg"], g["3"]["inputs"]["steps"])

src = inspect.getsource(optm.extract_eval_frames)
assert "max(8, min(12" in src
print("framecap OK")

live = []
for comp in [ROOT / "models" / "dspy_compiled", BASE / "models" / "dspy_compiled"]:
    if comp.exists():
        for p in list(comp.glob("*.json")):
            bak = p.with_name(p.name + f".bak_wipe_{time.strftime('%Y%m%dT%H%M%S')}")
            p.rename(bak)
            live.append(str(bak))
print("wiped leftover", live)
print("VERIFY DONE")
