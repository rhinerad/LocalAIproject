from __future__ import annotations
import ast, json, re, sys, time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
opath = BASE / "dspy_orchestrator.py"
ot = opath.read_text(encoding="utf-8")

# Show signature output fields and prompt extraction sites
print("=== video_motion / start_prompt / video_prompt refs in orch ===")
for i, ln in enumerate(ot.splitlines(), 1):
    if any(k in ln for k in ("video_motion_prompt", "start_prompt", "video_prompt", "empty; skipped GPU", "skipped GPU")):
        print(f"{i}: {ln[:160]}")

gpath = BASE / "generalized_video_director.py"
gt = gpath.read_text(encoding="utf-8")
print("=== signature outputs in gvd ===")
m = re.search(r"class GeneralizedVideoDirectorSignature[\s\S]{0,2500}", gt)
print(m.group(0)[:2000] if m else "no sig")

# Find empty-prompt check
m = re.search(r".{0,200}skipped GPU.{0,200}", ot)
print("=== skip context ===")
print(m.group(0) if m else "none")
