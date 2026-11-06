# CHANGELOG 2026-09-20 — Backrooms audit engineering closeout (in progress)

## Operator inputs
- Creative stills: size/aspect **OK**; creative sign-off **REJECTED_MANY** (`live_jobs/creative_stills_review_20260920/`)
- Conflict ledger **locked** safe defaults A/A/B/A/A/A (`live_jobs/conflict_ledger_decisions.json`)
- Character bible freeze (`live_jobs/character_bible_freeze_20260920/`)

## Registry bugfix
- `flux_still_batch.py` alias wrote start records under `refs.start` (often previous last id), overwriting last-frame entries
- Rebuilt `stills_approved.json` from disk PNGs; 102/102 contract PASS; chain SHA match 101/101
- Patched batch to always key `{cid}_approved_{start|last}_frame`

## Qual status
| Qual | Status | Notes |
|------|--------|-------|
| 1 Compile | PASS | prior |
| 2 Entrypoint | PASS offline | `verify_backrooms_entrypoint_offline.py` + production integration |
| 3 Voice bootstrap | PASS | prior ACTOR+ENTITY |
| 4 Combined boundary+audio | PASS prior; pixel follow-on | stills chain PASS; video strict pixel-perfect FAIL (encode drift; last closer than first) |
| 5 Representative GPU | **PASS 11/11** | `live_jobs/representative_beats_gpu_20260920/` |
| 6 Stills technical | PASS; creative unsigned | |
| 7 102-shot soak | **IN PROGRESS** | `live_jobs/qual7_soak_20260920/` short-length unique stills |
| 8 Delivery | **INTERIM PASS** | Qual5 SELECTED concat ~17.9s, 11 unique SHAs; **not** 17:00 |

## Honest blockers for final film claim
1. Creative still regen + human sign-off
2. Qual7 completion + Qual8 full 1020s SELECTED assembly
3. Full 10s editorial length (current GPU quals use short length like Qual3/4)
