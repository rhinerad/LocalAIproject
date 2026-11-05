from pathlib import Path
p = Path("local_agent/tools.py")
text = p.read_text(encoding="utf-8")
start = text.find('    "render_story_image_batch": (render_story_image_batch,')
end = text.find('    "prepare_storyboard_review":')
if start < 0 or end < 0:
    raise SystemExit(f"bounds not found start={start} end={end}")
replacement = (
    '    "render_story_image_batch": (render_story_image_batch, '
    "'PREFERRED for CLIP still sheets: sequentially render a list of stills "
    "(start then await complete/fail then next) so one tool call finishes many "
    "frames without MAX_TOOL_HOPS exhaustion or owns-the-backend dead-ends. "
    "Pass jobs as a list of story/prompt objects (optional model_profile). "
    "Flux sheet => model_profile/default realpro_flux. On full success marks "
    "this chat pending stills review — present outputs and WAIT; do not start "
    "video until approve_story_stills after explicit operator approval.'),\n"
    '    "await_story_image_job": (await_story_image_job, '
    "'Poll story_image_job_status until complete, failed, or timeout "
    "(default 900s). Pass story/pid/log from render_story_image; optional "
    "poll_s/timeout_s. Use after a single render_story_image when not using "
    "the batch tool.'),\n"
    '    "story_image_job_status": (story_image_job_status, '
    "'Read-only: check whether a render_story_image job is still running and "
    "whether it produced a real file. Pass story/pid/log. Detects stale PIDs "
    "when the owner was released / process is dead. Poll again if state is "
    "running.'),\n"
    '    "present_story_stills_for_review": (present_story_stills_for_review, '
    "'Mark generated story stills as pending operator review for this chat. "
    "Call after stills exist (batch does this automatically). Video tools "
    "stay blocked until approve_story_stills. Bare continue is not "
    "approval.'),\n"
    '    "approve_story_stills": (approve_story_stills, '
    "'Unlock video for this chat after the operator explicitly approves the "
    "stills (looks good / approved / go ahead with video). Requires "
    "operator_confirmed=true. Do not call on bare continue.'),\n"
    '    "story_stills_review_status": (story_stills_review_status, '
    "'Read-only: pending_review / approved / none for this chat story stills "
    "review gate.'),\n"
)
text = text[:start] + replacement + text[end:]
p.write_text(text, encoding="utf-8")
compile(text, str(p), "exec")
print("syntax OK")
