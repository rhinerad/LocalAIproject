# Claude Code handoff — C001_last identity-safe smile refinement

Continue the Backrooms prompt-pack still-image pipeline in:

`A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09`

Task `f8f7f70e364d40c0`, source revision
`72a7c2e51de194b3da9a717c4d02f288a634d0075f9d8a240eafce3f7496194a`.

## Read first

Read `CLAUDE.md`, this file, `CHANGELOG/2026-09-10d_c001_identity_safe_smile_refinement.md`,
`work/run_prompt_pack_production.py`, `work/image_render.py`, and the latest
`production_2026-09-10d.log` before acting.

## Non-negotiable state

- Still-only phase. Do not begin any video.
- Do not touch `outputs/equal_shares/**`.
- Preserve every existing attempt, receipt, image, QA file, and log.
- GPU ceiling is 82 C. Verify port 8188 and GPU ownership before every run.
- Run the supervisor as a direct script, never with `-m`:
  `python work/run_prompt_pack_production.py --cid f8f7f70e364d40c0`
- The production ledger is deliberately paused with no live supervisor. GPU and
  port 8188 were free at handoff.
- `C001_start` remains generated/QA-passed but operator approval is pending.
- Videos remain blocked until every still passes and the operator approves.

## Canonical visual evidence

Original identity/QA anchor:

`local_agent/runtime/managed_tasks/f8f7f70e364d40c0/revisions/72a7c2e51de194b3da9a717c4d02f288a634d0075f9d8a240eafce3f7496194a/outputs/media/stills/pack_f8f7f70e364d40c0_72a7c2e5_c001_start/baaf329eb9d84acba0ade4d8bb3c195c/still.png`

SHA-256: `0b944e9ab752d1b1d97d6816ed0014dbbce7c950f1804dd7c980b4daa5de7003`

Immutable wave intermediate; always restart smile refinement from this file,
never from a failed refinement:

`local_agent/runtime/managed_tasks/f8f7f70e364d40c0/revisions/72a7c2e51de194b3da9a717c4d02f288a634d0075f9d8a240eafce3f7496194a/outputs/media/stills/pack_f8f7f70e364d40c0_72a7c2e5_c001_last/022d6c6ef9b945f192d7a2545746ffe0/still.png`

SHA-256: `9374d6e23a5d81e42dbea377c5b8a4203ea521f731ee6364bc2675853b13b014`

Exact QA says the wave intermediate has the same person, hair, beard, clothes,
and room and visibly raises a hand. Its only semantic failure is no smile.

## What was fixed

1. Semantic QA now uses an independent blind candidate description, independent
   reference description, and prompt-free two-image continuity comparison. It
   caught a main-verdict hallucination that claimed a smile while its own blind
   observation said `serious`.
2. `select_smile_refinement_reference()` now accepts only the immutable
   `c001-localized-wave-openpose-ipadapter-v3` evidence. Failed v4/v5 refinements
   cannot recursively become anchors.
3. `work/image_render.py` has a new `face_refine_identity` mode using the already
   installed Impact Pack FaceDetailer plus SDXL IP-Adapter Face. It samples a
   detected/enlarged face crop and composites it into the untouched wave image.
4. Installed exact identity model:
   `A:\Users\rhine\ComfyUI-Shared\models\ipadapter\ip-adapter-plus-face_sdxl_vit-h.safetensors`
   SHA-256 `677AD8860204F7D0BFBA12D29E6C31DED9BEEFDF3E4BBD102518357D31A292C1`.
5. Installed Impact Pack dependencies in the existing ComfyUI venv:
   `piexif==1.1.3`, `ultralytics==8.4.146`, `segment-anything==1.0`, and
   `dill==0.4.1`. `YOLO_CONFIG_DIR` is isolated under the project runtime.
6. Every recovery policy is versioned and limited to one attempt. Infrastructure
   failures and rejected images remain immutable evidence.
7. The full-frame clamped-mouth test achieved protected overlap `0/255`, proving
   mask spill was eliminated, but its approximately 11x7 latent-pixel mouth area
   produced a blue object over the mouth. That path is rejected.

## Latest attempts

- `4565281dd7034b1fb3881988a342514e`: FaceDetailer preflight failed because
  `piexif` and `ultralytics` were missing. No model load or image.
- `5a2d751267fc4269a22ebadb7b4e4448`: preflight reached the next missing
  dependencies, `segment_anything` and `dill`. No model load or image.
- `f416e43bbf9a42b2bb705998d64b9ef2`: first successful FaceDetailer render,
  denoise 0.32, IP-Adapter weight 0.90. It preserved identity/room/wave but made
  a stern frown. Blind QA correctly rejected it.
- `920dd4357cc841359338dcfcafa02a13`: stronger smile prompt, denoise 0.42,
  IP-Adapter weight 0.70. It preserved identity/room/wave and visually softened
  the mouth, but the smile remained too subtle. Blind QA labeled it `serious,
  slightly concerned` and rejected it. This is the current active evidence path,
  not an accepted output.

Current production status:

`paused_for_identity_recovery`

Current last error:

`1 c001-smile-facedetailer-ipadapter-v5/face-crop-strong-smile-guidance-v4 attempt(s) rejected; evidence preserved for supervised workflow reassessment`

## Verification already green

Run from the repository root:

```powershell
python -m py_compile work/image_render.py work/run_prompt_pack_production.py work/test_still_retry_not_stop.py
python -m unittest local_agent.test_production_integrity local_agent.test_media_accuracy_gate work.test_still_retry_not_stop -q
```

Result at handoff: `Ran 62 tests ... OK`.

## Exact next engineering step

Do not change checkpoints yet. The FaceDetailer/IP-Adapter mechanism now works
and continuity is proven. Add one new bounded policy revision after v4:

- Always use `022d6c6e.../still.png` as the working reference.
- Keep `baaf329e.../still.png` as the identity and QA reference.
- Use a short face-only positive prompt demanding a clearly visible natural
  tooth-bearing friendly sitcom smile. The last negative prompt prohibited an
  open mouth and likely suppressed the only unambiguous smile cue; remove that
  prohibition while still rejecting oversized/deformed teeth.
- Try FaceDetailer denoise around `0.48-0.52` and IP-Adapter weight around
  `0.55-0.62`; preserve all other pixels through FaceDetailer compositing.
- Give the new policy a new `policy_revision` and `max_attempts: 1`.
- Run exactly one C001_last attempt, inspect the actual PNG manually, then allow
  exact Qwen2.5-VL QA. Do not trust the prompted verdict when blind evidence
  contradicts it.
- If it still fails only the smile, preserve it and reassess. Do not spin seeds,
  recursively refine a failed face, weaken QA, or start videos.

Only consider a checkpoint switch after a new documented bounded trial shows
RealVisXL cannot produce a clear smile under this working crop path. If switching,
test C001 only and rerun appearance, setting, anatomy, framing, and continuity QA.


## Update 2026-09-10h

Larger-mouth `inpaint_identity` trial `c001-smile-lowerface-inpaint-v8` failed:
attempt `27d66f0fa739466bad4643c87bf14033` produced a solid grey face plate (identity break, no smile).
See `CHANGELOG/2026-09-10h_c001_larger_mouth_inpaint_trial.md`. Ledger remains `paused_for_identity_recovery`.
Immutable wave unchanged.

## Update 2026-09-10i / 2026-09-10j

- v9 tiny-lip inpaint `58350556...`: continuity flags mostly true but white mouth patch + no smile. Changelog `2026-09-10i`.
- v10 medium-mouth ultra-low-denoise `325d4cf5...`: identity drift + no smile. Changelog `2026-09-10j`.
Ledger remains `paused_for_identity_recovery`. Immutable wave unchanged.

## Update 2026-09-10k

Mid-IP FaceDetailer `c001-smile-facedetailer-midip-v11` attempt `93d570a8...`:
continuity pass, blind expression serious / no smile. See `CHANGELOG/2026-09-10k_c001_mid_ip_facedetailer_trial.md`.
Ledger remains `paused_for_identity_recovery`. Immutable wave unchanged.

## Update 2026-09-10l

Stage B finalize controlled `face_refine_identity` attempt `6d7c1875...` (v12):
continuity pass, blind expression neutral / no smile. See `CHANGELOG/2026-09-10l_c001_stageb_face_refine_controlled_test.md`.
Ledger remains `paused_for_identity_recovery`. Immutable wave unchanged. Tests still green.

## Update 2026-09-10n — C001_last passed; operator review required

The diffusion approach is no longer the active recovery. Evidence from v5-v12
showed that identity-safe FaceDetailer settings retained a neutral/serious
mouth, while smile-producing or mouth-inpaint settings changed identity or
created face plates.

`work/image_render.py` now supports `liveportrait_expression` using the already
installed AdvancedLivePortrait `ExpressionEditor`. It loads the immutable wave,
retargets the detected facial expression, and composites the face back without
loading an SDXL checkpoint or sampler. Shared model paths now explicitly expose
`liveportrait/` and `ultralytics/`.

Two harness failures were fixed and preserved:

- v13 `14304c86...`: valid output existed, but the verifier incorrectly treated
  ExpressionEditor's temporary UI preview as a deliverable. Verification is
  now restricted to explicit `SaveImage` nodes.
- v14-v16: the exact VLM's full-frame and absolute face-crop blind passes called
  the small face neutral/serious. The prompt-aware pass said smiling. The gate
  now adds a separate prompt-free comparison of original and candidate face
  crops and requires same identity plus literal smile cues; the original blind
  passes remain recorded and are not overwritten.

Successful candidate:

- attempt: `72c3e47a11214b3dae1ee11f8821a99b`
- policy: `c001-smile-liveportrait-v17/blind-contrastive-expression-gate-v5`
- still SHA-256:
  `b10512dafe45a610cfc10721bac71fbff5c5bb8a5f49c6b2043bfaa087a293df`
- exact VLM continuity: same person/hair/facial hair/clothing/room all true
- prompt-free expression comparison: candidate more smiling=true,
  same identity=true, cues=`upturned mouth corners`, `visible teeth`
- changed pixels versus immutable wave: 20,819 (2.6473%), confined to
  `[451, 80, 599, 228]`
- tests: `Ran 68 tests ... OK`

The supervisor stopped at the successful C001 smile guard. Port 8188 is free,
the GPU is idle, approval remains pending, and no video started. The next action
is an operator review of C001_start and this C001_last candidate; do not resume
the pack before that decision.

## Update 2026-09-11a — malformed hand repaired; v28 passes

The operator rejected v17 because its raised hand was malformed. Bounded hand
repairs v20-v26 were preserved but rejected: four digits, multi-hand editing,
claw, source-pose reconstruction, literal skeleton, four digits, then a
two-finger gesture. Do not reuse those attempts as accepted anchors.

The successful image edit was not accepted as a full frame because it changed
more than the hand. It is stored only as a hash-pinned donor at:

`work/runtime/identity_donors/C001_open_palm_gpt_image_2026-09-11.png`

The v28 policy deterministically composites only a small feathered hand polygon
onto the v17 smile frame. The candidate changes 10,839 pixels (1.3783%), bounded
to `[639, 44, 750, 180]`.

Current successful automated-QA candidate:

- attempt: `6e12ff2ab0b84085b765b7dd07a6bd4c`
- version/revision:
  `c001-hand-donor-composite-v28/five-digit-schema-v12-recheck-v1`
- SHA-256:
  `1302d430636908f50d6d3c2815559a7161300d9d2a5ab96320dd80c95260b4b6`
- blind anatomy: four upright fingers + distinct thumb = five total digits;
  no missing, extra, or fused digits; plausible anatomy/wrist; high confidence
- continuity: same person/hair/facial hair/clothing/room geometry
- semantic gate:
  `reference-blind-continuity-face-and-hand-crop-v12`
- tests: `Ran 90 tests ... OK`

The v12 change resolves a real counting ambiguity by recording fingers and thumb
separately; it does not weaken the anatomy gate. The supervisor is stopped,
port 8188 is free, GPU is idle, and no later still or video started. Both C001
stills remain `approval_status: pending`; operator review is the next step.
