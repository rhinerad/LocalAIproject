# 2026-09-25v — Motion transfer identity, no download: a tight face crop of the character still fixes the 24-frame identity drift; an IP-Adapter attention mask confines colour bleed; adapter strength makes no difference; late-clip softening remains

Continues `2026-09-25u`. Operator, in chat: "try the no-download identity
tuning first". Nothing downloaded or installed. Id claimed once with
`scripts/next_changelog_id.py`. Benign inputs only; Equal Shares evidence
read, not changed.

## 1. Cause found by inspection

The character still used since 25s, `mt_poc_character_kent_v1.png` (copy of
the Kent master, 1672×941, sha256 `be5a186f…`), is a **full-body shot in a
hotel lobby**. His head is ~110×140 px (x 800–910, y 55–195). The PLUS FACE
IP-Adapter's CLIP-ViT-H encoder center-crops to a square and resizes to
224 px, so the face reaches it at roughly 15 px. The adapter was mostly
encoding "man in a lobby".

## 2. New inputs (new files in the owned input dir `work/runtime/image_render_runtime/input/`; nothing overwritten)

- `mt_poc_character_kent_face_v1.png`: crop (755, 30, 955, 230) of the
  master → 448×448 Lanczos; sha256
  `623da8288bd38315b73322d19fc59071d1f3921f401e5a6c483ea975cf4ec132`.
- `mt_poc_ipa_mask_left_v1.png`: 768×448 L, white on x < 400 (the man stays
  in the left ~52 % of this clip for all 24 frames); sha256
  `5b8c69940f7be5b7ddead643c65d78bd9ecb4bacb3a450603568ef46f5f4321b`.

## 3. Runner (`animatediff_v2v_poc.py`, CRLF kept; `_edit_runner_25v_ipa.py`, exact anchors, refuses a second run)

`--character`, `--ipa-weight`, `--ipa-weight-type`, `--ipa-embeds`,
`--ipa-mask` (core `LoadImageMask`, red channel → `IPAdapterAdvanced.attn_mask`).
The manifest records weight, weight type, embeds scaling, and the mask file
with its sha256. Defaults reproduce every earlier pass.

## 4. Runs (owned backend; operator chat idle and chat model unloaded before starting; preflight owner + port + thermal; owner released after each)

All as `pass15_ad24_core` (24 frames, AnimateDiff `mm_sdxl_v10_beta`, two
16-frame windows, union openpose, DWPose face off + xinsir sticks, seed
20260925, 768×448) except the column shown. Each run: history `success`, 72
output files present with sha256 in `animatediff_v2v_manifest_<tag>.json`,
mp4 h264 768×448 24 frames.

| tag | character | mask | weight / embeds | prompt_id | render | peak MiB | mp4 sha256 |
|---|---|---|---|---|---|---|---|
| `pass17_id_facecrop` | face crop | — | 0.8 / V only | `68d3cf09-37c1-4be2-b377-b435cdf2738e` | 308.9 s | 15 902 | `3b2d05d364288b1b97c85196fac31e21735b2b3deb1f24701fcc5dadba8c3e90` |
| `pass18_id_face_mask` | face crop | left 400 px | 0.8 / V only | `0f94e239-5898-432e-b239-bdc34703272b` | 306.6 s | 14 942 | `149e8fbb5076c5cee61d3b06e65010cbe0c138e7be5721585fd009d26e195db4` |
| `pass19_id_face_mask_kv10` | face crop | left 400 px | 1.0 / K+V | `13c61fea-dfdb-49d1-9752-e2f3001e4733` | 260.6 s | 15 902 | `31f60191ec42cde7501bf1705a526a99836456c0ca408c0570f5dfb481c867e6` |

Backend start 85–141 s; GPU 29–47 C.

## 5. Visual check

Native-resolution head-region crops (x 100–420, y 0–260, **no scaling**) of
frames 1/8/14/20/24: `id_25v_p15_vs_p17.png`, `id_25v_p17_vs_p18.png`,
`id_25v_p18_vs_p19.png` (made by `_id_sheet.py`). Full frames 1/8/16/24 of
p15/p17/p18 (orientation and scene only): `id_25v_full_p15_p17_p18.png`.

- **p15 → p17 (face crop): the decisive change.** p15's man turns into a
  long-haired, older, woman-like figure from about frame 13. p17 stays a man
  with short dark hair, a receding hairline and a moustache, in a teal
  cardigan over a light shirt, from frame 1 through frame 20, close to the
  reference. At frame 24 the face is rounder and younger and the moustache
  exaggerated. Side effect: the room takes on the crop's warm brown
  background.
- **p17 → p18 (mask):** the man is essentially the same. The brown bleed stays
  on the left, and the woman's side returns to p15's blue-green palette. The
  woman keeps grey curly hair and no moustache (the 25t body-only runs had put
  a moustache on her).
- **p18 → p19 (weight 1.0, K+V):** nearly indistinguishable. Adapter strength
  is not the limit.
- All frames upright; the man follows the reference (leans in, straightens,
  leans back in); room and bed continuous across the window seam.
- These are my frame-level judgements, not acceptance; the operator judges
  likeness.

Not run: a second reference view. The film's
`outputs/equal_shares/references/ensemble_cast_master_v1.png` shows Kent
face-on again with a ~60 px face, so it adds no new angle.

## 6. Text updated

`_edit_25v_text.py` (every anchor verified before any write; line endings kept):
- `local_agent/motion_transfer.py` (LF): AnimateDiff `why` gives the
  face-crop rule and the mask, instead of "identity is the open problem".
- `local_agent/gvd_tool_router/catalog_seed.py` (LF): seed row reason; row
  stays disabled.
- `docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md` (CRLF): new §6e.
- `TODO.md` (CRLF): note under decision option (c).

Tests: `python -m unittest test_motion_transfer_plan test_gvd_tool_router
test_queued_analysis_honesty`: **89 OK** (`tests_25v.log`). Full suite not
re-run: text strings only since the 25u full run (1631 OK).

## Not done / next

- Late-clip softness and drift on head turns. No-download next step: a
  per-frame face-detail pass (larger build; flicker risk). Download options:
  FaceID weights, or Wan 2.2 Animate. Both are the operator's call.
- A template needs a per-frame character mask (e.g. from DWPose person
  boxes). The static left-half mask fits only this clip.
- Still no pinned template, GVD VRAM profile, promotion, or
  `render_video_from_reference` tool.
