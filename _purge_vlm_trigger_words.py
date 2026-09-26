from pathlib import Path
import json, re, ast

root = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
gate = root / "local_agent" / "media_accuracy_gate.py"
batch = root / "batch_run_backrooms_gvd.py"
ov_path = root / "clip_overrides" / "C001.json"

t = gate.read_text(encoding="utf-8")

# Replace build_video_director_vlm_system_prompt entirely with positive-only version
old_sys = '''def build_video_director_vlm_system_prompt(
    *,
    literal_mode: bool = False,
    literal_rule: str | None = None,
) -> str:
    """VLM system prompt with optional clip-specific hard rule.

    When literal_mode is True (bypass_director / literal_prompt overrides),
    inject a highest-priority rule so the judge cannot rubber-stamp a global
    Backrooms aesthetic prior.
    """
    base = VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT
    if not literal_mode:
        return base
    rule = (literal_rule or "").strip() or (
        "This image MUST depict a normal, everyday living room/bedroom. "
        "If you detect ANY yellow wallpaper, liminal Backrooms aesthetics, "
        "or endless hallways, you MUST score this as a FAILURE."
    )
    return (
        base
        + "\\n\\n=== CLIP-SPECIFIC OVERRIDE (HIGHEST PRIORITY) ===\\n"
        + rule
        + "\\nIf this override conflicts with any Backrooms/liminal prior, the override WINS.\\n"
        + "On failure set text_video_alignment <= 0.10 and say so in the rationale.\\n"
    )'''

new_sys = '''def build_video_director_vlm_system_prompt(
    *,
    literal_mode: bool = False,
    literal_rule: str | None = None,
) -> str:
    """VLM system prompt with optional clip-specific hard rule.

    When literal_mode is True (bypass_director / literal_prompt overrides),
    inject a highest-priority *positive* verification requirement. Do not name
    rejected aesthetics — naming them primes the VLM to hallucinate them.
    """
    base = VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT
    if not literal_mode:
        return base
    rule = (literal_rule or "").strip() or (
        "VERIFICATION REQUIREMENT: This clip depicts a normal residential room "
        "(bedroom or living room) with blue walls and domestic furniture. "
        "Verify that domestic items (bed, posters, windows, furniture) are clearly visible. "
        "Score text_video_alignment high only when those domestic cues are present."
    )
    return (
        base
        + "\\n\\n=== CLIP-SPECIFIC OVERRIDE (HIGHEST PRIORITY) ===\\n"
        + rule
        + "\\nDescribe only what is visible. Prefer positive scene confirmation over listing absences.\\n"
        + "If the required domestic residential cues are missing, set text_video_alignment <= 0.10 "
        + "and say which expected domestic items are absent.\\n"
    )'''

# Flexible match on parameter names (literal_mode vs literal_mode etc)
m = re.search(
    r"def build_video_director_vlm_system_prompt\([\s\S]*?\n(?=def )",
    t,
)
if not m:
    raise SystemExit("system builder not found")
print("replacing system builder len", len(m.group(0)))
t = t[: m.start()] + new_sys + "\n\n" + t[m.end() :]

m2 = re.search(
    r"def build_vlm_user_prompt\([\s\S]*?\n(?=def )",
    t,
)
if not m2:
    raise SystemExit("user builder not found")
print("old user builder:\n", m2.group(0)[:900])

new_user = '''def build_vlm_user_prompt(
    *,
    start_prompt: str,
    video_prompt: str,
    literal_mode: bool = False,
    expected_scene: str | None = None,
) -> str:
    parts = [
        f"START_FRAME_BASELINE: {start_prompt}",
        f"VIDEO_MOTION_PROMPT: {video_prompt}",
    ]
    if literal_mode:
        detail = (expected_scene or start_prompt or "").strip()[:800]
        parts.append(
            "VERIFICATION_FOCUS: Confirm a normal residential interior "
            "(bedroom or living room) with blue walls, daylight from a window, "
            "and visible domestic items such as a bed, posters, desk/lamp, and ordinary furniture."
        )
        if detail:
            parts.append(f"EXPECTED_SCENE_DETAIL: {detail}")
        parts.append(
            "SCORING_HINT: Give text_video_alignment >= 0.90 when the frames clearly show "
            "those domestic residential cues matching START_FRAME_BASELINE and VIDEO_MOTION_PROMPT. "
            "If those domestic cues are missing, score text_video_alignment <= 0.10 and name what is absent."
        )
    return "\\n".join(parts)


'''

t = t[: m2.start()] + new_user + t[m2.end() :]
gate.write_text(t, encoding="utf-8")
ast.parse(t)
print("gate AST OK")

# Purge trigger words from builders' emitted strings (sanity)
emitted = t[t.find("def build_video_director_vlm_system_prompt"): t.find("def parse_video_director_scores")]
banned = ["backrooms", "liminal", "yellow wallpaper", "endless hallway", "endless corridor"]
low = emitted.lower()
print("banned still in builders:", [b for b in banned if b in low])

# Update C001 override rule to positive-only
ov = json.loads(ov_path.read_text(encoding="utf-8"))
ov["vlm_literal_rule"] = (
    "VERIFICATION REQUIREMENT: This clip depicts a normal residential room "
    "(bedroom/living room) with blue walls and domestic furniture. "
    "Verify that domestic items (bed, posters, windows, furniture) are clearly visible."
)
# keep expected_scene positive (already is)
ov_path.write_text(json.dumps(ov, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("updated C001 vlm_literal_rule")

# Purge batch hardcoded C001_LITERAL_VLM_RULE if present
if batch.exists():
    bt = batch.read_text(encoding="utf-8")
    if "C001_LITERAL_VLM_RULE" in bt or "yellow wallpaper" in bt.lower() or "backrooms" in bt.lower():
        # replace constant if any
        m = re.search(r"C001_LITERAL_VLM_RULE\s*=\s*\([\s\S]*?\)\n", bt)
        if m:
            bt = bt[: m.start()] + (
                "C001_LITERAL_VLM_RULE = (\n"
                '    "VERIFICATION REQUIREMENT: This clip depicts a normal residential room "\n'
                '    "(bedroom/living room) with blue walls and domestic furniture. "\n'
                '    "Verify that domestic items (bed, posters, windows, furniture) are clearly visible."\n'
                ")\n"
            ) + bt[m.end() :]
            batch.write_text(bt, encoding="utf-8")
            ast.parse(bt)
            print("batch C001_LITERAL_VLM_RULE updated")
        else:
            # show offending lines
            for i, line in enumerate(bt.splitlines(), 1):
                ll = line.lower()
                if any(b in ll for b in banned):
                    print(f"batch {i}: {line[:140]}")
    else:
        print("batch clean of trigger words")

# Reconstruct prompts and assert clean
import sys
sys.path.insert(0, str(root / "local_agent"))
import importlib
import media_accuracy_gate as mag
importlib.reload(mag)
sys_p = mag.build_video_director_vlm_system_prompt(
    literal_mode=True, literal_rule=ov["vlm_literal_rule"]
)
usr_p = mag.build_vlm_user_prompt(
    start_prompt=ov.get("start_prompt") or "",
    video_prompt=ov.get("video_prompt") or "",
    literal_mode=True,
    expected_scene=ov.get("expected_scene"),
)
blob = (sys_p + "\n" + usr_p).lower()
print("--- SYSTEM ---")
print(sys_p)
print("--- USER ---")
print(usr_p)
print("banned in rebuilt prompts:", [b for b in banned if b in blob])
# also check base constant
print("banned in BASE system:", [b for b in banned if b in mag.VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT.lower()])
