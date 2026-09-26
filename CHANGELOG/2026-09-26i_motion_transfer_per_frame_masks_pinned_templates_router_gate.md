# 2026-09-26i — Motion transfer, CPU building blocks: per-frame character masks from DWPose keypoints (replaces the static left-half mask and "leftmost face" rule), pinned two-stage API templates + builder, a router gate so the row can only serve motion-reference shots, and the `animatediff_pose` promotion family registered; smoke/promotion **not run** because the motion-transfer session came back mid-build and owns the GPU

Roadmap prompt Phase 3, first chunk. Code and tests only: no GPU, no
ComfyUI call, no render, no download. Id claimed once with
`scripts/next_changelog_id.py`.

## 0. Coordination — read this before touching anything below

At 09:34 the motion-transfer session had been idle for 7 h 18 min (last file
02:16) and its 26g entry listed exactly these items as its own unfinished
"next", so this session started on them. At **09:45–09:48** that session
resumed: it wrote `local_agent/motion_transfer_render.py` (701 lines: job
runner, programmatic graph builder with a structural template hash,
InsightFace-based target choice → a per-job vertical band mask),
`local_agent/motion_transfer_faces.py` (InsightFace crop / faces / score
helper), a `tools.py` edit adding `render_video_from_reference` +
`video_reference_job_status` (`_edit_tools_26h_render.py`), and started a
live validation job `mtr_20260926_094720_c5cf3a` (63 frames, 5 windows,
backend starting at 09:48). Its artefacts are labelled **`26h`**, which is
this session's already-written download entry (`2026-09-26h_wan22_…`); the
next free id after this file is `j`. **Nothing of that session's was
touched.** This entry stops at the CPU chunk; the tool, the worker and the
live validation are that session's, and the GPU smoke + promotion below
were deliberately not started beside its render.

Where the two builds meet (for whichever session continues):

| item | that session (`motion_transfer_render.py`) | this entry |
|---|---|---|
| character selection | InsightFace faces on sampled frames, tracked by face centre; `target` = left/right/center/auto | DWPose body keypoints (the pose stage already produces them), tracked by body centre; selector = leftmost/rightmost/largest/index/nearest |
| IP-Adapter mask | one static vertical band per job (`mask_band_px`, `LoadImageMask`) | **one mask PNG per frame** (padded body box + head disc), loaded as a batch (`VHS_LoadImagesPath` → `ImageToMask`); IP-Adapter applies a mask batch per frame under AnimateDiff (`CrossAttentionPatch` indexes `ad_params["sub_idxs"]` when `mask.shape[0] >= full_length`) |
| face-detail selection | `ImpactSEGSOrderedFilter` pick from the face rank | the same node, with the rule derived from the tracked head (leftmost / rightmost / topmost / bottommost / largest), or `ImpactSegsAndMask` over the union body mask when no ordering isolates the character |
| template | built in code, hashed structurally | two JSON files under `local_agent/graphs/`, sha256-pinned, `{{TOKEN}}` placeholders |

The per-frame mask module is a drop-in: its input is the JSON that
`SavePoseKpsAsJsonFile` writes from the DWPose node the worker already runs.

## 1. `local_agent/motion_transfer_masks.py` (new, LF; PIL only)

- `load_pose_frames` / `frame_people`: parses controlnet_aux's POSE_KEYPOINT
  JSON (OpenPose body-18, `[x, y, c]` triples, pixel or normalised — both
  handled), drops skeletons under 15 % of the canvas height (the framed
  photo on the nightstand that DWPose read as a person, doc §6).
- `select_person(people, {"by": largest|leftmost|rightmost|index|nearest})`.
- `track_person`: nearest body centre frame to frame within 25 % of the
  canvas diagonal; a frame with no match carries the previous person and is
  counted as `carried`.
- `body_mask`: padded keypoint box (12 %) plus a head disc sized from the
  shoulder width, drawn at the render size (scaled from the DWPose canvas).
- `face_rule`: `{"mode": "ordered", "target": "x1"|"y1"|"area", "order":
  bool, "take_count": 1}` when the character's head is unambiguously the
  leftmost/rightmost/topmost/bottommost head (5 % margin) in every frame it
  shares with someone, `area`/descending when alone, else
  `{"mode": "union_mask"}`.
- `prepare(pose_json, out_dir, size=, selector=)`: writes `mask_00001.png…`
  directly in `out_dir` (so `VHS_LoadImagesPath` over it loads exactly the
  frame masks) and `union/union_mask.png`, returns a manifest record with
  sha256s, counts, people per frame and the face rule.

## 2. Pinned templates + builder

- `local_agent/graphs/motion_transfer_animatediff_stage1_pose_api.json`
  (sha256 `02bea262…63a5`): `VHS_LoadVideoPath` → `DWPreprocessor` (face
  **off**, hands on, xinsir sticks, 512) → pose/src `SaveImage` +
  `SavePoseKpsAsJsonFile`.
- `local_agent/graphs/motion_transfer_animatediff_stage2_render_api.json`
  (sha256 `0836f376…62ba`): the 26g recommended configuration — RealVisXL 5
  + `mm_sdxl_v10_beta`, context 16/overlap 4 pyramid, union-promax
  `openpose` 0.8 with VAE, PLUS FACE IP-Adapter 0.8/linear/V-only on the
  face crop with `attn_mask` from the per-frame mask batch, euler/normal 20
  steps cfg 6, Impact video face-detail (`face_yolov8m`, guide 384, max 512,
  feather 8/20, denoise 0.5) through `IPAdapterUnifiedLoaderFaceID`
  FACEID PLUS V2 (LoRA 0.6, v2 1.0, CPU). Node ids match the proof-of-concept
  runner so its manifests stay comparable.
- `local_agent/motion_transfer_graph.py` (new, LF): `PINNED` / `DEFAULTS`,
  `TEMPLATE_SHA256`, `build_stage1(...)`, `build_stage2(...)` (whole-token
  JSON replacement so numbers stay numbers, then in-string splice for
  `{{PREFIX}}`; refuses any unfilled token; validates ranges; swaps node 42
  for `ImpactSegsAndMask` + a one-image mask load in `union_mask` mode),
  `validate_graph(graph, object_info)` (the runner's live check, moved out),
  `node_classes`.

## 3. Router gate + promotion family

- `gvd_tool_router/router.py::_compatible`: a row may declare
  `limits["requires_capabilities"]`; every listed capability must be in the
  shot's required set, else `shot_lacks_required_capability:<cap>`. Without
  it an *active* motion-transfer row (capabilities motion_reference +
  identity_reference + narrative_identity) would be selected for any
  identity-mode shot and its template would render the pinned reference clip
  regardless of the manifest. Applied by
  `runtime/roadmap_20260926/_edit_router_requires_caps.py` (1 anchor).
- `gvd_tool_router/catalog_seed.py`: the animatediff row now carries
  `extra_limits={"requires_capabilities": ["motion_reference"]}` and its
  reason says the templates and masks exist and only the VRAM profile is
  missing ("ComfyUI-Advanced-ControlNet" kept, so `test_motion_transfer_plan`
  still passes). The two Wan rows were not touched (they belong to the other
  session's text edits; the 26h TODO line still asks for the Animate row's
  "weights missing" text to be updated).
- `gvd_tool_router/apply_profile.py` + `smoke_measure.py`: family
  **`animatediff_pose`** → `animatediff_sdxl_pose_ipadapter_unvalidated`,
  fixture `fixtures/animatediff_pose_smoke.api.json` (**not created yet, see
  §5**), prompt bound to node 16 `text`, seed to KSampler 22, deliverable
  `OutputBinding("video", "49", "gifs", "video/mp4")`, capabilities
  motion_reference + identity + narrative, quality identity 0.5 / motion 0.6,
  in the `allow_new_nodes` set. Applied by `_edit_gvd_animatediff_family.py`
  (10 anchors; one anchor corrected after a first refused run).

## 4. Tests

- `test_motion_transfer_masks.py` (12): size floor, normalised coordinates,
  all selectors, tracking a walker, carrying a missing frame, no-match
  error, mask geometry at render size, one PNG per frame + union in its own
  folder, JSON-file input, face rule alone / topmost / crossing → union.
- `test_motion_transfer_graph.py` (13): sha256 pins, documented placeholder
  sets, pinned settings present in the built graph, typed substitution in
  both stages, `area(=w*h)` mapping, union-mode swap, 13 bad-input cases,
  unfilled-token refusal, and offline validation of every node class that
  the 2026-09-25 live schema dump contains (the seven classes outside that
  dump are listed for the live check).
- `test_gvd_requires_capabilities.py` (4): seed row declares it; identity
  shot without a motion reference → blocked with the new reason; with one →
  selected; rows without the limit unchanged.
- `python -m unittest test_motion_transfer_masks test_motion_transfer_graph
  test_gvd_requires_capabilities test_motion_transfer_plan` → **46/46 OK**.
  `test_gvd_tool_router` + `test_gvd_engine_policy` after the router gate →
  **74/74 OK** (70.3 s; `runtime/roadmap_20260926/tests_p3_router.log`).

## 5. Not done — the GPU half, with the recipe

1. **Fixture.** Generate `gvd_tool_router/fixtures/animatediff_pose_smoke.api.json`
   from the graph the tool actually renders (the other session's
   `motion_transfer_render.build_graph` with its benign job's face crop and
   mask, or `motion_transfer_graph.build_stage2` with `prepare()`'s masks
   for the `02A` clip). It must reference files that exist on this machine,
   as the wan8 / tile_video fixtures do.
2. **Smoke.** With no render running: `preflight_execute` → owned backend
   with custom nodes → `python -m gvd_tool_router.smoke_measure --family
   animatediff_pose` (it needs 8188 up and Qwen :11436 down) → stop the
   backend. Expect ~14.7 GB peak over baseline for 24 frames (26a/26g).
3. **Promote.** `python gvd_tool_router/apply_profile.py --report <report.json>`
   → `animatediff_sdxl_pose_ipadapter_unvalidated` active with a local
   profile; `gvd_route_shot` on a manifest with `motion_reference_video`
   then selects it, and `execute_tool` would submit the fixture graph (as
   for every other promoted family: the smoke graph *is* the registered
   stage, bound on prompt/seed only).
4. Wire the per-frame masks into the worker if wanted (§0 table).

## Files

New: `motion_transfer_masks.py`, `motion_transfer_graph.py`,
`graphs/motion_transfer_animatediff_stage{1_pose,2_render}_api.json`,
`test_motion_transfer_masks.py`, `test_motion_transfer_graph.py`,
`test_gvd_requires_capabilities.py`. Edited (LF kept): `router.py`,
`catalog_seed.py`, `apply_profile.py`, `smoke_measure.py`. `TODO.md`
(CRLF): Phase 3 status lines.
