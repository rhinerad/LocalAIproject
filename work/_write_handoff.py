from pathlib import Path
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")

# Append to current handoff
hp = ROOT/"docs"/"LOCAL_AGENT_CURRENT_HANDOFF_2026-09-06.md"
ht = hp.read_text(encoding="utf-8")
addon = '''

## 2026-09-07 — managed prompt-pack fix (r96)

Operator paste of the Backrooms Sitcom Audition Prompt Pack on chat
`be96946279cf480d` was mis-routed as `CAP_IMAGE` / `gpu_image` and attempted
`render_story_image_batch` with two invented frames. Fixed in
`CHANGELOG/2026-09-07b_managed_prompt_pack.md`:

- New `local_agent/managed_prompt_pack.py` + `CAP_CREATIVE` routing
- Deterministic ActionPlan ingest/export; durable progress under
  `local_agent/runtime/managed_tasks/<cid>/`
- Render tools blocked until an explicit short-turn render ask
- Live agent still needs restart to load `2026-09-07-managed-prompt-pack-r96`
'''
if "managed prompt-pack fix (r96)" not in ht:
    hp.write_text(ht.rstrip() + addon, encoding="utf-8")
    print("handoff appended")

# README brief section after product goal / specialist note
rp = ROOT/"local_agent"/"README.md"
rt = rp.read_text(encoding="utf-8")
needle = "Source citation, 2026-09-02:"
insert = '''Large creative/storyboard **prompt packs** (e.g. a 102-clip Backrooms audition
pack), 2026-09-07: classified as `CAP_CREATIVE`, not `CAP_IMAGE`. The harness
saves the full source under `runtime/managed_tasks/<conversation_id>/`, chunks
clips, writes per-clip outputs, and resumes on continue/proceed. It does **not**
start Comfy/`render_story_image*` from the pack paste alone — only after an
explicit short-turn render ask. Tools: `ingest_prompt_pack`,
`export_prompt_pack_outputs`, `prompt_pack_status`.

'''
if "prompt packs" not in rt[:3500]:
    if needle not in rt:
        raise SystemExit("README needle missing")
    rt = rt.replace(needle, insert + needle, 1)
    rp.write_text(rt, encoding="utf-8")
    print("README updated")
else:
    print("README already mentions packs")

# regenerate handoff status
import subprocess, sys
subprocess.check_call([sys.executable, str(ROOT/"scripts"/"write_handoff_status.py")], cwd=str(ROOT))
print("HANDOFF_STATUS regenerated")
