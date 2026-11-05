#!/usr/bin/env python3
"""Static preflight for Stage-1 prompts before they reach MiniMax."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import build_audio_pass_prompts as builder

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"


def normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.casefold()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-dir", default=str(PROJECT / "prompts_audio_pass"))
    parser.add_argument("--clip", action="append")
    parser.add_argument("--only-unrendered", action="store_true")
    parser.add_argument("--require-narrator-lock", action="store_true")
    parser.add_argument("--json")
    args = parser.parse_args()

    prompt_dir = Path(args.prompt_dir)
    story = json.loads((PROJECT / "story_config.json").read_text(encoding="utf-8-sig"))
    audio = json.loads((PROJECT / "audio_pass_config.json").read_text(encoding="utf-8-sig"))
    manifest_path = PROJECT / "audio_pass_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.exists() else {"clips": {}}
    prepared = {row["id"]: row for row in audio["clips"]}
    wanted = set(args.clip or [])
    results = []

    for clip in sorted(story["clips"], key=lambda row: row.get("sequence_order", 0)):
        cid = clip["id"]
        if wanted and cid not in wanted:
            continue
        prior = manifest.get("clips", {}).get(cid, {})
        if args.only_unrendered and prior.get("attempts"):
            continue
        row = prepared.get(cid, {})
        errors: list[str] = []
        warnings: list[str] = []
        path = prompt_dir / f"{cid}.txt"
        if not path.is_file() and not row.get("prompt_file"):
            # Non-dialogue clips intentionally have no prompts_audio_pass file.
            # render_audio_pass adds its reference prefix to story_config.prompt
            # at submission time, so audit the same effective text here.
            text = (
                "AUDIO-FIRST REFERENCE JOBS\n"
                "ref_image_0 is the exact opening composition. Begin on it precisely.\n\n"
                + str(clip.get("prompt", ""))
            ).strip()
        elif not path.is_file():
            errors.append("missing prompt file")
            text = ""
        else:
            text = path.read_text(encoding="utf-8").strip()
        if text and "One continuous unbroken take." not in text:
            errors.append("missing continuous-take opening")
        if "turbo" in text.casefold():
            errors.append("Turbo appears in prompt")
        if text.count("REFERENCE JOBS") != 1:
            errors.append(f"REFERENCE JOBS count is {text.count('REFERENCE JOBS')}, expected 1")

        dialogue = builder.parse_dialogue(clip, {})
        for index, line in enumerate(dialogue, 1):
            needle = normalized(line["text"])
            count = normalized(text).count(needle) if needle else 0
            if count != 1:
                errors.append(f"dialogue line {index} occurs {count} times, expected once")
            if line["start"] < 0 or line["end"] > float(clip.get("duration") or 0):
                errors.append(f"dialogue line {index} falls outside clip duration")
            words_per_second = len(needle.split()) / max(0.1, line["end"] - line["start"])
            if words_per_second > 3.6:
                warnings.append(f"dialogue line {index} is dense at {words_per_second:.2f} words/s")
        if dialogue:
            for source_line in text.splitlines():
                if re.search(
                    r"\b(?:nobody|no one|no character)\s+speaks(?:\s+to\s+anybody)?\b",
                    source_line,
                    flags=re.I,
                ) and not any(
                    phrase in source_line.casefold()
                    for phrase in ("except where", "speaks after", "speaks before", "speaks until")
                ):
                    errors.append("dialogue contradicts a no-one-speaks instruction")
                    break
        if dialogue and "Nobody in frame speaks except where" not in text:
            errors.append("missing mouth/silent-character lock")

        refs = row.get("ref_audios", [])
        indices = [ref.get("index") for ref in refs]
        if indices != list(range(len(indices))):
            errors.append(f"reference indices are not compact: {indices}")
        ref_characters = {ref.get("character") for ref in refs}
        for speaker in row.get("speakers", []):
            if speaker not in ref_characters:
                errors.append(f"missing voice reference for {speaker}")
        for ref in refs:
            ref_path = PROJECT / str(ref.get("wav", ""))
            if not ref_path.is_file() or ref_path.stat().st_size == 0:
                errors.append(f"missing reference WAV for {ref.get('character')}: {ref_path}")
        for label in ("first_frame", "last_frame"):
            value = clip.get(label)
            if value and not (PROJECT / value).is_file():
                errors.append(f"missing {label}: {value}")
        if args.require_narrator_lock and "Narrator" in row.get("speakers", []):
            if "VOCAL MIX — SINGLE NARRATOR PERFORMANCE ONLY" not in text:
                errors.append("missing single-layer Narrator lock")

        results.append({
            "clip": cid,
            "prompt": str(path),
            "status": "fail" if errors else "pass",
            "errors": errors,
            "warnings": warnings,
        })

    payload = {
        "schema_version": 1,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "prompt_dir": str(prompt_dir),
        "only_unrendered": args.only_unrendered,
        "clips_checked": len(results),
        "failed": sum(row["status"] == "fail" for row in results),
        "warnings": sum(len(row["warnings"]) for row in results),
        "results": results,
    }
    output = Path(args.json) if args.json else PROJECT / "runtime" / "audio_prompt_audit_latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "clips_checked": payload["clips_checked"],
        "failed": payload["failed"],
        "warnings": payload["warnings"],
        "report": str(output),
        "failed_clips": [row["clip"] for row in results if row["status"] == "fail"],
    }, indent=2))
    return 2 if payload["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
