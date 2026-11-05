from pathlib import Path
import json, tempfile, sys
from unittest.mock import patch
root = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
sys.path.insert(0, str(root/"local_agent"))
import managed_prompt_pack, router, action_resolver, tools, remote_security

raw = Path(r"A:\Users\rhine\.codex\attachments\7a6a1cac-a5cb-4e78-8ad4-beab1bea0e7a\pasted-text.txt").read_text(encoding="utf-8")
idx = raw.find("# Backrooms Sitcom Audition Prompt Pack")
text = raw[idx:] if idx >= 0 else raw
# strip any trailing non-pack UI if present after double blank + agent lines
cut = text.find("\nagent ")
if cut > 0:
    text = text[:cut]
print("len", len(text))
print("is_pack", managed_prompt_pack.is_prompt_pack(text))
print("capability", router.classify_capability(text))
clips = managed_prompt_pack.parse_clips(text)
print("parsed_clips", len(clips), "first", clips[0]["id"] if clips else None, "last", clips[-1]["id"] if clips else None)

with tempfile.TemporaryDirectory() as td:
    with patch.object(managed_prompt_pack, "DIR", Path(td)):
        cid = "verifybackrooms1"
        plan = action_resolver.classify(
            text, [{"role":"user","content":text}], cid,
            pending_calibration_path_fn=lambda *_: None,
            specialist_scope=False,
        )
        print("plan", plan.intent, [s[0] for s in plan.steps])
        ctx = remote_security.ToolContext(source="desktop", conversation_id=cid)
        ingest = json.loads(tools.call("ingest_prompt_pack", {"text": text}, context=ctx))
        print("clips", ingest["clip_count"], "allow_render", ingest["allow_render"])
        print("source", ingest["source_path"])
        exported = json.loads(tools.call("export_prompt_pack_outputs", {"chunk_size": 24}, context=ctx))
        print("exported", exported["exported_count"], "remaining", exported["remaining"], "status", exported["status"])
        print("output_dir", exported["output_dir"])
        blocked = tools.call("render_story_image_batch", {
            "jobs":[{"story":"C001","prompt":"Static wide view"}],
            "__conversation_id": cid,
        }, context=ctx)
        print("render_blocked", blocked[:160])
        plan2 = action_resolver.classify(
            "continue", [{"role":"user","content":"continue"}], cid,
            pending_calibration_path_fn=lambda *_: None,
            specialist_scope=False,
        )
        print("continue_plan", plan2.intent, [s[0] for s in plan2.steps])
