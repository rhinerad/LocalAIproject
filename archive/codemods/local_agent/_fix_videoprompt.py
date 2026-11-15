from __future__ import annotations
import ast, re, sys, time, json, urllib.request
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
OUT = Path(r"A:\Users\rhine\.grok\long-running-background-tasks")
TS = time.strftime("%Y%m%dT%H%M%S")

opath = BASE / "dspy_orchestrator.py"
ot = opath.read_text(encoding="utf-8")
opath.with_name(opath.name + f".bak_videoprompt_{TS}").write_text(ot, encoding="utf-8")

# Fix _director_motion_prompt to prefer video_prompt
old = '''def _director_motion_prompt(pred: Any) -> str:
    """MiniMax motion text: pred.video_motion_prompt, then legacy positive."""
    return str(
        _field(pred, "video_motion_prompt")
'''
# More robust: replace the function body via regex
m = re.search(r"def _director_motion_prompt\([\s\S]*?\n(?=def )", ot)
assert m, "missing _director_motion_prompt"
print("OLD FN:\n", m.group(0))
new_fn = '''def _director_motion_prompt(pred: Any) -> str:
    """MiniMax motion text: pred.video_prompt (current), then legacy aliases."""
    return str(
        _field(pred, "video_prompt")
        or _field(pred, "video_motion_prompt")
        or _field(pred, "motion_prompt")
        or _field(pred, "positive_prompt")
        or ""
    ).strip()


'''
ot = ot[: m.start()] + new_fn + ot[m.end() :]

# Also fix curriculum gate that mentions video_motion_prompt only
ot = ot.replace(
    'reasons.append("video_motion_prompt is empty")',
    'reasons.append("video_prompt is empty")',
)
ot = ot.replace(
    'raise ValueError("video_motion_prompt is empty; MiniMax I2V skipped")',
    'raise ValueError("video_prompt is empty; MiniMax I2V skipped")',
)
ot = ot.replace(
    'error="start_prompt or video_motion_prompt is empty; skipped GPU"',
    'error="start_prompt or video_prompt is empty; skipped GPU"',
)

# Silence denoise fallback: force 1.0 in parse_director_hparams after parse
# Find parse_director_hparams function and ensure denoise always 1.0 in returned dict
if "def parse_director_hparams" in ot:
    # after building hparams dict, force denoise
    ot2, n = re.subn(
        r"(def parse_director_hparams\([\s\S]*?)(return hparams)",
        r'\1    hparams["denoise"] = 1.0  # FLUX Empty Latent lock\n    \2',
        ot,
        count=1,
    )
    print("parse denoise lock", n)
    ot = ot2

opath.write_text(ot, encoding="utf-8")
ast.parse(ot)
print("orch syntax OK")

# Quick unit: mock pred with video_prompt
sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if "dspy_orchestrator" in mod or "generalized_video_director" in mod:
        del sys.modules[mod]
import dspy_orchestrator as o

class P:
    start_prompt = "a yellow hallway with grain"
    video_prompt = "slow handheld dolly forward"
    negative_prompt = "blur"
    cfg_scale = 4.0
    step_count = 20.0

assert o._director_start_prompt(None, P()) == "a yellow hallway with grain"
assert o._director_motion_prompt(P()) == "slow handheld dolly forward"
print("prompt helpers OK")

# Confirm graph still flux2
g = o.build_minimax_graph(
    P().start_prompt,
    P().video_prompt,
    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 20},
    negative="blur",
    prefix="dspy_opt/flux2",
)
assert g["14"]["inputs"]["unet_name"] == "flux2_dev_fp8mixed.safetensors"
assert g["10"]["inputs"]["vae_name"] == "flux2-vae.safetensors"
assert g["20"]["inputs"]["first_frame"] == ["8", 0]
assert float(g["3"]["inputs"]["denoise"]) == 1.0
print("graph OK", g["14"]["inputs"]["unet_name"], g["10"]["inputs"]["vae_name"])
print("PATCH DONE")
