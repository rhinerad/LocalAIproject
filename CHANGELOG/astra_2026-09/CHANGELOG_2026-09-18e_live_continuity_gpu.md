# CHANGELOG 2026-09-18e — bounded live GPU continuity test

## Result: PASS (`ok: true`)

ComfyUI **0.34.0** on DuranGamingPC RTX 5080. Profile: base continuity validation (864×480, 124 frames, 20 steps, SageAttention auto).

| Phase | Outcome |
|-------|---------|
| A live render | PASS — prompt `2c7629a3-2559-430e-858f-e437554051e9`; first_frame bound to `C001_ref_still.png` via LoadImage |
| B intentional tech QA fail | PASS — `RETRY_PENDING`; `select_attempt` blocked |
| C resume gate | PASS — `should_skip=false` on RETRY_PENDING |
| D select + child bind | PASS — SELECTED; parent switch invalidates child |

### Metrics
- Wall clock (submit→artifact): **331.78 s**
- Editorial length: **5.167 s** (124/24)
- **Wall-clock per accepted second: 64.211 s**
- Artifact: `A:\Users\rhine\ComfyUI-Shared\output\astra_live_continuity\continuity_1789743607_00001_.mp4`
- SHA256: `1b441c58c8ecba932b2fc63043ff01b0e386c9ba49c4a23e4c6c7f0afe150a30`

### Harness
`live_continuity_bounded_test.py` under the handoff root.
