#!/usr/bin/env python3
"""Import the user-authored 30-scene/90-clip script into Equal Shares.

The importer preserves the supplied prose, dialogue windows, and audio notes,
then builds production-ready MiniMax H3 prompts and selects a restrained subset
of the already approved scene boundary images.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections import defaultdict
from pathlib import Path


NAME_MAP = {
    "alex": "Kent Brentwood",
    "elise": "Doris Lovelay",
    "julian": "Avery Renfield",
    "reverend": "Faith White",
    "priya": "Ryann Sally",
}

APPEARANCE = {
    "alex": "Kent Brentwood: the exact established main-character likeness, short dark receding hair, distinctive dark mustache, teal cardigan, cream shirt, charcoal trousers, worn brown shoes, canvas shoulder bag",
    "elise": "Doris Lovelay: the established elderly mother, soft lined face, white-gray curls, lavender robe, cream shawl, frail and warm",
    "julian": "Avery Renfield: the established financially secure older brother, clean-cut salt-and-pepper hair, navy coat or jacket, pale blue shirt",
    "reverend": "Faith White: the established Covenant teacher represented by the older gray-bearded figure in a sand-colored coat with a woven circular emblem",
    "priya": "Ryann Sally: the established South Asian solicitor and moderator, rectangular glasses, black hair in a low bun, burgundy suit, ivory blouse",
}

# Clips A and B use deliberately matched reference pairs.  Clip C uses one
# carefully chosen anchor so the model can perform the consequence/reaction
# without morphing between an insert and an unrelated wide tableau.
C_ANCHOR_BY_SCENE = {
    1: 5, 2: 4, 3: 5, 4: 4, 5: 5, 6: 4, 7: 5, 8: 4, 9: 5, 10: 6,
    11: 5, 12: 4, 13: 4, 14: 4, 15: 6, 16: 6, 17: 4, 18: 4, 19: 4, 20: 4,
    21: 4, 22: 4, 23: 4, 24: 6, 25: 4, 26: 6, 27: 4, 28: 4, 29: 6, 30: 6,
}

NEGATIVE_ADDITIONS = (
    "Turbo generation, Turbo LoRA, abrupt cut inside the clip, fast montage, "
    "unmotivated camera jump, reference-frame morph, rubbery face, identity drift, "
    "duplicate protagonist, costume change, glass barrier, glass gate, glass fence, "
    "deformed hands, extra fingers, lip-sync drift, subtitles, captions, watermark"
)


def roman_act(value: str) -> str:
    return {"I": "act_1", "II": "act_2", "III": "act_3"}.get(value, value.lower())


def parse_dialogue(lines: list[str], clip_id: str, duration: int) -> list[dict]:
    timings = []
    pattern = re.compile(r"^\[(\d+(?:\.\d+)?)s-(\d+(?:\.\d+)?)s\]\s*(.+)$")
    for line in lines:
        if not line.strip():
            continue
        match = pattern.match(line.strip())
        if not match:
            raise ValueError(f"{clip_id}: invalid dialogue timing line: {line}")
        start, end = float(match.group(1)), float(match.group(2))
        if end > duration:
            raise ValueError(f"{clip_id}: dialogue ends at {end:g}s in a {duration}s clip")
        timings.append({"start": start, "end": end, "line": match.group(3).strip()})
    return timings


def parse_script(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    scenes: list[dict] = []
    current_act = None
    current_scene = None
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        act_match = re.fullmatch(r"ACT\s+(I|II|III)", line)
        if act_match:
            current_act = roman_act(act_match.group(1))
            index += 1
            continue
        scene_match = re.fullmatch(r"SCENE\s+(\d+)\s+—\s+(.+)", line)
        if scene_match:
            current_scene = {
                "scene_number": int(scene_match.group(1)),
                "title": scene_match.group(2).strip(),
                "act": current_act,
                "clips": [],
            }
            scenes.append(current_scene)
            index += 1
            continue
        clip_match = re.fullmatch(r"CLIP\s+(\d{2}[A-C])", line)
        if not clip_match:
            index += 1
            continue
        if current_scene is None:
            raise ValueError(f"{clip_match.group(1)} appears before a scene heading")
        clip_id = clip_match.group(1)
        index += 1
        block = []
        while index < len(lines):
            candidate = lines[index].strip()
            if re.fullmatch(r"(?:ACT\s+(?:I|II|III)|SCENE\s+\d+\s+—\s+.+|CLIP\s+\d{2}[A-C])", candidate):
                break
            block.append(lines[index])
            index += 1
        block_text = "\n".join(block).strip()
        duration_match = re.search(
            r"Generation model \+ length:\s*Image-to-Video,\s*(\d+) seconds", block_text
        )
        prompt_match = re.search(
            r"Prompt:\s*\n(.*?)(?=\nDialogue timing:|\nAudio:)", block_text, re.S
        )
        audio_match = re.search(r"\nAudio:\s*(.*)$", block_text, re.S)
        if not duration_match or not prompt_match or not audio_match:
            raise ValueError(f"{clip_id}: incomplete generation, prompt, or audio section")
        duration = int(duration_match.group(1))
        dialogue_match = re.search(r"\nDialogue timing:\s*\n(.*?)(?=\nAudio:)", block_text, re.S)
        dialogue_lines = dialogue_match.group(1).splitlines() if dialogue_match else []
        current_scene["clips"].append(
            {
                "id": clip_id,
                "generation_model": "Image-to-Video",
                "duration": duration,
                "source_prompt": " ".join(prompt_match.group(1).split()),
                "dialogue_timing": parse_dialogue(dialogue_lines, clip_id, duration),
                "audio": " ".join(audio_match.group(1).split()),
            }
        )
    if len(scenes) != 30:
        raise ValueError(f"expected 30 scenes, found {len(scenes)}")
    clips = [clip for scene in scenes for clip in scene["clips"]]
    if len(clips) != 90:
        raise ValueError(f"expected 90 clips, found {len(clips)}")
    expected = [f"{scene:02d}{letter}" for scene in range(1, 31) for letter in "ABC"]
    actual = [clip["id"] for clip in clips]
    if actual != expected:
        raise ValueError("clip IDs are missing or out of order")
    return scenes


def legacy_scene_metadata(legacy_plan: dict) -> dict[int, dict]:
    grouped = defaultdict(list)
    for shot in legacy_plan["shots"]:
        match = re.search(r"scene_(\d{3})_", shot["scene"])
        if not match:
            raise ValueError(f"cannot identify scene number in {shot['scene']}")
        grouped[int(match.group(1))].append(shot)
    result = {}
    for scene_number, shots in grouped.items():
        first = min(shots, key=lambda item: item["sequence_order"])
        result[scene_number] = {
            "act": first["act"],
            "scene": first["scene"],
            "story_purpose": first["story_purpose"],
            "characters_present": first["characters_present"],
            "location": first["location"],
            "time_of_day": first.get("time_of_day", "continuous with scene"),
            "negative_prompt": first.get("negative_prompt_additions", ""),
        }
    return result


def select_references(project: Path, scene_number: int, letter: str) -> tuple[str, str | None, str]:
    folder = f"frames/scene_{scene_number:03d}"
    if letter == "A":
        first, last = f"{folder}/boundary_00.png", f"{folder}/boundary_01.png"
        reason = "matched opening wide pair; stable geography and modest camera movement"
    elif letter == "B":
        first, last = f"{folder}/boundary_02.png", f"{folder}/boundary_03.png"
        reason = "matched central-action pair; supports dialogue and a controlled push-in"
    else:
        anchor = C_ANCHOR_BY_SCENE[scene_number]
        first, last = f"{folder}/boundary_{anchor:02d}.png", None
        reason = "single consequence/reaction anchor; avoids morphing between insert and closing tableau"
    for relative in (first, last):
        if relative and not (project / relative).is_file():
            raise FileNotFoundError(project / relative)
    return first, last, reason


def dialogue_text(timings: list[dict]) -> str:
    if not timings:
        return "No dialogue. Preserve quiet natural performance."
    return " ".join(
        f"[{item['start']:g}s-{item['end']:g}s] {item['line']}" for item in timings
    )


def minimax_h3_frames(duration: int, fps: int = 24) -> int:
    base = max(5, round(duration * fps))
    return base + (5 - (base % 17)) % 17


def production_prompt(clip: dict, metadata: dict, duration: int, has_last_frame: bool) -> str:
    searchable = " ".join(
        [clip["source_prompt"]] + [item["line"] for item in clip["dialogue_timing"]]
    ).casefold()
    active_ids = [
        character_id
        for character_id in metadata["characters_present"]
        if any(part.casefold() in searchable for part in NAME_MAP[character_id].split())
    ]
    if active_ids:
        character_block = "; ".join(APPEARANCE[item] for item in active_ids)
    else:
        character_block = (
            "preserve only the people already visible in the selected reference frame; "
            "do not add a named cast member who is absent from that frame"
        )
    reference_block = (
        "<Picture 1> is the exact starting composition and <Picture 2> is the exact ending composition. "
        "Use both pictures as strict identity, wardrobe, prop, lighting, and location anchors; begin from Picture 1 "
        "and arrive naturally at Picture 2 without a cut or a reference-frame morph. "
        if has_last_frame else
        "<Picture 1> is the sole visual anchor. Preserve its identity, wardrobe, props, lighting, and location, "
        "then continue the action naturally without inventing a second endpoint composition. "
    )
    return (
        f"Standard MiniMax H3 image-to-video generation, full-quality non-Turbo, exactly {duration} seconds, 16:9. "
        "Create one continuous cinematic shot with no internal cuts. "
        f"{reference_block}"
        f"Character continuity: {character_block}. "
        f"Action and performance: {clip['source_prompt']} "
        "Movement must remain modest, physically plausible, and emotionally restrained. Preserve facial identity and "
        "screen direction; when two endpoint frames are supplied, transition with only a natural controlled camera move "
        "and coherent body motion. Nobody behaves cruelly or theatrically. "
        f"Dialogue timing and delivery: {dialogue_text(clip['dialogue_timing'])} "
        f"Synchronized audio plan: {clip['audio']} "
        "Do not render subtitles or visible dialogue text."
    )


def update_bible(bible: dict, total_seconds: int, source_name: str) -> dict:
    result = copy.deepcopy(bible)
    project = result["project"]
    project.update(
        {
            "logline": "After his mother dies in a universally kind society, indebted caregiver Kent Brentwood and his financially secure brother inherit equal shares, exposing how sincere niceness can preserve injustice.",
            "target_minutes": round(total_seconds / 60, 2),
            "target_seconds": total_seconds,
            "clip_seconds": "variable",
            "clip_duration_range_seconds": [6, 10],
            "target_shots": 90,
            "source_script": source_name,
            "ending_requirement": "Kent says 'This is unfair'; everyone responds kindly, but his eviction proceeds and the system remains unchanged.",
        }
    )
    replacements = {
        "Alex Vale": "Kent Brentwood",
        "Alex": "Kent",
        "Elise Vale": "Doris Lovelay",
        "Elise": "Doris",
        "Julian Vale": "Avery Renfield",
        "Julian": "Avery",
        "Reverend Soren": "Faith White",
        "Priya Sen": "Ryann Sally",
        "Priya": "Ryann",
    }
    for character in result["characters"]:
        old_name = character["name"]
        character["visual_reference_identity"] = old_name
        character["name"] = NAME_MAP[character["id"]]
        for key in ("role", "motivation"):
            value = character.get(key, "")
            for old, new in replacements.items():
                value = value.replace(old, new)
            character[key] = value
        if character["id"] == "alex":
            character["reference_images"] = ["references/alex_vale_master_v1.png"]
        else:
            character["reference_images"] = ["references/ensemble_cast_master_v1.png"]
    for location in result["locations"]:
        value = location["name"]
        for old, new in replacements.items():
            value = value.replace(old, new)
        location["name"] = value
    result["story_rules"]["dialogue_policy"] = (
        "Use the exact supplied dialogue and timing windows. Clip duration varies from six to ten seconds."
    )
    result["story_rules"]["generation_policy"] = (
        "Use standard MiniMax H3 full-quality sampling. Never use Turbo nodes or Turbo LoRAs. "
        "Use only the curated reference subset assigned to each clip."
    )
    return result


def validation_record(clip: dict) -> dict:
    checks = [
        "duration within configured tolerance",
        "identity and wardrobe match selected reference frame(s)",
        "no unexplained duplicate person or glass barrier",
        "single continuous shot with coherent motion and no internal cut",
        "required story action is visible",
        "no subtitles, watermark, or malformed text",
    ]
    if clip["dialogue_timing"]:
        checks.append("dialogue occurs inside every specified timing window with stable speaker identity")
    else:
        checks.append("no spoken dialogue")
    return {
        "schema_version": 2,
        "clip_id": clip["id"],
        "scene_number": clip["scene_number"],
        "duration": clip["duration"],
        "frames": clip["frames"],
        "first_frame": clip["first_frame"],
        "last_frame": clip.get("last_frame"),
        "dialogue_timing": clip["dialogue_timing"],
        "checks": checks,
        "retry_policy": {
            "identity_failure": "retry with same references and seed+1",
            "motion_or_morph_failure": "retry after removing last frame; keep first anchor",
            "dialogue_timing_failure": "retry with timing language moved to the start of the prompt",
            "duration_failure": "retry with unchanged duration and recalculated frames",
        },
    }


def markdown_script(scenes: list[dict], total_seconds: int) -> str:
    lines = [
        "# Equal Shares — Variable-Length MiniMax Production Script",
        "",
        f"90 clips · {total_seconds} seconds · {total_seconds // 60} minutes {total_seconds % 60} seconds",
        "",
        "Reference policy: matched pairs for clips A and B; one curated anchor for clip C to reduce morphing and choppiness.",
        "",
    ]
    current_act = None
    for scene in scenes:
        if scene["act"] != current_act:
            current_act = scene["act"]
            lines.extend([f"## {current_act.replace('_', ' ').title()}", ""])
        lines.extend([f"### Scene {scene['scene_number']:02d} — {scene['title'].title()}", ""])
        for clip in scene["clips"]:
            lines.extend(
                [
                    f"#### Clip {clip['id']} — {clip['duration']} seconds",
                    "",
                    clip["source_prompt"],
                    "",
                    f"References: `{clip['first_frame']}`" + (f" → `{clip['last_frame']}`" if clip.get("last_frame") else " (single anchor)"),
                    "",
                ]
            )
            if clip["dialogue_timing"]:
                lines.extend(["Dialogue timing:", ""])
                for item in clip["dialogue_timing"]:
                    lines.append(f"- {item['start']:g}s–{item['end']:g}s: {item['line']}")
                lines.append("")
            lines.extend([f"Audio: {clip['audio']}", ""])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    project = args.project.resolve()
    scenes = parse_script(source.read_text(encoding="utf-8-sig"))
    legacy_plan_path = project / "shot_plan_legacy_180shot.json"
    if not legacy_plan_path.is_file():
        legacy_plan_path = project / "shot_plan.json"
    legacy_plan = json.loads(legacy_plan_path.read_text(encoding="utf-8"))
    metadata_by_scene = legacy_scene_metadata(legacy_plan)
    legacy_bible_path = project / "story_bible_legacy_180shot.json"
    if not legacy_bible_path.is_file():
        legacy_bible_path = project / "story_bible.json"
    bible = json.loads(legacy_bible_path.read_text(encoding="utf-8"))
    source_structured = {"schema_version": 2, "source": source.name, "scenes": scenes}

    clips = []
    for scene in scenes:
        scene_number = scene["scene_number"]
        metadata = metadata_by_scene[scene_number]
        for clip in scene["clips"]:
            letter = clip["id"][-1]
            first_frame, last_frame, reference_reason = select_references(project, scene_number, letter)
            duration = int(clip["duration"])
            frames = minimax_h3_frames(duration)
            item = {
                **clip,
                "scene_number": scene_number,
                "scene_title": scene["title"],
                "act": scene["act"],
                "scene": metadata["scene"],
                "sequence_order": len(clips) + 1,
                "story_purpose": metadata["story_purpose"],
                "characters_present": metadata["characters_present"],
                "character_names": [NAME_MAP[key] for key in metadata["characters_present"]],
                "location": metadata["location"],
                "time_of_day": metadata["time_of_day"],
                "frames": frames,
                "fps": 24,
                "first_frame": first_frame,
                "last_frame": last_frame,
                "reference_selection_reason": reference_reason,
                "prompt": production_prompt(clip, metadata, duration, last_frame is not None),
                "negative_prompt": ", ".join(
                    value for value in (bible.get("global_negative_prompt", ""), metadata["negative_prompt"], NEGATIVE_ADDITIONS) if value
                ),
                "seed": 52000 + len(clips) + 1,
                "validation_plan": f"validation_90clip/clip_{clip['id']}.json",
            }
            clips.append(item)

    total_seconds = sum(item["duration"] for item in clips)
    story_bible = update_bible(bible, total_seconds, source.name)
    shot_plan = {
        "schema_version": 2,
        "source_script": source.name,
        "project": {
            "title": "Equal Shares",
            "clip_count": len(clips),
            "total_seconds": total_seconds,
            "runtime": f"{total_seconds // 60}:{total_seconds % 60:02d}",
            "duration_range_seconds": [min(item["duration"] for item in clips), max(item["duration"] for item in clips)],
            "generation_model": "MiniMax H3 Image-to-Video, full quality, non-Turbo",
        },
        "reference_policy": {
            "clip_A": "boundary 00 to boundary 01 matched pair",
            "clip_B": "boundary 02 to boundary 03 matched pair",
            "clip_C": "one curated boundary 04, 05, or 06 anchor; no forced end frame",
            "reason": "Use fewer, compositionally compatible anchors to reduce morphing and choppy motion.",
        },
        "clips": clips,
    }
    legacy_config_path = project / "story_config_legacy_180shot.json"
    if not legacy_config_path.is_file():
        legacy_config_path = project / "story_config.json"
    old_config = json.loads(legacy_config_path.read_text(encoding="utf-8"))
    story_config = {
        key: value
        for key, value in old_config.items()
        if key not in {"scenes", "clips", "frames", "duration"}
    }
    story_config.update(
        {
            "schema_version": 2,
            "project_dir": ".",
            "comfy_output_root": "A:/Users/rhine/ComfyUI-Shared/output",
            "comfy_input_root": "A:/Users/rhine/ComfyUI-Shared/input",
            "fps": 24,
            "frame_count_mode": "minimax_h3_24fps_17n_plus_5",
            "width": 1344,
            "height": 768,
            "required_models": [
                "diffusion_models/minimax_h3_ref2va_pruned_nvfp4.safetensors",
                "vae/minimax_h3_video_vae_fp16.safetensors",
                "vae/minimax_h3_audio_vae_fp32.safetensors",
                "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            ],
            "duration_tolerance": 1.0,
            "clips": [
                {
                    key: item[key]
                    for key in (
                        "id", "prompt", "negative_prompt", "first_frame", "last_frame",
                        "duration", "frames", "fps", "seed", "dialogue_timing", "audio",
                        "validation_plan",
                    )
                    if item.get(key) is not None
                }
                for item in clips
            ],
        }
    )

    validation_dir = project / "validation_90clip"
    validation_dir.mkdir(parents=True, exist_ok=True)
    for item in clips:
        (validation_dir / f"clip_{item['id']}.json").write_text(
            json.dumps(validation_record(item), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    (project / "source_clip_script.json").write_text(
        json.dumps(source_structured, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (project / "story_bible.json").write_text(
        json.dumps(story_bible, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (project / "shot_plan.json").write_text(
        json.dumps(shot_plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (project / "story_config.json").write_text(
        json.dumps(story_config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for scene in scenes:
        for clip in scene["clips"]:
            match = next(item for item in clips if item["id"] == clip["id"])
            clip.update(
                {
                    "first_frame": match["first_frame"],
                    "last_frame": match.get("last_frame"),
                }
            )
    (project / "SCRIPT_AND_PROMPTS.md").write_text(
        markdown_script(scenes, total_seconds), encoding="utf-8"
    )
    print(
        f"Imported {len(clips)} clips across {len(scenes)} scenes: "
        f"{total_seconds}s ({total_seconds // 60}:{total_seconds % 60:02d})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
