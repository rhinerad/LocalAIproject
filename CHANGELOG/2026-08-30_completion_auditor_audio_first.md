# 2026-08-30 — completion auditor actually enforces the audio-first gate

## What changed

`work/audit_equal_shares_completion.py` was already counting
`audio_pass_manifest.json` status `"accepted"` for the 124-clip audio gate, but
it did not enforce the rest of the audio-first state CLAUDE.md named after the
2026-08-18 work. The gaps were in the code, not just the docstring.

| File | Change |
|---|---|
| `work/audit_equal_shares_completion.py` | Added `run_audit()`; fail-closed checks for `pending_ear_review` / `needs_ear_review`, `human_review_needed` across audio, picture, legacy, and visual review docs; one-off / VOX / filler refs on accepted clips via `voice_requirements.json`; explicit 1266 s target; AAC stream duration must be measurable and within 2 s of the video stream. `manifest.json` `"valid"` and `visual_audit.json` reviewed_pass remain informational only. |
| `work/test_audit_equal_shares_completion.py` | **New.** 10 tests covering the gates above, including the trap that 124 legacy `"valid"` + visual 43 is not Stage-1 audio acceptance. |

## Why

CLAUDE.md Completion: the script "must be extended to enforce the audio-first
state" and is the final gate. That line predated the retention_analysis fix,
the duration ladder, the one-off-speaker rule, and the voice-master harvest.
The auditor still would have declared a pass without checking pending ear
review, one-off/VOX refs, or A/V-synced AAC against 1266 s.

False negatives (blocking a real pass) are cheaper than false positives. Missing
`voice_requirements.json`, unmapped reference paths, and missing stream
durations all fail closed.

## The evidence — live state on 2026-08-30, not the 2026-08-13 doc claim

CLAUDE.md still says "As of 2026-08-13: 124 rendered, **43 accepted**". That
line is visual review of the old single-pass, not Stage-1 audio. Read from the
files today:

| Source | What it actually records | Count today |
|---|---|---|
| `story_config.json` | planned clips / edit duration | **124 clips, 1266.0 s** |
| `audio_pass_manifest.json` | Stage-1 audio acceptance | **0/124 accepted.** `clips` is `{}`. Reset 2026-08-18T17:15:17 cleared all 124 after the corrupt-prompt pass. |
| `picture_pass_manifest.json` | Stage-2 visual acceptance | **missing** (0/124) |
| `visual_audit.json` | old visual `reviewed_pass` | **43** — and its `audio_audit` still says H3 audio is "discarded from final assembly" |
| `manifest.json` | mechanical `"valid"` (not accepted) | **124/124 `"valid"`**, 122 with `raw_audio_discarded: true`, dialogue_validation 60 rejected / 60 valid / 4 absent. No Stage-1 audio field. |
| `EQUAL_SHARES_FINAL_1344x768.mp4` | final master | **absent** |

The project is **further from 124/124 Stage-1 audio than the stale 43 figure**.
Zero soundtracks are accepted. The 43 is leftover visual review. 124 `"valid"`
renders are not acceptances — CLAUDE.md "Validation is not acceptance".

`audio_pass_config_omni_v1.json` still *lists* 8 one-off character masters
(Aid worker, Congregation member, Council member, Crew lead, Doris recording,
Male Visitor Two, Unhoused man, Wealthy commuter). Native prompts currently
Audio-tag none of them (0 hits). The renderer filters at render time; the
auditor now fails if those refs appear on an accepted clip.

Harvest narrator master in `good_audio_harvest.json` is still
`pending_ear_review`. That is a master, not a clip status, so it does not trip
the clip-level pending gate.

## What was verified after

```
python work\test_audit_equal_shares_completion.py
Ran 10 tests in 43.265s
OK
```

Live gate against current outputs:

```
python work\audit_equal_shares_completion.py
EXIT:1
complete: false
audio_accepted_count: 0
picture_accepted_count: 0
legacy_manifest_valid_count_informational: 124
visual_audit_accepted_count_informational: 43
audio_gate_124_accepted: false
picture_gate_124_visually_accepted: false
final_master_present: false
final_duration_within_2s_of_1266: false
final_aac_synced: false
voice_requirements_present: true
no_one_off_or_vox_refs_on_accepted_clips: true   (vacuous: nothing accepted)
zero_pending_ear_review: true
zero_human_review_needed: true
planned_duration_within_2s_of_1266: true         (story_config sums to 1266.0)
```

The new checks that can pass vacuously today (`zero_pending_ear_review`,
`no_one_off_or_vox_refs_on_accepted_clips`) are covered by unit tests that
inject a pending clip, a one-off character, a VOX path, a fl2va clip with refs,
and an AAC stream 66 s shorter than picture.

## What is still unverified

- No accepted Stage-1 take exists, so the one-off/VOX scan has not yet run
  against a real `audio_pass_manifest` attempt record from
  `work/render_audio_pass.py`. The unit tests use the field names that runner
  writes (`audio_references`, `voice_ref_characters`, `prompt_source`).
- Stream-duration sync is mocked in tests. The live tree has no final master,
  so ffprobe was not exercised on a real 1344×768 H.264/AAC file.
- Native prompt files were sampled for `<Audio N>` → one-off mapping (0 hits)
  but that is not an extracted-graph proof of what H3 would receive.
- `audio_pass_config_omni_v1.json` still carries one-off masters; this change
  does not edit that config or `render_audio_pass.py`.
