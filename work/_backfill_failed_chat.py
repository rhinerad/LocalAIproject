"""Backfill failed chat pack into managed_tasks so continue can resume without re-paste."""
from pathlib import Path
import json, sys
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
sys.path.insert(0, str(ROOT/"local_agent"))
import managed_prompt_pack
import agentic_state

cid = "be96946279cf480d"
chat = json.loads((ROOT/"local_agent"/"chats"/f"{cid}.json").read_text(encoding="utf-8"))
text = chat["messages"][0]["content"]
assert managed_prompt_pack.is_prompt_pack(text)
progress = managed_prompt_pack.ingest(cid, text, allow_render=False)
exported = managed_prompt_pack.export_all(cid, chunk_size=24)
# refresh agentic checkpoint so continue sees paths
state = agentic_state.begin_turn(cid, text)
print(json.dumps({
    "cid": cid,
    "clip_count": exported["clip_count"],
    "exported_count": exported["exported_count"],
    "remaining": exported["remaining"],
    "source_path": exported["source_path"],
    "output_dir": exported["output_dir"],
    "progress_path": exported["progress_path"],
    "allow_render": exported["allow_render"],
    "agentic_kind": (state or {}).get("kind"),
}, indent=2))
