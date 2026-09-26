# CHANGELOG 2026-09-18i — Voice QA, endurance qualification, distinct long master

## Goal
Close the three remaining BLOCKED items after 18h:
1. Calibrated voice-similarity / transcript QA on real takes
2. Endurance / multi-shot unattended qualification
3. Long master from distinct SELECTED narrative shots (not identical-pad assembly)

## Added
- `native_voice_qa.py` — numpy spectral voice similarity + transcript Jaccard/exact; uncertain band; fail-closed mismatch
- `verify_native_voice_qa_offline.py` — offline unit gates (PASS)
- `run_voice_qa_on_live.py` — extract-from-mp4 path when audio exists
- `calibrate_voice_qa_live.py` — live calibration on real ALICE/BOB story voice WAVs
- `endurance_qualification.py` — bounded multi-shot SELECTED job, fault inject/repair, `execute_normalize_concat`
- `build_long_distinct_master.py` — cycle distinct SELECTED clips to ~10 min without identical-pad cheat

## Evidence (DuranGamingPC)
| Gate | Result | Artifact |
|------|--------|----------|
| Offline voice QA | PASS | `verify_native_voice_qa_offline.py` |
| Live voice QA calibrate | PASS | `live_jobs/.../voice_qa/live_voice_qa_report.json` |
| Endurance control-plane | PASS | `live_jobs/.../endurance_qualification_report.json` |
| Short distinct master (5 unique SHA) | PASS ~22.3 s | `.../final/master_distinct_selected.mp4` |
| Long distinct master (5 unique, 27 cycles) | PASS ~601.9 s | `.../final/master_long_distinct_selected.mp4` |

## Honest limits
- **Voice spectral discrimination is weak** on these short refs: same-ALICE ~1.0 vs ALICE↔BOB ~0.986. Transcript mismatch fail-closed is the strong gate. Diarized take extract + stronger timbre model still needed for production speaker lock.
- **`dual_char_00001_.mp4` has no audio stream** in the 18h smoke; take-level extract QA deferred until muxed audio exists.
- **Endurance** = `BOUNDED_ENDURANCE_CONTROL_PLANE` (multi-shot SELECTED + fault repair + concat). Not a multi-hour unattended soak.
- **Long master** proves distinct-SELECTED assembly at ~10:02. Does **not** prove continuous multi-hour generation.

## Unattended policy
Uses existing `unattended_policy.py` / `machine_accepted` vs `operator_accepted` from 18h.
