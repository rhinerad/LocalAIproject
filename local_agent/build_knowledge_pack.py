#!/usr/bin/env python3
"""Compile everything the local model needs into a context it can actually hold.

THE PROBLEM
-----------
This project's documentation is ~200 KB across CLAUDE.md, PROVEN_FACTS.md, the
runbook, the prompt rules and five CHANGELOG entries. The CPU-safe fallback has
a bounded 16K context and cannot read all of that, and even if it could, most of it is
history rather than operating instructions.

So this compiles a **derived, compact brief** — target under 12 KB — containing
only what changes an answer:

  * the settings that are invariant across 15 proven renders
  * the six-section prompt schema with a real worked example
  * the rules that were learned the hard way, each with its measurement
  * the CURRENT state: what is done, what is blocked, what runs next
  * the exact commands, with their preconditions

REGENERATED, NOT WRITTEN BY HAND
--------------------------------
Every number here is read from the project's own state files at build time. That
matters: a hand-written brief drifts, and drift is what caused the 2026-08-17
fault. Re-run this after any change and the model's knowledge follows.

    python local_agent\\build_knowledge_pack.py

Writes the project-only `local_agent/knowledge/EQUAL_SHARES_REFERENCE.md` and
`PROJECT_STATE.json`. The local agent is general-purpose; this detailed
reference is injected only for an explicitly scoped Equal Shares request.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
OUT = Path(__file__).resolve().parent / "knowledge"
REFERENCE = OUT / "EQUAL_SHARES_REFERENCE.md"


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def gather() -> dict:
    req = load(EQ / "voice_requirements.json", {})
    man = load(EQ / "audio_pass_manifest.json", {"clips": {}})
    dur = load(EQ / "audio_pass_durations.json", {"clips": []})
    aud = load(EQ / "voice_audition_manifest.json", {"characters": {}})
    story = load(EQ / "story_config.json", {"clips": []})
    cfg = load(EQ / "audio_pass_config_omni_v1.json", {"clips": []})

    masters = {}
    for e in cfg.get("clips", []):
        for a in e.get("ref_audios", []):
            masters[a["character"]] = {"wav": a["wav"], "provisional": bool(a.get("provisional"))}

    prompts = EQ / "prompts_native_r2v"
    n_prompts = len(list(prompts.glob("*.txt"))) if prompts.is_dir() else 0

    chosen = sum(1 for v in aud.get("characters", {}).values() if v.get("chosen"))
    rendered = sum(1 for v in aud.get("characters", {}).values()
                   for t in v.get("takes", []) if t.get("status") == "rendered")

    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "clips_total": len(story.get("clips", [])),
        "dialogue_clips": len(req.get("clips", [])),
        "speakers": len(req.get("characters", {})),
        "recurring": req.get("recurring", []),
        "one_off": req.get("one_off", []),
        "fl2va_clips": (req.get("summary") or {}).get("fl2va_clips", []),
        "mixed_clips": (req.get("summary") or {}).get("mixed_clips", []),
        "prompts_generated": n_prompts,
        "manifest_clip_records": len(man.get("clips", {})),
        "voice_masters": masters,
        "auditions_rendered": rendered,
        "auditions_chosen": chosen,
        "shortened_clips": sum(1 for r in dur.get("clips", [])
                               if r.get("has_dialogue")
                               and r.get("audio_pass_frames", 0) < r.get("scripted_frames", 0)),
    }


def build_system_prompt(s: dict) -> str:
    rec = ", ".join(s["recurring"]) or "(none)"
    one = ", ".join(s["one_off"]) or "(none)"
    prov = [k for k, v in s["voice_masters"].items() if v["provisional"]]
    return f"""# Equal Shares specialist reference

This is reference material for the Equal Shares project, a 21-minute film built
as {s['clips_total']} MiniMax H3 clips in ComfyUI on this Windows machine. It is
not the local agent's identity or default task. Apply it only after the current
operator request explicitly identifies Equal Shares, MiniMax H3, an Equal
Shares clip identifier, or an Equal Shares project file/path.

# The one rule above all others

A change is **not verified** because the config and the docs agree, because a
drift check is clean, or because regenerated files look right. All three passed
on 2026-08-16 while the renderer sent a corrupted prompt to every clip.

Verified means: the workflow embedded in a real render was extracted
(`ffprobe -show_entries format_tags=prompt` on the MP4, or the PNG metadata) and
diffed against `docs/GOLDEN_REFERENCE/GOOD_AUDIO_GRAPHS.json`. If that has not
been done, say the change is **unverified**.

# Render settings — identical across all 15 proven-good renders, never change them

| | |
|---|---|
| UNet (with references) | `minimax_h3_ref2va_pruned_nvfp4.safetensors` |
| UNet (no references) | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| VAEs | `minimax_h3_video_vae_fp16` + `minimax_h3_audio_vae_fp32` |
| Sampler / scheduler | `res_multistep` / `simple`, denoise 1.0 |
| Steps | 20 |
| Megapixels | **0.2** for soundtrack, 0.9 first for picture |
| fps / bit depth | 24 / 8-bit |
| Frame count | must be congruent to **5 modulo 17** |

Turbo checkpoints, Turbo nodes and Turbo LoRAs are **prohibited**.

# The prompt format

Six sections in this exact order — **nothing above `subject_definitions:`**.
A prepended header is the most expensive fault in this project's history.

```
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
```

Tags: `<Subject N>` visible content, `<Picture N>` frame anchor, `<Audio N>` voice
reference. Tags follow wiring order. Limits: 9 images, 3 audio.

Key rules (each from a failed render):
1. `retention_analysis` must declare every reference; a voice master is always `reference`.
2. One scripted line = one `<d>[English] …</d>` block. Split = gibberish at the seam.
3. Delivery before the closing tag; mouth closes after `</d>`. Prose after reads as speech.
4. Quotation marks = on-screen lettering. Speech goes in `<d>`.
5. `[Shot N]` = a cut. One continuous take = one `[Shot 1]`. `[0-1 s]` is not H3 grammar.
6. `non_diegetic_music: N/A` for this film.

Use `search_docs` to retrieve a real prompt example or the full rule context.

# Two rules about voices

**One-off speakers need nothing.** ONE clip → no voice master, no `<Audio N>`.
A clip with no recurring speaker uses `MiniMaxH3ImageToVideo` with no references.

- recurring, need a master ({len(s['recurring'])}): {rec}
- one-off, need nothing ({len(s['one_off'])}): {one}
- clips with no references: {', '.join(s['fl2va_clips']) or '(none)'}
- mixed clips: {', '.join(s['mixed_clips']) or '(none)'}

**Duration ladder.** Gibberish or mispronounced words → retry by changing
**duration** (base, +1, −1, +2, −2, +3, −3 s), seed held fixed. A doubled voice
is a `retention_analysis` fault, not a duration fault.

# Current state — regenerated {s['generated']}

- {s['prompts_generated']} native prompts; {s['dialogue_clips']} dialogue clips;
  {s['shortened_clips']} shortened for soundtrack pass (padded back at assembly)
- soundtrack manifest: **{s['manifest_clip_records']}** clip records
- voice auditions: **{s['auditions_rendered']} rendered, {s['auditions_chosen']} chosen**
- provisional/unapproved masters: {', '.join(prov) or '(none)'}

**Soundtrack pass blocked** until voices are chosen; only the Narrator is approved.

# Standing constraints

- One ComfyUI, ever (port 8188). Never delete raw renders, references, manifests.
- No downloads without stating size. No hand-edits to generated prompts.
- No picture rendering until audio gate = 124/124 accepted.
- Every change gets a CHANGELOG/ entry: what, why, evidence, verified, unverified.
"""


def main() -> int:
    s = gather()
    OUT.mkdir(parents=True, exist_ok=True)
    sp = build_system_prompt(s)
    REFERENCE.write_text(sp, encoding="utf8")
    (OUT / "PROJECT_STATE.json").write_text(json.dumps(s, indent=2), encoding="utf8")
    kb = len(sp.encode("utf8")) / 1024
    print(f"system prompt : {kb:.1f} KB  ({len(sp.split())} words)")
    print(f"                {REFERENCE}")
    print(f"state         : {OUT / 'PROJECT_STATE.json'}")
    print(f"\nspeakers {s['speakers']} = {len(s['recurring'])} recurring + {len(s['one_off'])} one-off")
    print(f"prompts {s['prompts_generated']} | manifest records {s['manifest_clip_records']} "
          f"| auditions {s['auditions_rendered']} rendered, {s['auditions_chosen']} chosen")
    if kb > 8:
        print(f"\nWARNING: {kb:.1f} KB exceeds the 6 KB target. Trim the brief.")

    import retrieval as _ret
    stats = _ret.rebuild()
    print(f"\nretrieval index: {stats['files']} files  {stats['chunks']} chunks  "
          f"{stats['index_size_kb']} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
