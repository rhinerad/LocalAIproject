#!/usr/bin/env python3
"""Backrooms exact-pack compile layer (no GPU).

Compiles EDITOR OVERRIDES into typed JobSettings, parses clips via
managed_prompt_pack, extracts structured dialogue, durations, canvas policy,
and records unresolved creative conflicts — never silently rewriting story.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "local_agent"))

from atomic_io import atomic_write_json  # noqa: E402

_FLUX_MARKERS = (
    "### 0. Flux",
    "still-image generator is Flux",
    "The still-image generator is Flux",
)
_TIME_RANGE_RE = re.compile(
    r"(?P<m1>\d+):(?P<s1>\d+)\s*[-–—]\s*(?P<m2>\d+):(?P<s2>\d+)"
)
_D_TAG_RE = re.compile(r"<d>\[English\]\s*(.*?)\s*</d>", re.I | re.S)
_SPEAKER_PRE_RE = re.compile(
    r"(?P<span>.{0,80}?)$",
    re.S,
)
_IMPROV_RE = re.compile(
    r"\bimprovise(?:d|s)?\b|\bimprovised\s+(?:sitcom\s+)?exchange\b|"
    r"\bimaginary\s+scene\s+partner\b",
    re.I,
)
_SPEECH_BEARING_RE = re.compile(
    r"\b(?:Actor|Entity|actor|entity)\s+(?:says|whispers|mutters|asks|repeats|voice)\b|"
    r"<d>\[English\]|"
    r"\ba\s+low,?\s+distorted\s+human\s+voice\s+says\b|"
    r"\bspoken\s+dialogue\b",
    re.I,
)
_SDXL_WEIGHT_RE = re.compile(r"\([^)]+:\d+(?:\.\d+)?\)|<\w+:\d+(?:\.\d+)?>")
_CLIP_ID_RE = re.compile(r"^C(\d+)$", re.I)


@dataclass
class JobSettings:
    still_backend: str = "flux"
    reject_sdxl: bool = True
    aspect: str = "4:3"
    aspect_ratio: str = "4:3"
    default_clip_duration_s: float = 10.0
    fps: int = 24
    require_all_stills_approved: bool = True
    native_minimax_voice: bool = True
    no_music: bool = True
    needs_canvas_qualification: bool = True
    canvas_policy: str = (
        "Resolution must be a qualified 4:3 Flux canvas. Do not invent untested "
        "WxH; needs_canvas_qualification=True until a supported canvas is proven."
    )
    override_resolution: str = (
        "EDITOR OVERRIDES Rule 0 Flux: still_backend=flux beats any SDXL model "
        "labels, SDXL LoRA paths (BacHal_...), and weighted SDXL prompt syntax "
        "in body text. Preserve source_* fields; do not load SDXL LoRA for Flux."
    )
    source_has_flux_override: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_flux_override(source: str) -> bool:
    raw = str(source or "")
    return any(m in raw for m in _FLUX_MARKERS) or bool(
        re.search(r"(?i)still-image\s+generator\s+is\s+Flux", raw)
    )


def compile_job_settings(source: str) -> JobSettings:
    """Parse EDITOR OVERRIDES into typed JobSettings (Flux highest priority)."""
    settings = JobSettings()
    settings.source_has_flux_override = detect_flux_override(source)
    if not settings.source_has_flux_override and "## EDITOR OVERRIDES" in (source or ""):
        # Pack title may still say Flux Frames First
        if re.search(r"(?i)\bFlux\s+Frames\s+First\b", source or ""):
            settings.source_has_flux_override = True
    if settings.source_has_flux_override or "## EDITOR OVERRIDES" in (source or ""):
        settings.still_backend = "flux"
        settings.reject_sdxl = True
        settings.aspect = "4:3"
        settings.aspect_ratio = "4:3"
        settings.default_clip_duration_s = 10.0
        settings.fps = 24
        settings.require_all_stills_approved = True
        settings.native_minimax_voice = True
        settings.no_music = True
        settings.needs_canvas_qualification = True
    return settings


def parse_duration_seconds(header_or_text: str, default: float = 10.0) -> float:
    m = _TIME_RANGE_RE.search(str(header_or_text or ""))
    if not m:
        return float(default)
    t1 = int(m.group("m1")) * 60 + int(m.group("s1"))
    t2 = int(m.group("m2")) * 60 + int(m.group("s2"))
    dur = float(t2 - t1)
    return dur if dur > 0 else float(default)


def _map_speaker(pre_context: str) -> str:
    ctx = (pre_context or "").lower()
    # Prefer nearest speaker cue in the trailing window.
    entity_hits = list(re.finditer(r"\bentity(?:\s+voice)?\b", ctx))
    actor_hits = list(
        re.finditer(
            r"\b(?:actor|alice|bob)(?:\s+voice)?\b|\bthe\s+actor\b",
            ctx,
        )
    )
    last_ent = entity_hits[-1].start() if entity_hits else -1
    last_act = actor_hits[-1].start() if actor_hits else -1
    if last_ent > last_act:
        return "ENTITY"
    if last_act >= 0:
        return "ACTOR"
    if re.search(r"\bhuman\s+voice\b|\bdistorted\s+human\s+voice\b", ctx):
        return "ENTITY"
    return "ACTOR"


def extract_dialogue_lines(video_prompt: str, clip_id: str = "") -> list[dict[str, Any]]:
    """Extract ordered dialogue from MiniMax video prose / <d> tags."""
    text = str(video_prompt or "")
    lines: list[dict[str, Any]] = []
    for m in _D_TAG_RE.finditer(text):
        exact = " ".join(m.group(1).split()).strip()
        start = m.start()
        pre = text[max(0, start - 80) : start]
        speaker = _map_speaker(pre)
        lines.append(
            {
                "speaker_id": speaker,
                "speaker": speaker,
                "exact_text": exact,
                "text": exact,
                "improvisation_permitted": False,
                "order": len(lines),
            }
        )
    # Improvisation directions without exact words (C007/C009 style).
    if _IMPROV_RE.search(text) and not lines:
        lines.append(
            {
                "speaker_id": "ACTOR",
                "speaker": "ACTOR",
                "exact_text": None,
                "text": None,
                "improvisation_permitted": True,
                "order": 0,
                "note": "improvisation directed; exact transcript not specified",
            }
        )
    elif _IMPROV_RE.search(text):
        # Mark any existing lines? Prefer a separate improv marker line if
        # prose asks to improvise in addition to tagged speech.
        for line in lines:
            if line.get("exact_text") is None:
                line["improvisation_permitted"] = True
    return lines


def text_clearly_speech_bearing(video_prompt: str) -> bool:
    return bool(_SPEECH_BEARING_RE.search(str(video_prompt or "")))


def enrich_clip(
    clip: dict[str, Any],
    settings: JobSettings,
    *,
    compile_errors: list[str],
) -> dict[str, Any]:
    out = dict(clip)
    cid = str(out.get("id") or "").upper()
    header = str(out.get("header") or "")
    # Prefer duration from video section header text if present in body.
    body = str(out.get("body") or "")
    video = str(out.get("source_video_prompt") or out.get("video_prompt") or "")
    dur_src = header
    # Frame-first packs store time on video heading inside body.
    vm = re.search(
        rf"{re.escape(cid)}\s*[—–-]\s*VIDEO\s+PROMPT\s*[—–-]\s*({_TIME_RANGE_RE.pattern})",
        body,
        re.I,
    )
    if vm:
        dur_src = vm.group(1)
    elif _TIME_RANGE_RE.search(header):
        dur_src = header
    elif _TIME_RANGE_RE.search(body[:400]):
        dur_src = body[:400]
    out["duration_seconds"] = parse_duration_seconds(
        dur_src, settings.default_clip_duration_s
    )
    out["aspect_ratio"] = settings.aspect_ratio
    out["fps"] = settings.fps
    out["model_profile"] = "flux" if settings.still_backend == "flux" else out.get(
        "model_profile"
    )
    out["override_resolution"] = settings.override_resolution
    out["canvas_policy"] = settings.canvas_policy
    out["needs_canvas_qualification"] = settings.needs_canvas_qualification

    dialogue = extract_dialogue_lines(video, cid)
    # Also scan source_video_prompt if adapter rewrote video_prompt.
    if not dialogue and out.get("source_video_prompt"):
        dialogue = extract_dialogue_lines(str(out["source_video_prompt"]), cid)
    out["dialogue_lines"] = dialogue

    speech_bearing = bool(dialogue) or text_clearly_speech_bearing(video)
    if not speech_bearing and out.get("source_video_prompt"):
        speech_bearing = text_clearly_speech_bearing(str(out["source_video_prompt"]))

    if dialogue:
        # required_audio True unless every line is improvisation-only with no text
        has_exact = any(d.get("exact_text") for d in dialogue)
        has_improv = any(d.get("improvisation_permitted") for d in dialogue)
        out["required_audio"] = bool(has_exact or has_improv or speech_bearing)
    elif speech_bearing:
        out["required_audio"] = True
        out["compile_error"] = (
            f"{cid}: speech-bearing video prompt but dialogue extraction empty"
        )
        compile_errors.append(out["compile_error"])
    else:
        out["required_audio"] = False

    # Strip SDXL LoRA bindings when Flux.
    if settings.reject_sdxl or settings.still_backend == "flux":
        for field in ("start_frame_lora", "last_frame_lora"):
            out[field] = None
        # Ensure model_profile not realvisxl
        if str(out.get("model_profile") or "").lower() in {
            "realvisxl",
            "sdxl",
            "realvis",
        }:
            out["model_profile"] = "flux"
    return out


def build_conflict_ledger(source: str, clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Record creative conflicts; do not silently rewrite story."""
    entries: list[dict[str, Any]] = []
    raw = str(source or "")

    entries.append(
        {
            "id": "ending_revised_vs_body_attack",
            "clips": [f"C{n:03d}" for n in range(69, 103)],
            "status": "unresolved_creative",
            "summary": (
                "Introduction says revised C069–C102 supersedes the original, but "
                "parsed bodies may still contain attack/static/mirroring progression "
                "alongside appended revised story material. Do not infer a replacement "
                "34-shot ending without an explicit operator choice."
            ),
        }
    )
    entries.append(
        {
            "id": "static_transition_scope",
            "clips": ["C069", "C070", "C071"],
            "status": "explicit_override",
            "summary": (
                "EDITOR OVERRIDES Rule 6 permits only a brief static transition at "
                "C069. C070/C071 continuing or holding static needs an explicit "
                "exception if retained; C102 final cutoff likewise."
            ),
        }
    )
    improv_clips = [
        c["id"]
        for c in clips
        if any(
            (d or {}).get("improvisation_permitted")
            for d in (c.get("dialogue_lines") or [])
        )
    ]
    if improv_clips:
        entries.append(
            {
                "id": "improvisation_lines",
                "clips": improv_clips,
                "status": "unresolved_creative",
                "summary": (
                    "Some lines are directions to improvise rather than exact dialogue "
                    "(e.g. C007/C009). Marked improvisation_permitted=True with "
                    "exact_text=None; exact-transcript QA cannot validate unspecified words."
                ),
            }
        )
    entries.append(
        {
            "id": "handheld_vs_external_fullbody_post_fall",
            "clips": ["C015", "C016"],
            "status": "unresolved_creative",
            "summary": (
                "Actor handheld camcorder POV conflicts with any post-fall description "
                "that requires an external full-body view. Compile camera ownership and "
                "visible-body constraints per shot including landing and pickup."
            ),
        }
    )
    entries.append(
        {
            "id": "c102_you_can_talk",
            "clips": ["C102"],
            "status": "unresolved_creative",
            "summary": (
                'C102 "You can talk?" follows earlier entity dialogue. Determine whether '
                "this is intentional comedy or a stale-ending inconsistency."
            ),
        }
    )
    # Kept out of the f-string below: a backslash inside an f-string expression
    # is a SyntaxError before Python 3.12.
    appendix_present = bool(re.search(r"(?i)##\s*APPENDIX|Character Bible", raw))
    entries.append(
        {
            "id": "appendix_stripping_risks",
            "clips": [],
            "status": "explicit_override",
            "summary": (
                "Generic appendix stripping can discard character-bible/story-rule "
                "information. Extract and version the bible before separating clip "
                "bodies. Separate appended agent reports and conversation debris from "
                "story authority."
            ),
            "note": (
                "Source contains APPENDIX / Character Bible markers; parser truncates "
                f"at appendix (appendix_present={appendix_present})."
            ),
        }
    )
    return entries


def compile_pack(path: str | Path, *, out_dir: str | Path | None = None) -> dict[str, Any]:
    """Compile the exact attachment into job settings, clips, ledger, report."""
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    # Strip leading chat wrapper if present (audit paste often prefixes instructions).
    if '## EDITOR OVERRIDES' in raw and not raw.lstrip().startswith("# Backrooms"):
        # Keep from first markdown title if embedded in quotes/prose
        m = re.search(r'(?m)^#\s+Backrooms\s+Sitcom', raw)
        if m:
            raw = raw[m.start():]
        # Also strip trailing agent dump after story authority when present
        junk = re.search(
            r'(?is)\n"{0,1}\s*and here is the update from grok agent',
            raw,
        )
        if junk:
            raw = raw[: junk.start()].rstrip()

    settings = compile_job_settings(raw)
    import managed_prompt_pack as mpp

    # Ensure adapter sees Flux before adapting: temporarily inject is already in source.
    clips = mpp.parse_clips(raw)
    compile_errors: list[str] = []
    enriched = [enrich_clip(c, settings, compile_errors=compile_errors) for c in clips]

    # Fail closed on speech-bearing missing extraction
    blockers = list(compile_errors)
    if settings.reject_sdxl:
        for c in enriched:
            for field in ("start_frame_lora", "last_frame_lora"):
                lora = c.get(field)
                if isinstance(lora, dict) and lora.get("name"):
                    blockers.append(
                        f"{c.get('id')}: SDXL LoRA still bound after Flux compile ({lora})"
                    )
            if str(c.get("model_profile") or "").lower() != "flux":
                blockers.append(
                    f"{c.get('id')}: model_profile={c.get('model_profile')!r} expected flux"
                )

    ledger = build_conflict_ledger(raw, enriched)
    dialogue_fields_count = sum(
        1 for c in enriched if c.get("dialogue_lines")
    )
    dialogue_line_count = sum(len(c.get("dialogue_lines") or []) for c in enriched)
    duration_total_s = sum(float(c.get("duration_seconds") or 0) for c in enriched)
    required_audio_count = sum(1 for c in enriched if c.get("required_audio"))

    report = {
        "clip_count": len(enriched),
        "flux_ok": all(str(c.get("model_profile") or "").lower() == "flux" for c in enriched)
        and settings.still_backend == "flux",
        "still_backend": settings.still_backend,
        "reject_sdxl": settings.reject_sdxl,
        "aspect_ratio": settings.aspect_ratio,
        "dialogue_fields_count": dialogue_fields_count,
        "dialogue_line_count": dialogue_line_count,
        "required_audio_count": required_audio_count,
        "duration_total_s": duration_total_s,
        "duration_expected_s": 1020.0,
        "fps": settings.fps,
        "conflict_ledger_count": len(ledger),
        "compile_errors": compile_errors,
        "blockers": blockers,
        "needs_canvas_qualification": settings.needs_canvas_qualification,
        "source_path": str(path),
    }

    out = Path(out_dir) if out_dir else HERE / "outputs_compile"
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "job_settings.json", settings.to_dict())
    atomic_write_json(out / "clips_compiled.json", {"clips": enriched, "count": len(enriched)})
    atomic_write_json(out / "conflict_ledger.json", {"entries": ledger, "count": len(ledger)})
    atomic_write_json(out / "compile_report.json", report)

    return {
        "settings": settings.to_dict(),
        "clips": enriched,
        "ledger": ledger,
        "report": report,
        "out_dir": str(out),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compile Backrooms pack (offline).")
    p.add_argument(
        "--source",
        type=Path,
        default=HERE / "pasted-text.txt",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=HERE / "outputs_compile",
    )
    args = p.parse_args(argv)
    result = compile_pack(args.source, out_dir=args.out_dir)
    report = result["report"]
    print(json.dumps(report, indent=2))
    if report.get("blockers") or report.get("compile_errors"):
        # Compile errors on speech extraction are blockers; still write artifacts.
        print("COMPILE_BLOCKERS", len(report.get("blockers") or []), flush=True)
    print(
        f"Wrote {result['out_dir']} clips={report['clip_count']} "
        f"duration_total_s={report['duration_total_s']} "
        f"dialogue_fields={report['dialogue_fields_count']}",
        flush=True,
    )
    return 0 if report.get("flux_ok") and report.get("clip_count") == 102 else 1


if __name__ == "__main__":
    raise SystemExit(main())
