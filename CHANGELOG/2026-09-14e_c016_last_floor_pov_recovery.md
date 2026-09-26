# 2026-09-14e — C016 last-frame floor-POV recovery

## Diagnosis

C016 start remains accepted on checksum-pinned donor
`work/runtime/identity_donors/c016_start/c016_start_floor_hand_backrooms_imagegen_v1.png`
SHA-256 `fc7893767a312afb317d6176833899fb990390e3ebf3c08a1ad0772674da6e5d`.

C016 last was paused after three bounded failures. Existing evidence was kept.

1. Attempt `8c833fb8fcc5476999949d635add4ac1` — owned ComfyUI PID 31972 stayed
   alive on `--listen 127.0.0.1 --port 8188` but never bound the loopback port.
   stderr stopped after pytorch attention init; stdout was empty; the 240-second
   startup deadline then fired as `alive_not_listening`. Startup ownership and
   loopback-only bind were not changed. Later C016-last renders did start, so
   this is an intermittent owned-process stall, not a bind-config regression.
2. Attempt `038a499fbe674852bad4589ace648369` — floor-level hallway, but the
   generic full-person / visible-camcorder rubric and missing Mode B face/torso
   prompt language failed mechanical and exact-VLM QA.
3. Attempt `51703aecd00b4197911a7f403fde78a6` — standing empty-office plate,
   not a fallen-camcorder floor POV.

The authored last-frame line is "The carpet becomes damp brown-beige under
sickly yellow light." It does not request a hand. Mode B still forbids face
and torso. A hand/sleeve is therefore not required; face/body identity
comparison is skipped only because this shot cannot show them.

## Bounded repair

- Added one checksum-pinned empty floor-POV candidate at
  `work/runtime/identity_donors/c016_last/c016_last_floor_empty_backrooms_imagegen_v1.png`.
- SHA-256: `088e854fb176577c58d05d43837e697c1eb6639124d2fbd34b7b625e30b31f75`.
- Added `c016-last-hash-pinned-floor-pov-v1` / `floor-pov-environment-lock-v1`.
  Eligible only after two completed base failures; `max_attempts: 1`.
- Exact-VLM rubric: static low/tilted 4:3 fallen-camcorder POV, damp
  brown-beige carpet, sickly yellow wallpaper/fluorescent light/repetitive
  openings, no person/hand/camera/operator/furniture/text/gore. Cross-image
  identity comparison is skipped. Setting, composition, forbidden-equipment,
  and exact Qwen2.5-VL Caption V4 checks remain required.
- Donor copy does not start ComfyUI.

## Verification

```
python -m py_compile work/run_prompt_pack_production.py work/test_still_retry_not_stop.py local_agent/media_accuracy_gate.py
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 124 tests passed. No model weight, predictor, router, or video
workflow was changed.

## Controlled rerun

Direct runner: `python .\work\run_prompt_pack_production.py --cid f8f7f70e364d40c0`.
GPU was idle (29 C, 0% util). Port 8188 was closed. No second supervisor.

C016 start was re-copied and re-reviewed on the same checksum-pinned donor
because `qa_passed()` compares the ledger canonical prompt hash to the
original job prompt, while the v3 recovery bound the delivery QA prompt.
The re-review passed on the same pixels
`fc7893767a312afb317d6176833899fb990390e3ebf3c08a1ad0772674da6e5d`.
No ComfyUI start.

C016 last then used policy `c016-last-hash-pinned-floor-pov-v1` /
`floor-pov-environment-lock-v1`, attempt
`8f6065756a1b47298301a024685f1b64`, donor SHA-256
`088e854fb176577c58d05d43837e697c1eb6639124d2fbd34b7b625e30b31f75`.
Mechanical QA passed. Exact Qwen2.5-VL Caption V4 / llama.cpp returned
`pass: true` with no camera, matching floor-level Backrooms setting and
composition, and empty subjects. The gate then failed closed because
`requested_subjects_present` and `requested_pose_or_action_visible` were
false on an authored empty plate. That is a contract mismatch, not a
second image. Evidence was preserved. Production is
`paused_for_identity_recovery`. No video was started.

Do not seed-spin. A later same-pixel v2 would need to treat an empty
floor-POV delivery rubric as having no requested person/pose, then
re-review these exact pixels through the same VLM.
