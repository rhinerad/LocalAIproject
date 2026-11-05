#!/usr/bin/env python3
"""Rebuild the Omni-Reference soundtrack config from the current sources of truth.

`audio_pass_config_omni_v1.json` is what `work/render_audio_pass.py` actually
reads. It drifts every time something upstream changes, and a stale entry is
invisible until a render comes out wrong. This regenerates it so the renderer
always uses:

  prompts     outputs/equal_shares/prompts_native_r2v/<clip>.txt
              H3's native six-section R2V format. The older
              prompts_audio_pass_omni_v1/ set predates the official guides and
              lacks `retention_analysis`, which is what caused the doubled voice.

  voice refs  outputs/equal_shares/omni_voice_master_map.json
              Per-character master, by current path and checksum. The Narrator
              moved from omni_master_v1 to v2 on 2026-08-15 and the config still
              pointed at v1.

  duration    outputs/equal_shares/audio_pass_durations.json
              SHORTENED to fit the spoken line, then padded with digital silence
              at assembly. Every one of the 14 known-good takes is short this way.
              NOTE, corrected 2026-08-18: shortening is a precaution and a cost
              saving, NOT a cure for gibberish -- 4_`.mp4 is 56% silence and is
              clean. See docs/GOLDEN_REFERENCE/PROVEN_FACTS.md section 3.

`scripted_duration` and `scripted_frames` are carried alongside so the padding
step and the picture pass can always recover the original film timing.

**Picture is not affected.** `work/render_picture_pass.py` reads its duration
from story_config.json and strips any shortened value that reaches it. The film
keeps its original pacing.

Writes a timestamped backup before overwriting.
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"

CONFIG = EQ / "audio_pass_config_omni_v1.json"
DURATIONS = EQ / "audio_pass_durations.json"
MASTERS = EQ / "omni_voice_master_map.json"
NATIVE_PROMPTS = "prompts_native_r2v"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf8"))
    durations = {r["id"]: r for r in json.loads(DURATIONS.read_text(encoding="utf8"))["clips"]}
    masters = json.loads(MASTERS.read_text(encoding="utf8")).get("references", {})

    changed = {"prompt": 0, "voice": 0, "duration": 0}
    missing_prompt, missing_master = [], set()

    for entry in cfg.get("clips", []):
        cid = entry["id"]

        # --- prompt -------------------------------------------------------
        want = f"{NATIVE_PROMPTS}/{cid}.txt"
        if not (EQ / want).is_file():
            missing_prompt.append(cid)
        elif entry.get("prompt_file") != want:
            entry["prompt_file"] = want
            changed["prompt"] += 1

        # --- voice masters -------------------------------------------------
        for ref in entry.get("ref_audios", []):
            name = ref.get("character")
            m = masters.get(name)
            if not m:
                missing_master.add(name)
                continue
            if ref.get("wav") != m["ref_wav"] or ref.get("sha256") != m.get("sha256"):
                ref["wav"] = m["ref_wav"]
                ref["sha256"] = m.get("sha256")
                ref["seconds"] = m.get("seconds")
                ref["provisional"] = bool(m.get("provisional") or m.get("requires_ear_review"))
                changed["voice"] += 1

        # --- shortened render length ---------------------------------------
        d = durations.get(cid)
        if d and d.get("has_dialogue"):
            if (entry.get("duration") != d["audio_pass_seconds"]
                    or entry.get("frames") != d["audio_pass_frames"]):
                entry["scripted_duration"] = d["scripted_seconds"]
                entry["scripted_frames"] = d["scripted_frames"]
                entry["duration"] = d["audio_pass_seconds"]
                entry["frames"] = d["audio_pass_frames"]
                entry["pad_silence_seconds"] = d["pad_silence_seconds"]
                changed["duration"] += 1

    cfg["prompt_set"] = NATIVE_PROMPTS
    cfg["prompt_format"] = "MiniMax H3 native six-section R2V; see docs/H3_PROMPT_RULES.md"
    cfg["duration_policy"] = (
        "Soundtrack renders use the shortened `duration`/`frames` here so H3 cannot "
        "invent speech to fill an empty tail. Pad each accepted WAV back to "
        "`scripted_duration` with work/pad_accepted_soundtracks.py. Picture always "
        "renders `scripted_duration` from story_config.json."
    )
    cfg["synced_at"] = datetime.datetime.now().isoformat(timespec="seconds")

    print(f"prompt_file repointed to {NATIVE_PROMPTS}/ : {changed['prompt']}")
    print(f"voice master paths refreshed              : {changed['voice']}")
    print(f"render lengths shortened                  : {changed['duration']}")
    if missing_prompt:
        print(f"NO NATIVE PROMPT for                      : {missing_prompt}")
    if missing_master:
        print(f"characters with no voice master           : {sorted(missing_master)}")

    if args.check:
        print("\n--check: nothing written")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(CONFIG, CONFIG.with_name(f"{CONFIG.stem}.BACKUP_{stamp}.json"))
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf8")
    print(f"\nwrote {CONFIG.name} (backup kept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
