#!/usr/bin/env python3
"""Pick one audio reference per speaking character, for MiniMax H3 ref2va.

WHAT CHANGED, 2026-08-13 (v2) -- read this before trusting v1 output
--------------------------------------------------------------------
Version 1 selected the window straight from `dialogue_timing` in
story_config.json and checked it with mean dB. Both were wrong, and listening
caught it:

  * `dialogue_timing` is when a line is SCRIPTED to be spoken, not when speech
    actually occurs. H3 comes in early by a median of about a second and often
    does not fill the window. So the cut was mostly not-speech.
  * Mean dB cannot tell speech from noise. Kent's reference came from `14D`, the
    driving clip. It measured -19.9 dB mean and 100% "voiced" under a -35 dB
    silence gate, because road and engine noise never drops below the gate. It
    was 14.6 seconds of car interior with about 2 seconds of dialogue in it.

v2 ignores the scripted window as evidence and searches the actual audio, using
work/speech_density.py, which scores speech by spectral band ratio rather than
level.

THE SELECTION RULE
------------------
One reference = **one contiguous speaking passage from one take.** Never
stitched, never concatenated, never assembled from two spans. Splicing two
passages teaches the model an average of two deliveries, which is exactly the
drift the reference exists to prevent.

Selection happens in two steps, cheap filter first:

  1. **From the script.** Keep only clips where the character is the ONLY
     speaker, and where their scripted lines cover most of the clip's duration
     (SCRIPT_COVERAGE_MIN). A clip that is 13 seconds of one person talking is
     the right shape for a reference; a clip where they say four words at the
     end is not, no matter how clean those four words are. This is free -- it
     reads story_config.json and needs no audio.

  2. **From the audio.** Confirm the take actually contains a continuous
     speaking passage, using work/speech_density.py. The script says what was
     asked for; only the audio says what H3 delivered, and the two differ often
     enough that step 1 alone is not safe.

"Contiguous" allows natural breath and sentence pauses -- a passage may contain
internal gaps up to MAX_GAP -- but the whole span must still be at least
MIN_DENSITY speech. Otherwise "two words, six seconds of nothing, two more
words" would qualify.

Candidates are examined in story order. The first appearance that actually
contains a reliable contiguous passage is the voice lock for that character.
"First appearance" therefore means the first delivered, usable H3 performance,
not merely the first scripted line: a silent, noisy, mixed-voice, or gibberish
take cannot become the canonical reference just because it occurs earlier.

**If no existing take qualifies, no reference is invented.** The character is
written to `needs_story_bootstrap`. Their first actual story clip with enough
assigned speech is rendered at 0.2 MP as part of the soundtrack pass, using the
real story dialogue. Once that full soundtrack is accepted, the delivered line
becomes the canonical reference. Purpose-built filler dialogue is prohibited.

Writes outputs/equal_shares/voice_reference_map.json and, with --extract, the
cut WAVs. Existing WAVs are moved aside to *.superseded_v1.wav rather than
overwritten.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
VOX_SPECS = EQ / "voice_reference_vox_specs.json"
VOX_MANIFEST = EQ / "vox_reference_manifest.json"
BOOTSTRAP_PLAN = EQ / "story_voice_bootstrap_plan.json"

_spec = importlib.util.spec_from_file_location("speech_density", ROOT / "work" / "speech_density.py")
sd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sd)

# H3 reference audio window
MAX_SECONDS = 15.0
MIN_SECONDS = 2.0
GOOD_SECONDS = 6.0      # below this, flag the reference as thin
MAX_GAP = 1.0           # longest internal pause still counted as one passage
MIN_DENSITY = 0.60      # a passage must be at least this much actual speech
SCRIPT_COVERAGE_MIN = 0.55   # scripted speech must fill this much of the clip
DUMMY_SPEECH_SECONDS = 13.0  # target speech in a purpose-built VOX reference clip
EDGE_PAD = 0.15         # breathing room either side of the final cut


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def speaker_of(line: str) -> str:
    head = line.split("“")[0].split('"')[0]
    return re.split(r"[,:]", head)[0].strip()


def map_path(win_path: str, mounts: dict[str, str]) -> Path | None:
    if not win_path:
        return None
    p = win_path.replace("\\", "/")
    for win_prefix, local in mounts.items():
        wp = win_prefix.replace("\\", "/")
        if p.lower().startswith(wp.lower()):
            return Path(local) / p[len(wp):].lstrip("/")
    cand = Path(win_path)
    return cand if cand.exists() else None


def load_mounts() -> dict[str, str]:
    raw = os.environ.get("VOICE_REF_MOUNTS", "")
    out: dict[str, str] = {}
    for pair in filter(None, raw.split(";")):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k] = v
    return out


def best_passage(path: Path, lo: float | None, hi: float | None) -> tuple[float, float, float] | None:
    """Longest contiguous speaking passage in [lo, hi], or in the whole file."""
    try:
        a, sr = sd.read_audio(path)
    except Exception:
        return None
    if lo is not None:
        a = a[max(0, int(lo * sr)):int(hi * sr)] if hi else a[max(0, int(lo * sr)):]
    mask, hop = sd.speech_mask(a, sr)
    s, e, dens = sd.longest_passage(mask, hop, MAX_GAP, MIN_DENSITY, MIN_SECONDS)
    if e - s < MIN_SECONDS:
        return None
    off = lo if lo is not None else 0.0
    if e - s > MAX_SECONDS:            # keep the opening of an over-long passage
        e = s + MAX_SECONDS
    return off + s, off + e, dens


def build(cfg: dict, manifest: dict, accepted: set[str], mounts: dict[str, str], verbose: bool):
    clips = cfg["clips"]
    order = {c["id"]: c.get("sequence_order", i) for i, c in enumerate(clips)}

    # Step 1 -- the free filter, straight from the script.
    by_char: dict[str, list[dict]] = {}
    for clip in clips:
        timing = clip.get("dialogue_timing") or []
        if not timing:
            continue
        here = {speaker_of(d["line"]) for d in timing}
        if len(here) != 1:
            continue                      # sole speaker only, no exceptions
        name = here.pop()
        dur = float(clip.get("duration") or 0) or 1.0
        spoken = sum(float(d["end"]) - float(d["start"]) for d in timing)
        rec = manifest.get("clips", {}).get(clip["id"], {})
        src = rec.get("comfy_source") or ""
        by_char.setdefault(name, []).append({
            "clip": clip["id"],
            "sequence_order": order.get(clip["id"], 0),
            "duration": dur,
            "scripted_seconds": round(spoken, 1),
            "coverage": round(spoken / dur, 3),
            "accepted": clip["id"] in accepted,
            "comfy_source": src,
            "local": map_path(src, mounts),
        })

    chosen: dict[str, dict] = {}
    needs_dummy: dict[str, dict] = {}
    all_speakers = set()
    for clip in clips:
        for d in clip.get("dialogue_timing") or []:
            all_speakers.add(speaker_of(d["line"]))

    for name in sorted(all_speakers):
        options = by_char.get(name, [])
        # Step 1: keep clips that are mostly this character talking.
        strong = [o for o in options if o["coverage"] >= SCRIPT_COVERAGE_MIN]
        # User rule: the first qualifying appearance establishes the voice.
        # Do not prefer a later clip just because it has marginally higher
        # scripted coverage. Audio evidence below still has veto power.
        strong.sort(key=lambda o: o["sequence_order"])

        if verbose:
            print(f'  {name}: {len(options)} solo clips, '
                  f'{len(strong)} with coverage >= {SCRIPT_COVERAGE_MIN:.0%}')
            for o in options:
                print(f'      {o["clip"]:5s} {o["scripted_seconds"]:5.1f}s of '
                      f'{o["duration"]:4.1f}s = {o["coverage"]:4.0%}'
                      + ('  <= candidate' if o in strong else ''))

        # Step 2: confirm the audio actually delivers.
        picked = None
        for o in strong:
            if not o["local"] or not o["local"].exists():
                continue
            r = best_passage(o["local"], None, None)
            if verbose:
                got = f'{r[1]-r[0]:.1f}s @{r[0]:.1f} density {r[2]:.0%}' if r else "no passage"
                print(f'      audio {o["clip"]:5s} -> {got}')
            if r and (r[1] - r[0]) >= GOOD_SECONDS:
                picked = (o, r)
                break                     # first reliable appearance wins
        if picked is None:
            best_cov = max((o["coverage"] for o in options), default=0.0)
            needs_dummy[name] = {
                "reason": ("no solo clip with enough speech"
                           if strong else
                           "no solo clip where this character talks for most of the shot"),
                "solo_clips": [o["clip"] for o in options],
                "best_script_coverage": round(best_cov, 3),
                "candidates_passing_script_filter": [o["clip"] for o in strong],
                "dummy_seconds_needed": DUMMY_SPEECH_SECONDS,
            }
            continue

        o, (s, e, dens) = picked
        chosen[name] = {
            "character": name,
            "slug": slug(name),
            "source_clip": o["clip"],
            "comfy_source": o["comfy_source"],
            "extract_start": round(float(max(0.0, s - EDGE_PAD)), 2),
            "extract_end": round(float(e + EDGE_PAD), 2),
            "speech_seconds": round(float(e - s), 2),
            "speech_density": round(float(dens), 3),
            "script_coverage": o["coverage"],
            "contiguous_single_take": True,
            "sole_speaker_in_clip": True,
            "visually_accepted": bool(o["accepted"]),
            "thin": bool((e - s) < GOOD_SECONDS),
            "solo_clips_available": len(options),
            "ref_wav": f"voices/{slug(name)}/h3_voice_ref.wav",
        }

    return chosen, needs_dummy


def write_vox_specs(needs: dict, cfg: dict, out_path: Path) -> None:
    """Emit render specs for characters that need a purpose-built voice clip.

    These never enter story_config.json, manifest.json, or the completion audit.
    Their only job is to make one character talk continuously for long enough to
    cut a reference from.
    """
    clips = {c["id"]: c for c in cfg["clips"]}
    specs = []
    for name, info in sorted(needs.items()):
        first = info["solo_clips"][0] if info["solo_clips"] else None
        anchor = (clips.get(first) or {}).get("first_frame")
        if not anchor:
            for c in cfg["clips"]:
                if any(speaker_of(d["line"]) == name for d in c.get("dialogue_timing") or []):
                    anchor = c.get("first_frame")
                    break
        specs.append({
            "id": f"VOX_{slug(name).upper()}_REF",
            "character": name,
            "slug": slug(name),
            "purpose": "voice reference only — never enters the edit",
            "duration": 15.0,
            "frames": 362,
            "first_frame": anchor,
            "last_frame": None,
            "megapixels": 0.2,
            "steps": 20,
            "target_speech_seconds": info["dummy_seconds_needed"],
            "output_dir": f"story/VOX_{slug(name).upper()}_REF/",
            "prompt_requirements": [
                "Exactly one person in frame, the named character, locked-off camera.",
                f"They speak continuously from 1 s to {1 + info['dummy_seconds_needed']:.0f} s "
                "with no gap longer than half a second.",
                "Write fresh filler dialogue in that character's register — never film "
                "dialogue, so a leaked clip is obviously not part of the story.",
                "Cover a spread of vowels, plosives, sibilants and nasals.",
                "Nobody else speaks, mutters, or moves their lips at any point.",
                "No music. Quiet ambience only.",
                "Judge on audio alone: continuous speech, one voice, no music. "
                "Gibberish words are fine — this is a timbre reference.",
            ],
        })
    out_path.write_text(json.dumps({
        "note": "Voice-reference dummy clips. Not part of the film.",
        "never_add_to": ["story_config.json", "manifest.json", "completion audit"],
        "clips": specs,
    }, indent=2), encoding="utf8")


def build_story_bootstrap_plan(needs: dict, cfg: dict, chosen: dict) -> dict:
    """Map unresolved voices to real story clips, never invented dialogue."""
    ordered = sorted(cfg["clips"], key=lambda c: c.get("sequence_order", 0))
    characters: dict[str, dict] = {}
    for name in sorted(needs):
        candidates = []
        for clip in ordered:
            windows = []
            for row in clip.get("dialogue_timing") or []:
                if speaker_of(row["line"]) != name:
                    continue
                windows.append({
                    "start": float(row["start"]),
                    "end": float(row["end"]),
                    "line": row["line"],
                })
            if not windows:
                continue
            scripted = sum(x["end"] - x["start"] for x in windows)
            candidates.append({
                "clip": clip["id"],
                "sequence_order": clip.get("sequence_order", 0),
                "scripted_seconds": round(scripted, 2),
                "windows": windows,
                "all_speakers": list(dict.fromkeys(
                    speaker_of(x["line"])
                    for x in clip.get("dialogue_timing") or []
                )),
            })
        reliable = [x for x in candidates if x["scripted_seconds"] >= GOOD_SECONDS]
        minimally_usable = [x for x in candidates if x["scripted_seconds"] >= MIN_SECONDS]
        selected = reliable[0] if reliable else (minimally_usable[0] if minimally_usable else None)
        thin = bool(selected and selected["scripted_seconds"] < GOOD_SECONDS)
        characters[name] = {
            "character": name,
            "status": (
                "thin_story_bootstrap_requires_human_review" if thin else
                "awaiting_story_soundtrack" if selected else
                "human_review_needed"
            ),
            "source_clip": selected["clip"] if selected else None,
            "scripted_seconds": selected["scripted_seconds"] if selected else 0.0,
            "dialogue_windows": selected["windows"] if selected else [],
            "all_speakers_in_source": selected["all_speakers"] if selected else [],
            "candidate_clips": [x["clip"] for x in candidates],
            "reliable_target_seconds": GOOD_SECONDS,
            "minimum_usable_seconds": MIN_SECONDS,
            "thin_reference": thin,
            "selection_rule": (
                f"first actual story appearance with at least {GOOD_SECONDS:.1f}s of "
                f"assigned speech; if none exists, first minimally usable {MIN_SECONDS:.1f}s "
                "appearance is preserved but requires human voice review"
            ),
        }

    clips: list[dict] = []
    for clip in ordered:
        targets = [
            name for name, row in characters.items()
            if row.get("source_clip") == clip["id"]
        ]
        if not targets:
            continue
        speakers = list(dict.fromkeys(
            speaker_of(x["line"]) for x in clip.get("dialogue_timing") or []
        ))
        clips.append({
            "id": clip["id"],
            "sequence_order": clip.get("sequence_order", 0),
            "bootstrap_characters": targets,
            "speakers": speakers,
            "existing_reference_speakers": [x for x in speakers if x in chosen],
            "unresolved_dependencies": [
                x for x in speakers if x not in chosen and x not in targets
            ],
            "uses_actual_story_prompt": True,
            "uses_actual_story_dialogue": True,
        })

    return {
        "schema_version": 1,
        "policy": "first qualifying delivered MiniMax H3 story appearance",
        "render_stage": "0.2 MP full-quality non-Turbo MiniMax H3 soundtrack",
        "forbidden": [
            "invented dialogue",
            "purpose-built VOX clips",
            "filler speech",
            "non-story voice samples",
        ],
        "characters": characters,
        "clips": clips,
    }


def merge_story_bootstraps(chosen: dict, unresolved: dict, plan: dict,
                           verbose: bool, allow_provisional: bool = False) -> None:
    """Establish missing voices from actual-story soundtrack attempts.

    Accepted soundtracks remain the only canonical source. When the user has
    explicitly allowed generation to continue ahead of ear review, a pending
    candidate may also be extracted as a clearly marked *provisional* reference.
    That lets Stage 1 keep rendering without turning unknown audio into an
    acceptance decision. Stage 2 still requires 124 accepted soundtracks.
    """
    manifest_path = EQ / "audio_pass_manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as error:
        if verbose:
            print(f"  story bootstrap merge skipped: {error}")
        return

    for name, spec in plan.get("characters", {}).items():
        clip_id = spec.get("source_clip")
        if not clip_id:
            continue
        entry = manifest.get("clips", {}).get(clip_id, {})
        status = entry.get("status")
        provisional = False
        if status == "accepted":
            source = Path(entry.get("accepted_full_wav", ""))
        elif allow_provisional and status in {
            "needs_ear_review", "auto_pass_pending_continuity_review"
        }:
            attempts = entry.get("attempts") or []
            candidate = next(
                (
                    row.get("candidate_full_wav") for row in reversed(attempts)
                    if row.get("candidate_full_wav")
                    and row.get("status") in {
                        "needs_ear_review", "auto_pass_pending_continuity_review"
                    }
                ),
                "",
            )
            source = Path(candidate)
            provisional = True
        else:
            continue
        if not source.is_file():
            continue
        windows = spec.get("dialogue_windows") or []
        if not windows:
            continue
        lo = max(0.0, min(float(x["start"]) for x in windows) - 0.75)
        hi = max(float(x["end"]) for x in windows) + 0.50
        passage = best_passage(source, lo, hi)
        if not passage:
            if verbose:
                label = "provisional" if provisional else "accepted"
                print(f"  {name}: {label} {clip_id} has no usable passage in assigned window")
            continue
        start, end, density = passage
        seconds = end - start
        chosen[name] = {
            "character": name,
            "slug": slug(name),
            "source_clip": clip_id,
            "comfy_source": str(source),
            "extract_start": round(float(max(0.0, start - EDGE_PAD)), 2),
            "extract_end": round(float(end + EDGE_PAD), 2),
            "speech_seconds": round(float(seconds), 2),
            "speech_density": round(float(density), 3),
            "script_coverage": round(float(spec.get("scripted_seconds", 0)) /
                                     max(float(hi), 1.0), 3),
            "contiguous_single_take": True,
            "sole_speaker_in_clip": len(spec.get("all_speakers_in_source", [])) == 1,
            "source_is_accepted_story_soundtrack": not provisional,
            "audio_reviewed": not provisional,
            "provisional": provisional,
            "requires_ear_review": provisional,
            "generation_use_only_until_reviewed": provisional,
            "thin": bool(seconds < GOOD_SECONDS),
            "ref_wav": (
                f"voices/{slug(name)}/h3_voice_ref.provisional_{clip_id}.wav"
                if provisional else f"voices/{slug(name)}/h3_voice_ref.wav"
            ),
        }
        unresolved.pop(name, None)
        if verbose:
            label = "PROVISIONAL pending ear review" if provisional else "accepted"
            print(f"  story bootstrap {name}: {seconds:.1f}s from {label} {clip_id}")


def merge_reviewed_vox_references(chosen: dict, needs_dummy: dict, verbose: bool) -> None:
    """Merge audio-reviewed VOX takes without adding them to the story manifest.

    The VOX renderer performs the spectral speech-duration gate, but one-voice
    and no-music are ear checks. A take is eligible here only after its manifest
    has ``audio_only_review: passed``. This prevents a measurement from being
    mistaken for human acceptance.
    """
    if not VOX_SPECS.exists() or not VOX_MANIFEST.exists():
        return
    try:
        specs = {
            row["id"]: row
            for row in json.loads(VOX_SPECS.read_text(encoding="utf-8"))["clips"]
        }
        manifest = json.loads(VOX_MANIFEST.read_text(encoding="utf-8"))
    except Exception as error:
        if verbose:
            print(f"  VOX merge skipped: {error}")
        return

    for clip_id, entry in manifest.get("clips", {}).items():
        spec = specs.get(clip_id)
        if not spec or entry.get("status") != "metric_pass":
            continue
        if str(entry.get("audio_only_review", "")).lower() != "passed":
            if verbose:
                print(f"  VOX {clip_id}: metrics pass; awaiting one-voice/no-music ear check")
            continue
        video = Path(entry.get("video", ""))
        if not video.is_file():
            if verbose:
                print(f"  VOX {clip_id}: reviewed video is missing: {video}")
            continue
        passage = best_passage(video, None, None)
        if not passage:
            if verbose:
                print(f"  VOX {clip_id}: no qualifying speech passage")
            continue
        start, end, density = passage
        if end - start < GOOD_SECONDS or density < 0.70:
            if verbose:
                print(f"  VOX {clip_id}: passage below gate ({end-start:.1f}s at {density:.0%})")
            continue

        name = spec["character"]
        chosen[name] = {
            "character": name,
            "slug": spec["slug"],
            "source_clip": clip_id,
            "comfy_source": str(video),
            "extract_start": round(float(max(0.0, start - EDGE_PAD)), 2),
            "extract_end": round(float(end + EDGE_PAD), 2),
            "speech_seconds": round(float(end - start), 2),
            "speech_density": round(float(density), 3),
            "script_coverage": round(float(spec.get("target_speech_seconds", 13.0)) / 15.0, 3),
            "contiguous_single_take": True,
            "sole_speaker_in_clip": True,
            "visually_accepted": False,
            "audio_only_reviewed": True,
            "thin": False,
            "solo_clips_available": 0,
            "ref_wav": f"voices/{spec['slug']}/h3_voice_ref.wav",
        }
        needs_dummy.pop(name, None)
        if verbose:
            print(f"  VOX {clip_id}: merged {end-start:.1f}s at {density:.0%}")


def extract(chosen: dict, mounts: dict[str, str]) -> None:
    for name, rec in sorted(chosen.items()):
        src = map_path(rec["comfy_source"], mounts)
        if not src or not src.exists():
            print(f"  SKIP {name}: take not found")
            continue
        if rec.get("provisional"):
            source_tag = re.sub(
                r"[^A-Za-z0-9]+", "_", str(rec["source_clip"])
            ).strip("_")
            canonical = (
                EQ / "voices" / rec["slug"]
                / f"h3_voice_ref.provisional_{source_tag}.wav"
            )
        else:
            canonical = EQ / "voices" / rec["slug"] / "h3_voice_ref.wav"
        out = canonical
        out.parent.mkdir(parents=True, exist_ok=True)
        if canonical.exists():
            if rec.get("provisional") and canonical.stat().st_size > 0:
                print(f"  KEEP {name}: provisional story reference already exists: {canonical}")
                rec["ref_wav"] = canonical.relative_to(EQ).as_posix()
                continue
            # The user changed selection to first qualifying appearance. Keep
            # the established reference as evidence and write the new source to
            # a versioned sibling. The map below will point at the sibling.
            source_tag = re.sub(r"[^A-Za-z0-9]+", "_", str(rec["source_clip"])).strip("_")
            base = canonical.with_name(f"h3_voice_ref.first_{source_tag}.wav")
            out = base
            version = 2
            while out.exists() and out.stat().st_size == 0:
                out = canonical.with_name(f"h3_voice_ref.first_{source_tag}.v{version}.wav")
                version += 1
            if out.exists():
                print(f"  KEEP {name}: versioned first-appearance reference already exists: {out}")
                rec["ref_wav"] = out.relative_to(EQ).as_posix()
                continue
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
            "-ss", str(rec["extract_start"]), "-to", str(rec["extract_end"]),
            "-i", str(src), "-vn", "-ac", "1", "-ar", "44100",
            "-af", "loudnorm=I=-20:TP=-2:LRA=11", str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(f"  FAIL {name}: {r.stderr.strip()[:160]}")
        else:
            rec["ref_wav"] = out.relative_to(EQ).as_posix()
            print(f'  wrote {name:24s} {rec["speech_seconds"]:5.1f}s speech '
                  f'from {rec["source_clip"]}')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--allow-provisional-story-bootstraps", action="store_true",
        help=(
            "use pending actual-story soundtrack candidates as clearly marked "
            "generation-only voice references; never marks them accepted"
        ),
    )
    ap.add_argument("--out", default=str(EQ / "voice_reference_map.json"))
    args = ap.parse_args()

    mounts = load_mounts()
    cfg = json.loads((EQ / "story_config.json").read_text(encoding="utf8"))
    manifest = json.loads((EQ / "manifest.json").read_text(encoding="utf8"))
    audit = json.loads((EQ / "visual_audit.json").read_text(encoding="utf8"))
    accepted = set(audit.get("reviewed_pass") or [])

    chosen, unresolved = build(cfg, manifest, accepted, mounts, args.verbose)
    bootstrap_plan = build_story_bootstrap_plan(unresolved, cfg, chosen)
    merge_story_bootstraps(
        chosen, unresolved, bootstrap_plan, args.verbose,
        allow_provisional=args.allow_provisional_story_bootstraps,
    )
    bootstrap_plan = build_story_bootstrap_plan(unresolved, cfg, chosen)

    print(f"\n{'CHARACTER':24s} {'clip':>5} {'speech':>7} {'dens':>5} {'window':>13}  flag")
    for name, r in sorted(chosen.items(), key=lambda kv: -kv[1]["speech_seconds"]):
        flag = "THIN" if r["thin"] else ""
        if not r["sole_speaker_in_clip"]:
            flag = (flag + " shared-clip").strip()
        print(f'{name:24s} {r["source_clip"]:>5} {r["speech_seconds"]:6.1f}s '
              f'{r["speech_density"]:5.0%} '
              f'{r["extract_start"]:5.1f}-{r["extract_end"]:<6.1f} {flag}')
    if unresolved:
        print("\nNEED A REAL-STORY VOICE BOOTSTRAP — no accepted take has enough speech:")
        for name, row in sorted(bootstrap_plan["characters"].items()):
            print(f'  {name:24s} -> {row.get("source_clip") or "HUMAN REVIEW"} '
                  f'({row.get("scripted_seconds", 0):.1f}s assigned story speech)')

    good = sum(1 for r in chosen.values() if not r["thin"])
    print(f"\n{good} solid (>={GOOD_SECONDS}s), {len(chosen)-good} thin, "
          f"{len(unresolved)} need a real-story bootstrap")

    if args.extract:
        print("\nextracting:")
        extract(chosen, mounts)

    payload = {
        "generated_by": "work/build_voice_reference_map.py v3",
        "method": "first qualifying appearance with a contiguous speaking passage found by work/speech_density.py",
        "rules": {
            "one_contiguous_passage_from_one_take": True,
            "never_concatenate": True,
            "max_internal_gap_seconds": MAX_GAP,
            "min_speech_density": MIN_DENSITY,
            "min_seconds": MIN_SECONDS,
            "good_seconds": GOOD_SECONDS,
            "max_seconds": MAX_SECONDS,
            "script_coverage_min": SCRIPT_COVERAGE_MIN,
            "sole_speaker_required_for_legacy_take_reuse": True,
            "story_bootstrap_may_use_multi_speaker_clip": True,
            "purpose_built_or_invented_dialogue": "prohibited",
            "candidate_order": "story order; first reliable delivered appearance wins",
            "scripted_windows_not_trusted": "H3 speaks early and rarely fills the window",
            "pending_story_audio_may_be_generation_only_provisional": bool(
                args.allow_provisional_story_bootstraps
            ),
        },
        "references": chosen,
        "provisional_references": sorted(
            name for name, row in chosen.items() if row.get("provisional")
        ),
        "needs_story_bootstrap": bootstrap_plan["characters"],
    }
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf8")
    print(f"wrote {args.out}")

    BOOTSTRAP_PLAN.write_text(json.dumps(bootstrap_plan, indent=2), encoding="utf8")
    print(f"wrote {BOOTSTRAP_PLAN}  ({len(bootstrap_plan['clips'])} real story clips)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
