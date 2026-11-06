from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(
    r"A:\Users\rhine\.codex\attachments\7a6a1cac-a5cb-4e78-8ad4-beab1bea0e7a\pasted-text.txt"
)
DEFAULT_OUTPUT = REPO / "work" / "backrooms_sitcom_audition_prompt_pack.EDIT_THIS.txt"
DEFAULT_RAW_COPY = REPO / "work" / "backrooms_sitcom_audition_prompt_pack.RAW_SOURCE_COPY.txt"
DEFAULT_REPORT = REPO / "work" / "backrooms_sitcom_audition_prompt_pack.reorder_report.json"


CLIP_RE = re.compile(
    r"####\s+C(?P<num>\d{3}),\s*(?P<time>.*?)(?=\s+Start Frame:)"
    r"\s+Start Frame:\s*(?P<start>.*?)(?=\s+Last Frame:)"
    r"\s+Last Frame:\s*(?P<last>.*?)(?=\s+Video Prompt:)"
    r"\s+Video Prompt:\s*(?P<video>.*?)(?=\s+####\s+C\d{3},|\s+###\s+|\s+##\s+|\Z)",
    re.DOTALL,
)


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def duration_seconds(time_range: str) -> float:
    def parse_stamp(stamp: str) -> float:
        parts = [float(part) for part in stamp.strip().split(":")]
        if len(parts) == 2:
            return parts[0] * 60.0 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
        raise ValueError(f"Unsupported time stamp: {stamp!r}")

    left, right = time_range.split("-", 1)
    return max(0.0, parse_stamp(right) - parse_stamp(left))


def tag_dialogue(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        spoken = match.group(1).strip()
        if not spoken:
            return match.group(0)
        return f"<d>[English] {spoken}</d>"

    return re.sub(r'"([^"\n]+)"', repl, text)


def section(text: str, start_heading: str, end_heading: str | None = None) -> str:
    start = text.find(start_heading)
    if start < 0:
        return ""
    start += len(start_heading)
    if end_heading is None:
        return compact(text[start:])
    end = text.find(end_heading, start)
    if end < 0:
        return compact(text[start:])
    return compact(text[start:end])


def parse_clips(text: str) -> OrderedDict[str, dict[str, str]]:
    # The source intentionally has original C069-C102 and a revised C069-C102.
    # Last occurrence wins so the revised second half supersedes the old one.
    clips: OrderedDict[str, dict[str, str]] = OrderedDict()
    for match in CLIP_RE.finditer(text):
        num = match.group("num")
        clips[num] = {
            "clip": f"C{num}",
            "time": compact(match.group("time")),
            "start": compact(match.group("start")),
            "last": compact(match.group("last")),
            "video": compact(match.group("video")),
        }

    ordered = OrderedDict()
    for index in range(1, 103):
        key = f"{index:03d}"
        if key not in clips:
            raise ValueError(f"Missing required clip C{key}")
        ordered[key] = clips[key]
    return ordered


def build_output(source_text: str, source_path: Path, clips: OrderedDict[str, dict[str, str]]) -> str:
    master = section(source_text, "## Master Continuity Prompt", "## Negative Prompt")
    negative = section(source_text, "## Negative Prompt", "## Clean Shot-to-Shot Continuity Protocol")
    clean_protocol = section(source_text, "## Clean Shot-to-Shot Continuity Protocol", "## Character Bible")
    character_bible = section(source_text, "## Character Bible", "## Story Rules")
    story_rules = section(source_text, "## Story Rules", "## Clip Prompts")
    audio_direction = section(source_text, "## Audio Direction", "## Minimax Assembly Notes")
    assembly_notes = section(source_text, "## Minimax Assembly Notes", "## Revised Second Half")
    revised_lore = section(source_text, "### Lore Basis for the Conversation", "### C069,")
    dialogue_tone = section(source_text, "## Dialogue Tone for the New Half", "## Generation Notes for the Static Reset")
    static_reset = section(source_text, "## Generation Notes for the Static Reset", None)
    camcorder_pov_lock = (
        "Diegetic camcorder POV lock: the image must look like it was captured only by the story's physical "
        "consumer camcorder. During the audition, this means the tripod-mounted camcorder view. After the fall, "
        "this means the actor's handheld camcorder view from his real position, height, grip, stumble, and turn. "
        "Do not use an outside film camera, drone, gimbal, cinematic coverage, impossible reverse angle, selfie angle, "
        "third-person observer shot, or omniscient camera. The viewer is seeing through the character's camcorder."
    )
    backrooms_lora_path = (
        r"A:\Users\rhine\ComfyUI-Shared\models\loras\BacHal_(Background)*(SDXL)*(AD).safetensors"
    )
    backrooms_lora_rule = (
        f"For every SDXL still image where the character is inside the Backrooms / Level 0 yellow-room environment, "
        f"use the Backrooms SDXL LoRA at `{backrooms_lora_path}`. Apply it as an environment/background helper only: "
        "it should strengthen yellow wallpaper, damp carpet, fluorescent office maze geometry, and liminal room texture "
        "without changing the actor's identity, clothing, pose, face, or camcorder POV. Do not apply this LoRA to the "
        "ordinary apartment audition shots before the fall unless the frame has already entered the Backrooms."
    )

    lines: list[str] = []
    lines.append("# Backrooms Sitcom Audition Prompt Pack — SDXL Frames First")
    lines.append("")
    lines.append(f"Source file: `{source_path}`")
    lines.append(f"Rewritten: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(
        "This edited version front-loads every SDXL START FRAME and LAST FRAME image prompt first. "
        "The video generation prompts come only after all still-image prompts are complete."
    )
    lines.append("")
    lines.append("Authoritative continuity choice: clips C001-C068 come from the original sequence; "
                 "clips C069-C102 use the revised second half because the source says it supersedes the old C069-C102.")
    lines.append("")
    lines.append("Global camera rule:")
    lines.append("")
    lines.append(camcorder_pov_lock)
    lines.append("")
    lines.append("Global SDXL Backrooms LoRA rule:")
    lines.append("")
    lines.append(backrooms_lora_rule)
    lines.append("")
    lines.append("MiniMax video-prompt rule:")
    lines.append("")
    lines.append(
        "The video section uses MiniMax first-last-frame video format: the first line aligns Picture 1 to 0.00 seconds "
        "and Picture 2 to the final moment; the body then uses integrated_multimodal_description, overall_soundscape, "
        "and non_diegetic_music. Keep each clip as a single continuous camcorder shot unless the source explicitly "
        "requires a static cut, fall, or impact."
    )
    lines.append("")
    lines.append("## SECTION 1 — SDXL START/LAST FRAME IMAGE PROMPTS")
    lines.append("")
    lines.append(
        "Generate and review these still frames before animating. Each prompt is a static SDXL image prompt, "
        "not a motion prompt."
    )
    lines.append("")

    for key, clip in clips.items():
        filename_base = f"clip_{key}"
        for label, field, suffix in (
            ("START FRAME IMAGE", "start", "start"),
            ("LAST FRAME IMAGE", "last", "last"),
        ):
            lines.append(f"### {clip['clip']} — {label} — {clip['time']}")
            lines.append("")
            lines.append(f"Filename: `{filename_base}_{suffix}.png`")
            lines.append("")
            lines.append("Model target: SDXL still image")
            lines.append("")
            if int(key) >= 16:
                lines.append(f"Required Backrooms SDXL LoRA: `{backrooms_lora_path}`")
                lines.append("")
            lines.append("Positive prompt:")
            lines.append("")
            lines.append(
                f"{master} Static single-frame SDXL reference still, 4:3 found-footage composition, "
                f"clean readable handoff frame for image-to-video. {camcorder_pov_lock} "
                f"{backrooms_lora_rule if int(key) >= 16 else ''} {clip[field]} "
                "Preserve all character identity, clothing, camera defects, room geometry, lighting direction, "
                "screen direction, and Backrooms continuity exactly."
            )
            lines.append("")
            lines.append("Negative prompt:")
            lines.append("")
            lines.append(negative)
            lines.append("")
            lines.append("Continuity anchors:")
            lines.append("")
            lines.append(
                "Use the same actor, entity design if present, camcorder look, yellow Level 0 architecture, "
                "fluorescent lighting, damp carpet, and restrained horror-comedy tone established by the source pack."
            )
            lines.append("")

    lines.append("## SECTION 2 — VIDEO GENERATION PROMPTS")
    lines.append("")
    lines.append(
        "Use the still images from Section 1 as the supplied start and last frames. "
        "Each video prompt describes only motion, timing, performance, sound, dialogue, and continuity between those frames."
    )
    lines.append("")

    for key, clip in clips.items():
        filename_base = f"clip_{key}"
        duration = duration_seconds(clip["time"])
        tagged_video = tag_dialogue(clip["video"])
        lines.append(f"### {clip['clip']} — VIDEO PROMPT — {clip['time']}")
        lines.append("")
        lines.append(f"Uses start frame: `{filename_base}_start.png`")
        lines.append(f"Uses last frame: `{filename_base}_last.png`")
        lines.append("")
        lines.append("MiniMax first-last-frame prompt:")
        lines.append("")
        lines.append(
            "How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the "
            f"0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the {duration:.2f}-second "
            "mark of the target video."
        )
        lines.append("")
        lines.append(
            "integrated_multimodal_description: [Shot 1] Authentic 1990s consumer-camcorder found-footage, "
            "4:3 aspect ratio, mild VHS softness, autofocus hunting, exposure pumping, tape hiss, and practical "
            "fluorescent or household lighting. Picture 1 is the exact opening composition and Picture 2 is the exact "
            f"ending composition. {camcorder_pov_lock} Beginning from Picture 1, {tagged_video} "
            "The action develops continuously in one physical take with natural acceleration and deceleration, "
            "stable room geometry, stable actor identity, stable clothing, stable entity anatomy when present, "
            "and no unplanned cut or external camera angle. During the final 1.5 seconds, the motion settles cleanly "
            "into Picture 2."
        )
        lines.append("")
        lines.append(
            "overall_soundscape: Built-in camcorder microphone audio with steady tape hiss, room tone, fluorescent hum, "
            "footsteps, breath, fabric movement, carpet contact, camera handling noise, and the physical sounds implied "
            "by the visible action. Dialogue is synchronized to the visible speaker and remains short enough for the clip."
        )
        lines.append("")
        lines.append("non_diegetic_music: N/A")
        lines.append("")

    lines.append("## APPENDIX — GLOBAL CONTINUITY AND ASSEMBLY NOTES")
    lines.append("")
    lines.append("### Character Bible")
    lines.append("")
    lines.append(character_bible)
    lines.append("")
    lines.append("### Story Rules")
    lines.append("")
    lines.append(story_rules)
    lines.append("")
    if revised_lore:
        lines.append("### Revised Second Half Lore Basis")
        lines.append("")
        lines.append(revised_lore)
        lines.append("")
    if dialogue_tone:
        lines.append("### Dialogue Tone for the New Half")
        lines.append("")
        lines.append(dialogue_tone)
        lines.append("")
    if static_reset:
        lines.append("### Generation Notes for the Static Reset")
        lines.append("")
        lines.append(static_reset)
        lines.append("")
    lines.append("### Audio Direction")
    lines.append("")
    lines.append(audio_direction)
    lines.append("")
    lines.append("### Minimax Assembly Notes")
    lines.append("")
    lines.append(assembly_notes)
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-copy", type=Path, default=DEFAULT_RAW_COPY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    source_text = args.source.read_text(encoding="utf-8", errors="replace")
    clips = parse_clips(source_text)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_copy.write_text(source_text, encoding="utf-8")
    rewritten = build_output(source_text, args.source, clips)
    args.output.write_text(rewritten, encoding="utf-8", newline="\n")

    report = {
        "ok": True,
        "source": str(args.source),
        "output": str(args.output),
        "raw_copy": str(args.raw_copy),
        "clip_count": len(clips),
        "sdxl_start_frame_prompts": len(clips),
        "sdxl_last_frame_prompts": len(clips),
        "video_prompts": len(clips),
        "uses_revised_c069_c102": True,
        "backrooms_sdxl_lora_rule": r"A:\Users\rhine\ComfyUI-Shared\models\loras\BacHal_(Background)*(SDXL)*(AD).safetensors",
        "backrooms_sdxl_lora_applies_from_clip": "C016",
        "minimax_video_format": "FL2VA alignment line + integrated_multimodal_description + overall_soundscape + non_diegetic_music",
        "render_started": False,
    }
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
