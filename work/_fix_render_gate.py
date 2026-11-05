from pathlib import Path
import json
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
# Check image owner / recent outputs
owner = ROOT/"work"/"runtime"/"image_render_owner.json"
print("owner:", owner.read_text(encoding="utf-8") if owner.exists() else "missing")
# fix wants_explicit_render
p = ROOT/"local_agent"/"managed_prompt_pack.py"
t = p.read_text(encoding="utf-8")
old = '''def wants_explicit_render(text: str | None) -> bool:
    return bool(_EXPLICIT_RENDER_RE.search(str(text or "")))'''
new = '''def wants_explicit_render(text: str | None) -> bool:
    """True only for a short current-turn render ask — not pack assembly prose."""
    raw = str(text or "")
    # Large packs embed lines like "Generate the stills first..."; that is pack
    # content, not an operator instruction to start Comfy on this turn.
    if is_prompt_pack(raw) or len(raw) > 4000:
        return False
    return bool(_EXPLICIT_RENDER_RE.search(raw))'''
if old not in t:
    raise SystemExit("wants_explicit_render not found")
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
print("fixed wants_explicit_render")
