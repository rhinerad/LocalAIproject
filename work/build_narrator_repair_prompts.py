#!/usr/bin/env python3
"""Build versioned Narrator retries from the user's proven prompt set.

The supplied prompt blocks are matched by their actual scripted words rather
than assumed numeric position. This matters because 00D2 is an inserted clip
and the supplied file contains ten, not eleven, prompt blocks. Missing matches
fall back to the already-prepared Stage-1 prompt. Every output receives the
single-performance reference isolation lock.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import build_audio_pass_prompts as builder

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
DEFAULT_SOURCE = Path(
    r"A:\Users\rhine\.codex\attachments\00e794b0-ef45-46f7-b468-62596454e529\pasted-text.txt"
)
DEFAULT_OUTPUT = PROJECT / "prompts_audio_pass_narrator_repair_v2"
NARRATOR_IDS = (
    "00A", "00B", "00C", "00D", "00D2", "00E", "00F", "00G",
    "00H", "00I", "00J", "00K", "00L", "00M", "00N", "00O",
)


def clean(text: str) -> str:
    replacements = {
        "â€œ": '"', "â€": '"', "â€™": "'", "â€”": "—",
        "â€“": "–", "â€¦": "…", "\r\n": "\n",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.strip()


def split_blocks(text: str) -> list[str]:
    starts = list(re.finditer(r'(?m)^"One continuous unbroken take\.', text))
    blocks: list[str] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = clean(text[match.start():end])
        if block.startswith('"'):
            block = block[1:]
        if block.rstrip().endswith('"'):
            block = block.rstrip()[:-1]
        blocks.append(block.strip())
    return blocks


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", clean(text).casefold())


def expected_text(clip: dict) -> str:
    dialogue = builder.parse_dialogue(clip, {})
    return " ".join(row["text"] for row in dialogue)


def overlap_score(expected: str, block: str) -> float:
    wanted = Counter(words(expected))
    available = Counter(words(block))
    if not wanted:
        return 0.0
    matched = sum(min(count, available[token]) for token, count in wanted.items())
    return matched / sum(wanted.values())


def ensure_lock(text: str) -> str:
    if "VOCAL MIX — SINGLE NARRATOR PERFORMANCE ONLY" in text:
        return text.rstrip() + "\n"
    marker = "\n\nCAMERA\n"
    lock = "\n\n" + builder.NARRATOR_SINGLE_LAYER_LOCK + "\n"
    if marker in text:
        return text.replace(marker, lock + marker, 1).rstrip() + "\n"
    return text.rstrip() + lock + "\n"


def dialogue_is_single_copy(clip: dict, prompt: str) -> bool:
    haystack = " ".join(words(prompt))
    for row in builder.parse_dialogue(clip, {}):
        needle = " ".join(words(row["text"]))
        if not needle or haystack.count(needle) != 1:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"proven prompt source is missing: {source}")
    blocks = split_blocks(source.read_text(encoding="utf-8-sig"))
    if not blocks:
        raise SystemExit("no proven prompt blocks found")

    story = json.loads((PROJECT / "story_config.json").read_text(encoding="utf-8-sig"))
    clips = {row["id"]: row for row in story["clips"]}
    vmap = json.loads(
        (PROJECT / "voice_reference_map.json").read_text(encoding="utf-8-sig")
    )

    candidates = [cid for cid in NARRATOR_IDS if cid in clips]
    scored: list[tuple[float, int, str]] = []
    for block_index, block in enumerate(blocks):
        for cid in candidates:
            scored.append((overlap_score(expected_text(clips[cid]), block), block_index, cid))
    mapping: dict[str, int] = {}
    used_blocks: set[int] = set()
    for score, block_index, cid in sorted(scored, reverse=True):
        if score < 0.55 or cid in mapping or block_index in used_blocks:
            continue
        mapping[cid] = block_index
        used_blocks.add(block_index)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "supplied_prompt_blocks": len(blocks),
        "policy": "proven visual prompt plus canonical dialogue and single-layer Narrator lock",
        "clips": {},
    }
    for cid in candidates:
        if cid in mapping:
            block_index = mapping[cid]
            prompt, speakers = builder.build_one(clips[cid], blocks[block_index], vmap)
            provenance = f"supplied_proven_block_{block_index + 1}"
            if not dialogue_is_single_copy(clips[cid], prompt):
                standard = PROJECT / "prompts_audio_pass" / f"{cid}.txt"
                prompt = standard.read_text(encoding="utf-8")
                provenance += "_fallback_due_duplicate_dialogue_in_source"
        else:
            standard = PROJECT / "prompts_audio_pass" / f"{cid}.txt"
            prompt = standard.read_text(encoding="utf-8")
            speakers = ["Narrator"]
            provenance = "existing_stage1_prompt_no_supplied_dialogue_match"
        prompt = ensure_lock(prompt)
        if not dialogue_is_single_copy(clips[cid], prompt):
            raise RuntimeError(f"{cid}: repair prompt does not contain each line exactly once")
        path = output / f"{cid}.txt"
        path.write_text(prompt, encoding="utf-8")
        report["clips"][cid] = {
            "prompt": str(path),
            "source": provenance,
            "speakers": speakers,
            "single_layer_lock": True,
            "expected_dialogue": expected_text(clips[cid]),
        }

    report["unmatched_supplied_blocks"] = [
        index + 1 for index in range(len(blocks)) if index not in used_blocks
    ]
    (output / "_repair_manifest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({
        "output_dir": str(output),
        "supplied_blocks": len(blocks),
        "matched": {cid: index + 1 for cid, index in sorted(mapping.items())},
        "fallback": [cid for cid in candidates if cid not in mapping],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
