# Evidence matrix — 2026-09-18i

Canonical handoff:
`A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09`

| Claim | Status | Proof |
|-------|--------|-------|
| Offline transcript + similarity QA unit tests | PASS | `verify_native_voice_qa_offline.py` |
| Same-ref spectral high; mismatch transcript fail-closed | PASS | `live_jobs/remaining_20260918_111727/voice_qa/live_voice_qa_report.json` |
| Cross-speaker spectral separation calibrated for production lock | PARTIAL / WEAK | same≈1.0, cross≈0.986 — margin too small for sole gate |
| Take extract from dual_char live mp4 | BLOCKED | video-only; no audio stream |
| Bounded endurance multi-shot + fault repair | PASS | `endurance_qualification_report.json` (`qualification_level`: BOUNDED_ENDURANCE_CONTROL_PLANE) |
| Distinct SELECTED short master (≠ identical pad) | PASS | 5 unique input SHA256; `master_distinct_selected.mp4` ~22.3 s |
| Distinct SELECTED long master ~10 min | PASS | `master_long_distinct_selected.mp4` ~601.9 s; 5 unique SHA; 27 cycles |
| Multi-hour unattended soak | NOT RUN | follow-on |
| Proves long-form continuous generation | NO | assembly / control-plane only |

## Input clips (distinct SHA256)
- `ComfyUI-Shared/output/astra_live_continuity/continuity_1789743607_00001_.mp4`
- `ComfyUI-Shared/output/astra_post36/fasth3_00001_.mp4`
- `ComfyUI-Shared/output/astra_post36/ref_single_00001_.mp4`
- `ComfyUI-Shared/output/astra_post36/ref_dual_00001_.mp4`
- `ComfyUI-Shared/output/astra_native_voice/dual_char_00001_.mp4`
