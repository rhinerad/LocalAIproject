from pathlib import Path
import json, re, ast

root = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
batch = root / "batch_run_backrooms_gvd.py"
gv_path = root / "generate_video.py"
ov = root / "clip_overrides" / "C001.json"

start = (
    "Authentic 1990s consumer camcorder found-footage sitcom audition tape, 4:3 frame, mild VHS softness, "
    "cool blue daylight streaming through window blinds, cluttered messy teenager bedroom, "
    "movie posters and band flyers taped on dark blue walls, laundry pile on a chair, desk lamp with a blue shade, "
    "soda cans and homework papers on a low table, patterned navy bedspread, ordinary carpet with a taped X mark, "
    "diegetic camcorder on a locked tripod Mode A, actor fully visible in third-person audition framing facing camera, "
    "busy lived-in teenage room with strong blue color and clutter"
)
video = (
    "Locked tripod camcorder, fixed frame inside a cluttered messy teenager bedroom with dark blue walls and movie posters. "
    "Cool blue daylight through window blinds, desk lamp glow. Quiet establishing beat, then the actor steps onto the taped mark on the carpet, "
    "faces camera, and says: Hi, thanks for having me. Practiced sitcom smile, one hand raised in a casual greeting. "
    "Natural room tone, slight mic hiss. Continuous single take, stay in this busy blue bedroom only"
)

data = {
    "id": "C001",
    "bypass_director": True,
    "literal_prompt": True,
    "bypass_director": True,
    "literal_prompt": True,
    "category": "sitcom_audition",
    "notes": "Pre-fall normal-world sitcom audition. Empty negative to avoid FLUX/MiniMax concept bleed. Strong blue cluttered bedroom anchors.",
    "start_prompt": start,
    "video_prompt": video,
    "start_prompt": start,
    "video_prompt": video,
    "negative_prompt": "",
    "cfg_scale": 5.5,
    "step_count": 28,
    "denoise": 1.0,
    "vlm_literal_rule": (
        "This image MUST depict a normal everyday living room or cluttered teenager bedroom with blue daylight and posters. "
        "If you detect ANY yellow wallpaper, liminal Backrooms aesthetics, or endless hallways, you MUST score this as a FAILURE."
    ),
    "expected_scene": (
        "Cluttered messy teenager bedroom, dark blue walls with movie posters, cool blue daylight through blinds, "
        "taped mark on carpet, actor facing locked tripod camcorder"
    ),
}
# rebuild without duplicate-key confusion
data = {
    "id": "C001",
    "bypass_director": True,
    "literal_prompt": True,
    "category": "sitcom_audition",
    "notes": "Pre-fall normal-world sitcom audition. Empty negative to avoid FLUX/MiniMax concept bleed. Strong blue cluttered bedroom anchors.",
    "start_prompt": start,
    "video_prompt": video,
    "negative_prompt": "",
    "cfg_scale": 5.5,
    "step_count": 28,
    "denoise": 1.0,
    "vlm_literal_rule": (
        "This image MUST depict a normal everyday living room or cluttered teenager bedroom with blue daylight and posters. "
        "If you detect ANY yellow wallpaper, liminal Backrooms aesthetics, or endless hallways, you MUST score this as a FAILURE."
    ),
    "expected_scene": (
        "Cluttered messy teenager bedroom, dark blue walls with movie posters, cool blue daylight through blinds, "
        "taped mark on carpet, actor facing locked tripod camcorder"
    ),
}
# aliases for whichever loader is live
data["bypass_director"] = True
data["literal_prompt"] = True
data["start_prompt"] = start
data["video_prompt"] = video
data["start_prompt"] = start
data["video_prompt"] = video

ov.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", ov)

bt = batch.read_text(encoding="utf-8")

new_neg = """    # Empty string is intentional (FLUX/MiniMax concept-bleed): do not fall through.
    if "negative_prompt" in override:
        neg = str(override.get("negative_prompt") or "")
    elif "negative_prompt" in override:
        neg = str(override.get("negative_prompt") or "")
    else:
        neg = str(clip.get("start_frame_negative") or clip.get("start_frame_negative") or "")
    neg = neg.strip()"""

if "Empty string is intentional" not in bt:
    m = re.search(r"    neg = str\(\n(?:        .*\n){1,6}    \)\.strip\(\)", bt)
    if not m:
        raise SystemExit("neg block not found:\n" + bt[bt.find("negative_prompt")-100:bt.find("negative_prompt")+400])
    print("replacing:\n", m.group(0))
    bt = bt[: m.start()] + new_neg + bt[m.end() :]
else:
    print("neg empty-fix already present")

# wants_literal — accept both naming schemes
m = re.search(r"def wants_literal\(override: dict\) -> bool:\n(?:    .*\n)+", bt)
new_wl = """def wants_literal(override: dict) -> bool:
    return bool(
        override.get("bypass_director")
        or override.get("literal_prompt")
        or override.get("bypass_director")
        or override.get("literal_prompt")
    )

"""
if m:
    bt = bt[: m.start()] + new_wl + bt[m.end() :]
    print("wants_literal updated")

# start/video alias reads inside pred_from_override
# Normalize to read all known keys
def ensure_alias(text: str, primary: str, alias: str) -> str:
    # if primary get exists and alias not already or'd next to it
    token = f'override.get("{primary}")'
    both = f'override.get("{primary}") or override.get("{alias}")'
    token_sq = f"override.get('{primary}')"
    both_sq = f"override.get('{primary}') or override.get('{alias}')"
    if both in text or both_sq in text:
        return text
    if token in text:
        return text.replace(token, both, 1)
    if token_sq in text:
        return text.replace(token_sq, both_sq, 1)
    return text

bt = ensure_alias(bt, "start_prompt", "start_prompt")
bt = ensure_alias(bt, "start_prompt", "start_prompt")
bt = ensure_alias(bt, "video_prompt", "video_prompt")
bt = ensure_alias(bt, "video_prompt", "video_prompt")

# Make pred carry literal flags — find SimpleNamespace / type construction
# Look for negative_prompt=neg in pred_from_override and add flags nearby
if "bypass_director=" not in bt[bt.find("def pred_from_override"): bt.find("def pred_from_override") + 2000]:
    # try inject after negative_prompt=neg,
    for needle in ["negative_prompt=neg,", "negative_prompt=neg"]:
        loc = bt.find(needle, bt.find("def pred_from_override"))
        if loc != -1 and loc < bt.find("def pred_from_override") + 2500:
            insert = (
                needle
                + "\n        bypass_director=bool(override.get('bypass_director') or override.get('bypass_director')),"
                + "\n        literal_prompt=bool(override.get('literal_prompt') or override.get('literal_prompt')),"
            )
            bt = bt[:loc] + insert + bt[loc + len(needle) :]
            print("injected literal flags on pred")
            break

batch.write_text(bt, encoding="utf-8")
ast.parse(bt)
print("batch AST OK")

# generate_video force empty neg
if gv_path.exists():
    gv = gv_path.read_text(encoding="utf-8")
    if "FORCE_EMPTY_NEGATIVE_FOR_LITERAL" not in gv:
        m = re.search(
            r"neg = str\(getattr\(pred, ['\"]negative_prompt['\"], ['\"]{2}\) or ['\"]{2}\)\.strip\(\)",
            gv,
        )
        if not m:
            # broader
            m = re.search(r"neg = str\(getattr\(pred, .*\n?", gv)
            print("broader match", m.group(0) if m else None)
            # line-based
            lines = gv.splitlines(True)
            for i, line in enumerate(lines):
                if "negative_prompt" in line and "getattr(pred" in line and "neg" in line:
                    print("line", i + 1, line)
                    inject = (
                        "    # FORCE_EMPTY_NEGATIVE_FOR_LITERAL: bypass/literal clips must not bleed concepts via CLIP negative\n"
                        "    if bool(getattr(pred, 'bypass_director', False) or getattr(pred, 'literal_prompt', False)\n"
                        "            or getattr(pred, 'bypass_director', False) or getattr(pred, 'literal_prompt', False)):\n"
                        "        neg = ''\n"
                    )
                    lines.insert(i + 1, inject)
                    gv = "".join(lines)
                    gv_path.write_text(gv, encoding="utf-8")
                    print("generate_video patched at line", i + 1)
                    break
            else:
                print("FAILED to patch generate_video")
        else:
            inject = (
                m.group(0)
                + "\n    # FORCE_EMPTY_NEGATIVE_FOR_LITERAL: bypass/literal clips must not bleed concepts via CLIP negative\n"
                + "    if bool(getattr(pred, 'bypass_director', False) or getattr(pred, 'literal_prompt', False)\n"
                + "            or getattr(pred, 'bypass_director', False) or getattr(pred, 'literal_prompt', False)):\n"
                + "        neg = ''\n"
            )
            gv = gv[: m.start()] + inject + gv[m.end() :]
            gv_path.write_text(gv, encoding="utf-8")
            print("generate_video patched via regex")
    else:
        print("generate_video already patched")
    ast.parse(gv_path.read_text(encoding="utf-8"))
    print("generate_video AST OK")

# Verify banned tokens in Comfy-bound fields
banned = ["backrooms", "liminal", "yellow"]
gen = (data["start_prompt"] + " " + data["video_prompt"] + " " + data["negative_prompt"]).lower()
print("banned in gen fields:", [b for b in banned if b in gen])
print("neg repr:", repr(data["negative_prompt"]))
print("done")
