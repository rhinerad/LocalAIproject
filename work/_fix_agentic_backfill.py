from pathlib import Path
import json, sys, time
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
sys.path.insert(0, str(ROOT/"local_agent"))
import managed_prompt_pack
from atomic_io import atomic_write_text

cid = "be96946279cf480d"
progress = managed_prompt_pack.load_progress(cid)
assert progress and progress["clip_count"] == 102
state = {
    "version": 1,
    "conversation_id": cid,
    "goal": f"Managed prompt pack: {progress.get('title')} ({progress.get('clip_count')} clips). Source: {progress.get('source_path')}",
    "status": "active",
    "kind": "prompt_pack",
    "plan": [
        {"id": 1, "title": "Persist full prompt-pack source as managed artifact", "status": "completed"},
        {"id": 2, "title": "Chunk clips and write durable progress", "status": "completed"},
        {"id": 3, "title": "Export per-clip output files to the pack folder", "status": "completed"},
        {"id": 4, "title": "Resume from progress on continue/proceed (no re-paste)", "status": "completed"},
        {"id": 5, "title": "Do not render unless operator explicitly asks", "status": "pending"},
    ],
    "observations": [],
    "prompt_pack": {
        "source_path": progress.get("source_path"),
        "output_dir": progress.get("output_dir"),
        "progress_path": progress.get("progress_path"),
        "clip_count": progress.get("clip_count"),
        "allow_render": False,
    },
    "active_files": [
        {"path": progress.get("source_path"), "tool": "ingest_prompt_pack", "outcome": "observed"},
        {"path": progress.get("output_dir"), "tool": "export_prompt_pack_outputs", "outcome": "observed"},
        {"path": progress.get("progress_path"), "tool": "ingest_prompt_pack", "outcome": "observed"},
    ],
    "last_operator_request": "Backfill managed prompt pack from chat history (dry-run export only)",
    "updated": time.time(),
    "prior_tasks": [{
        "goal": "prior blocked CAP_IMAGE render attempt",
        "status": "superseded",
        "updated": time.time(),
        "superseded_at": time.time(),
    }],
}
path = ROOT/"local_agent"/"runtime"/"agentic_tasks"/f"{cid}.json"
atomic_write_text(path, json.dumps(state, indent=2, ensure_ascii=False))
print("wrote", path)
print("outputs sample", list((Path(progress['output_dir']).glob('C0*.md')))[:3])
print("index", (Path(progress['output_dir'])/"INDEX.json").exists())
