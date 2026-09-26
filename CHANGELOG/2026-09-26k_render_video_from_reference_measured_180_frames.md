# 2026-09-26k — `render_video_from_reference`: measured a 180-frame (15-window) run; cap raised 64 → 180 with a free-RAM refusal (system RAM, not VRAM, bounds length); fixed the identity check overflowing the Windows command line on long clips

Operator, in chat: "do the measured longer run". Continues `2026-09-26j`. Id
claimed once with `scripts/next_changelog_id.py`. Benign inputs only; nothing
downloaded or installed.

## 1. Choice of clip

The longest benign clips on disk are 15.08 s (`ComfyUI-Shared/output/story/*`,
163 probed read-only). The 26C–26F scene clips contain cuts
(`runtime/motion_transfer_20260925/_preview_long/candidates.png`), and 25B
has a crowd of audience faces. `VOX_HOUSING_REPRESENTATIVE/attempt_1_00001_.mp4`
is one continuous take of a single woman walking down a corridor, phone to
her ear, gesturing with an envelope (`candidates_vox.png`): real body motion,
no cuts, one face. Rendered at **12 fps → 180 frames, 15 context windows**
(the frame count that matters for memory and time; ≈ 22.5 s at 8 fps).
Character: the Kent master copy (a gender-swapped recast).

## 2. Measured run (`runtime/motion_transfer_20260925/tool_measure_long_26k.py/.log/.json`)

The driver raised `motion_transfer_render.MAX_FRAMES` to 180 **in its own
process only**, then called `tools.call("render_video_from_reference", …)`
like the agent does (gate mode `allow`, operator chat idle), polled the
status tool, and sampled system RAM every 5 s.

| | |
|---|---|
| job | `mtr_20260926_113356_a6c884`, prompt_id `cced1789-85e2-4f9a-ba93-870d4728ae18`, history success |
| analysis | 1 person, no mask, detail pass on the largest face through FaceID Plus V2 |
| frames planned = source = pose = generated = detailed | 180 = 180 = 180 = 180 = 180; `verified_outputs: true` |
| final mp4 | `video_fd_00001.mp4`, h264 768×448 12 fps, 180 frames, 15.000 s, 1 220 019 B, sha256 `01a611e1a8b46a2a62e9fd6792ca3f0b7b2ffb9eaf25851bdda20416f0b87b8e` (undetailed `video_00001.mp4` 1 238 091 B, `892c3fe6…`) |
| files | 720 outputs, all present with sha256 |
| backend start / render / wall | 103.0 s / **1279.0 s (7.1 s per frame)** / 1427 s |
| GPU during render (626 samples) | peak **15 881 MiB** (same ceiling as 24–63 frames; context windows keep VRAM flat), peak **74 C** (ceiling 82) |
| system RAM (285 samples) | baseline 15.41 GB → peak **29.84 of 30.9 GB** (+14.4 GB) |
| identity | the job's own check failed (§3); recomputed with the fix: **mean 0.343**, min 0.231, 180/180 detected (frames 1–60: 0.358, 61–120: 0.367, 121–180: 0.303) → `identity_check_rescore_26k.json` beside the untouched `manifest.json` |

**Visual check** (`long_26k_frames.png`: source vs detailed, every 12th
frame; `long_26k_heads.png`: native head crops at f1/45/90/135/180):
- Every sampled frame is upright.
- Identity is strong and steady: the same Kent-like man (receding dark hair,
  moustache, round face, teal cardigan, the reference's raised-eyebrow
  expression) from f1 to f180.
- The motion follows the source: phone to his ear, walking toward the camera,
  the envelope at the start and end.
- **New:** the hallway's lighting and colour drift across windows (warm
  orange ↔ cool green-grey), gradually rather than as a hard cut.
- My frame-level judgement, not acceptance.

## 3. Bug found and fixed: identity check on long clips

With 180 detailed frames the runner passed every absolute path to the helper
on one command line: 38 340 characters, more than Windows allows (`WinError
206: The filename or extension is too long`). The render and every other
check were unaffected; `identity_check` came back `available: false`.

- `motion_transfer_faces.py`: `faces` and `score` accept `--frames-file` (one
  path per line), mutually exclusive with `--frames`.
- `motion_transfer_render.py`: the job writes `identity_frames.txt` and passes
  that file instead.
- Proven on the real 180 frames via the runner's own `_helper` (the rescore
  above), and inside a real job in §5.

## 4. Cap and RAM guard

- `MAX_FRAMES` 64 → **180** (measured).
- RAM, not VRAM, is the limit. `ram_needed_gb(frames)` = 14.4 GB × frames/180
  + 1.5 GB margin (15.9 GB at 180 frames, 6.5 at 63). `ram_check` uses psutil
  `available`.
- Two refusals: the tool refuses before anything is spawned (nothing created)
  and the job refuses before preflight (`manifest.ram_at_start` recorded), each
  with a message naming free vs needed GB.
- A whole 70 s clip at 8 fps (≈ 565 frames) projects to ~3× the measured RAM
  and does not fit one job on this 31 GB machine; it needs sections (each
  generates its own room look) or more memory.
- `tools.py` (LF; `_edit_tools_26k_cap.py`, 6 exact anchors, mtime re-checked,
  last edited by me at 09:45): description and schema say 180 frames and the
  RAM rule; RAM refusal before the gate; estimate recalibrated
  (`ceil(frames × 9 s) + 2…15 min backend`), with `ram` in the start result.
  The note now says "about 7-9 seconds per frame".
- Status-tool note updated the same way.

## 5. Final-code live check (`tool_validation_26k_final.py/.log`)

Job `mtr_20260926_120504_9eb315`: the hallway clip, start 6 s, 2 s → 16
frames, face detail on, target auto. Prompt `4e31b152-943b-45d7-b20f-97ac0280805e`,
history success.
- Tool RAM check `{ok, 17.1 GB free, 2.8 GB needed}`; the job recorded
  `ram_at_start` `{ok, 17.2, 2.8}`.
- `verified_outputs: true`, 16 frames at every stage; final `video_fd`
  2.000 s, sha256 `f4e750f4bc0307a948b09c829fa19113be0e6045a873ca50089cfa2bdb4db8e7`;
  64 files with sha256.
- **Identity check through `identity_frames.txt`: 16/16, mean 0.277**, min 0.255.
- GPU peak 14 594 MiB, 67 C; backend 149.2 s, render 270.2 s.

## 6. Text and tests

- `_edit_26k_text.py` (anchors verified, mtime re-checked, line endings
  kept): `local_agent/motion_transfer.py` AnimateDiff `why` (180 frames,
  RAM-bounded); doc §7 limits (measured numbers, RAM bound, the 70 s
  projection, background drift); `TODO.md` note.
- `test_motion_transfer_render.py`: 180-frame refusal text, the measured
  180-frame case allowed, RAM need scaling and `ram_check` with a fake psutil,
  the tool refusing on short RAM with nothing spawned or created, and the
  helper's `--frames-file` parsing and exclusivity. With
  `test_remote_tool_allowlist` and `test_motion_transfer_plan`: **62 OK**.
- Full non-live suite: see §7.

## 7. Full suite

`python -m unittest $(ls test_*.py | grep -v _live | sed 's/[.]py$//')` from `local_agent/`
(`runtime/motion_transfer_20260925/full_26k.log`): **Ran 1754 tests in 426 s, OK (skipped=2), exit 0.**

## Not done

- Longer than 180 frames is unmeasured and projected not to fit RAM here.
- Background drift across many windows is not addressed.
- GVD VRAM profile / promotion still not done (the numbers above are what a
  profile would carry: 15.9 GB VRAM ceiling, RAM scaling).
- The GUI server must be restarted to load the new `tools.py` (as in 26j).
