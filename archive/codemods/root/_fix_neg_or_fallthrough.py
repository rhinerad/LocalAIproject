from pathlib import Path
import re, ast

root = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
batch = root / "batch_run_backrooms_gvd.py"
gv = root / "generate_video.py"
orch = root / "local_agent" / "dspy_orchestrator.py"

bt = batch.read_text(encoding="utf-8")
old = """    neg = str(
        override.get('negative_prompt')
        or clip.get('start_frame_negative')
        or 'watermark, readable text, subtitles, liminal backrooms hallway'
    ).strip()"""
new = """    # Empty string is intentional — do NOT fall through via `or` (FLUX concept bleed).
    if 'negative_prompt' in override:
        neg = str(override.get('negative_prompt') if override.get('negative_prompt') is not None else '')
    elif 'negative_prompt' in override:
        neg = str(override.get('negative_prompt') if override.get('negative_prompt') is not None else '')
    else:
        neg = str(clip.get('start_frame_negative') or clip.get('start_frame_negative') or '')
    neg = neg.strip()
    # Literal / bypass clips: hard-empty negative for FLUX + MiniMax
    if bool(override.get('bypass_director') or override.get('literal_prompt')
            or override.get('bypass_director') or override.get('literal_prompt')):
        neg = ''"""

if old not in bt:
    # try double-quoted variant from file
    m = re.search(
        r"    neg = str\(\n        override\.get\([\"']negative_prompt[\"']\)\n        or clip\.get\([\"']start_frame_negative[\"']\)\n        or [\"']watermark, readable text, subtitles, liminal backrooms hallway[\"']\n    \)\.strip\(\)",
        bt,
    )
    if not m:
        raise SystemExit("old neg block not found:\n" + bt[bt.find("neg = str"):bt.find("neg = str")+350])
    bt = bt[:m.start()] + new + bt[m.end():]
    print("patched via regex")
else:
    bt = bt.replace(old, new)
    print("patched via exact")

batch.write_text(bt, encoding="utf-8")
ast.parse(bt)
print("batch AST OK")

# Ensure submit_comfy / generate_minimax forces empty when literal flags set
gvt = gv.read_text(encoding="utf-8")
# find submit_comfy and ensure neg forced before generate_minimax_clip
i = gvt.find("def submit_comfy")
print("submit_comfy at", i)
print(gvt[i:i+1600])

# Patch submit_comfy to force empty negative on the pred before orch call
if "FORCE_EMPTY_NEG_SUBMIT" not in gvt:
    # Insert after hp["denoise"] = 1.0 or before generate_minimax_clip
    needle = "video_path = orch.generate_minimax_clip(example, pred, hp)"
    if needle not in gvt:
        # alternate names
        m = re.search(r"video_path = orch\.generate_\w+\(example, pred, hp\)", gvt)
        if not m:
            raise SystemExit("submit call not found")
        needle = m.group(0)
    inject = """# FORCE_EMPTY_NEG_SUBMIT: literal/bypass clips — empty CLIP negative (no concept bleed)
    if bool(getattr(pred, 'bypass_director', False) or getattr(pred, 'literal_prompt', False)
            or getattr(pred, 'bypass_director', False) or getattr(pred, 'literal_prompt', False)):
        try:
            pred.negative_prompt = ''
        except Exception:
            pass
    """ + needle
    gvt = gvt.replace(needle, inject, 1)
    gv.write_text(gvt, encoding="utf-8")
    ast.parse(gvt)
    print("generate_video submit patched")
else:
    print("submit already patched")

# Dry-run import check: simulate pred_from_override with empty neg
import sys
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "local_agent"))
# import batch module
import importlib.util
spec = importlib.util.spec_from_file_location("batch_mod", batch)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ov = {
    "bypass_director": True,
    "literal_prompt": True,
    "start_prompt": "cool blue daylight cluttered messy teenager bedroom",
    "video_prompt": "actor steps onto taped mark",
    "negative_prompt": "",
}
clip = {"id": "C001", "start_frame_negative": "liminal backrooms hallway yellow wallpaper"}
pred, hp = mod.pred_from_override(ov, clip)
print("SIM neg=", repr(pred.negative_prompt))
assert pred.negative_prompt == "", repr(pred.negative_prompt)
print("SIM OK empty neg")
