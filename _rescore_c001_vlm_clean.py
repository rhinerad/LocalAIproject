from pathlib import Path
import json, sys

root = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "local_agent"))

import batch_run_backrooms_gvd as batch
import media_accuracy_gate as mag

ov = batch.load_clip_override("C001")
prog = batch.load_progress()
entry = (prog.get("clips") or {}).get("C001") or {}
video = Path(str(entry.get("video_path") or ""))
if not video.is_file():
    # fallback known path
    video = Path(r"A:\Users\rhine\ComfyUI-Shared\output\dspy_opt\gvd_br_c001_855bb0f0a1_00001_.mp4")
print("video", video, "exists", video.is_file())
print("override rule", ov.get("vlm_literal_rule"))

start = str(ov.get("start_prompt") or "")
video_p = str(ov.get("video_prompt") or "")
sys_p = mag.build_video_director_vlm_system_prompt(
    literal_mode=True, literal_rule=str(ov.get("vlm_literal_rule") or "")
)
usr_p = mag.build_vlm_user_prompt(
    start_prompt=start,
    video_prompt=video_p,
    literal_mode=True,
    expected_scene=str(ov.get("expected_scene") or start),
)
banned = ["backrooms", "liminal", "yellow wallpaper", "endless hallway", "endless corridor"]
blob = (sys_p + "\n" + usr_p).lower()
hit = [b for b in banned if b in blob]
print("banned hits in prompts:", hit)
assert not hit, hit
print("---SYSTEM---\n", sys_p[-500:])
print("---USER---\n", usr_p)

qa = batch.run_literal_vlm_qa(
    video,
    start_prompt=start,
    video_prompt=video_p,
    override=ov,
)
print("QA RESULT", json.dumps({k: qa.get(k) for k in ("pass", "text_video_alignment", "dump") if k in qa or True}, indent=2, default=str)[:500])
print("full keys", list(qa.keys()))
print("pass", qa.get("pass"), "tva", qa.get("text_video_alignment"))
parsed = qa.get("parsed") or {}
print("parsed scores", json.dumps(parsed, indent=2, default=str)[:2000])

# update progress vlm fields
prog.setdefault("clips", {})["C001"] = {
    **entry,
    "vlm_qa": {
        "pass": bool(qa.get("pass")),
        "text_video_alignment": qa.get("text_video_alignment"),
        "dump": qa.get("dump"),
        "rescored_clean_rubric": True,
    },
}
batch.save_progress(prog)
print("progress updated")
