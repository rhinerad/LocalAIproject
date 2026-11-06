# 2026-09-26d — Roadmap Phase 1: the four Section-A operator decisions, decided in chat; Phase 2a found already landed (26b); motion-transfer session observed mid-render and left alone

Executes Phase 1 of the roadmap prompt built on
`pipeline-completion-roadmap-2026-09-26.md`. No code changed in this entry.
No render, no download, no GPU call, no ComfyUI call. Id claimed once with
`scripts/next_changelog_id.py` (`.id_claims/2026-09-26c` is the stray claim
26b already reported; `d` is this entry).

## 0. State re-verified before asking anything

- `CHANGELOG/` tail: `2026-09-26b` (GVD router MiniMax-first policy) landed
  after the roadmap was written. That **is** roadmap item B.5 / prompt
  Phase 2a in full: `engine_family` / `engine_tier` tiered sort in
  `router.route()`, `ShotManifest.requested_engine`, planner phrasing,
  `execute_tool` Wan-fallback acknowledgement gate, `requires_operator_approval`
  made real, legacy `dspy_orchestrator.py` / `batch_run_backrooms_gvd.py`
  confirmed MiniMax-only, 25 new tests. Re-run here:
  `python -m unittest test_gvd_engine_policy` → **25/25 OK** (22.8 s).
  **Phase 2a is therefore superseded and not repeated in this session.**
- Another session (the motion-transfer stage-2 agent) is live in this tree:
  `local_agent/runtime/motion_transfer_20260925/` gained
  `pip_install_26b.log` (insightface 2.0, onnx 1.23.0, ml_dtypes 0.6.0 at
  00:59), `faceid_import_test.{py,log}`, `pass22_faceid_fd050` (history
  success, 630.2 s, peak 14,691 MiB, done 01:25:56) and `pass23_faceid_w06_l04_fd050`
  (owned backend started 01:28:22, graph posted 01:41:47, rendering as this
  is written; port 8188 LISTENING pid 36188, GPU 4.7 GB / 30 C). New weights
  on disk at 00:55: `models/ipadapter/ip-adapter-faceid-plusv2_sdxl.bin`
  (1,487,555,181 B) and `models/loras/ip-adapter-faceid-plusv2_sdxl_lora.safetensors`
  (371,842,896 B). That session has no changelog entry yet. **Nothing in
  its folder, its runner, `motion_transfer.py`, or the GVD catalog rows it
  edits was touched by this session, and no GPU/drive-heavy work was
  started beside it.**
- `git`: only that session's runtime artefacts and the regenerated
  `HANDOFF_STATUS.md` are dirty; no code drift against the roadmap.

## 1. The four decisions (asked in chat with the evidence below; answered 2026-09-26)

| # | question | evidence put to the operator | decision |
|---|---|---|---|
| 1 | motion-transfer identity quality | 25v: face crop + region mask holds identity through 24 frames, upright, follows the motion; 26a: face-detail denoise 0.5 pulls frame 24 toward the reference with no added flicker (head-region frame-to-frame 8.74 → 8.65 mean), every face stays soft (~60 px wide at 768×448), face-detail doubles per-clip time (527–557 s vs ~300 s); FaceID Plus v2 weights already on disk and being rendered by the other session | **FaceID confirmed, and Wan 2.2 Animate 14B download approved** (the 17 GB option). VACE not chosen. |
| 2 | Backrooms motion-keyword table | current table: walk, walking, momentum, push in, push-in, tracking forward, track forward, dolly, glide, advance, move forward; row 265 (B01 `644b`) "gradually moves … panning" rejected → 0.02 (after a 757 s render in 25i; pre-render since 25j) although the clip reviews good and judges 1.00/1.00/0.80 offline | **Relax it** (Phase 2b, separate entry). |
| 3 | still-QA scope | `creative_still_qa.creative_approve` checks actor-visible / face count / continuity anchor only; 24a states "Environment/scene mismatch is not detected by this QA layer" (the missing-skateboard case); heavier CLIP/WD14/Caption-V4 semantic check exists for video submission | **Add a prompt-content axis.** Decided, not built; queued in TODO. |
| 4 | D02 `614e` judge miss | 25g: rig check catches D01 `3032`, c036, tripod clip; on `614e` the VLM writes "FPV drone view through dense pine canopy" ×8 although the quadcopter fills the centre of all 8 frames; all three wordings miss; 25g's next-try = brief-free object listing | **Open a follow-up investigation.** Queued in TODO; VLM-only, separate session. |

None of the four was defaulted or guessed.

## 2. Wan 2.2 Animate download spec (approved; **not executed here**)

Looked up on the Hub with the operator's authenticated HF connector, read-only:

| file | repo | bytes | target |
|---|---|---|---|
| `Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors` | `Kijai/WanVideo_comfy_fp8_scaled` | 18,401,760,586 | `A:\Users\rhine\ComfyUI-Shared\models\diffusion_models\` |
| `LoRAs/Wan22_relight/WanAnimate_relight_lora_fp16.safetensors` (optional) | `Kijai/WanVideo_comfy` | 1,436,672,440 | `...\models\loras\` |

Notes from the repo README: the `_v2` scaled files (17,317,143,060 B) exist
for *native* ComfyUI workflows (fp8 face-encoder layers); for
`ComfyUI-WanVideoWrapper` (installed, commit `ee71d5c4`, 2026-09-15, and it
has `WanVideoAnimateEmbeds`) the initial e4m3fn file is the one to use, as
the doc's §3c already named. The doc's "~0.6 GB relight LoRA" is 1.44 GB
(fp16) or 273 MB (rank-resized); the fp16 one is listed. A: has 10,495 GiB
free. The download is deferred until the motion-transfer session's render
is not writing to A: and does not own the GPU (feedback rule: no multi-GB
A: traffic beside a render); it is queued as an open TODO line with the
size/sha256 verification requirement.

## 3. Files changed

- `TODO.md` (CRLF kept): new "Operator decisions — 2026-09-26d" section
  after START OVER; decision notes appended to the motion-keyword item, the
  `614e` judge-miss item, and the motion-transfer decision item. Applied by
  `local_agent/runtime/roadmap_20260926/_edit_todo_26d.py` (4 exact anchors,
  each matched once, refuses a second run).
- This file.

## Next in this session

Phase 2b (relax the gate + stale "Do not start videos" cleanup) and Phase 2c
(GVD "ask, don't guess" surfacing into the chat reply), each with its own
entry. Phase 3 is the other session's live work; this session will not edit
motion-transfer files while that session is active.
