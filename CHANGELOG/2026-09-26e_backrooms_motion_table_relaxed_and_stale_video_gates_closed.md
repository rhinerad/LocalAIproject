# 2026-09-26e — Backrooms motion-keyword table relaxed (word-bounded vocabulary with a negation floor; row 265's wording now renders) and 22 stale "do not start videos" TODO lines closed against 2026-09-22j

Roadmap prompt Phase 2b. Operator decision 2 in `2026-09-26d`: relax. No
GPU, no VLM, no render: code, tests and `TODO.md` only. Id claimed once with
`scripts/next_changelog_id.py`. The motion-transfer session was rendering
(pass23 finished 01:54, pass24 started after) throughout; nothing of its was
touched.

## 1. The gate before and after (`local_agent/dspy_orchestrator.py`, LF kept)

Before: `mechanical_director_gate` required, for a Backrooms example, a
substring hit from `_CAMERA_KEYWORDS` **and** from
`_MOTION_KEYWORDS = (walk, walking, momentum, push in, push-in, tracking
forward, track forward, dolly, glide, advance, move forward)`. History row
265 (GVD-B01 `644b`, CHANGELOG 2026-09-25i) — `video_prompt` "The handheld
camcorder gradually moves along the hallway, panning slowly." — has neither
"walk" nor any listed phrase, so it scored 0.02; the clip it produced is
reviewed good and judges 1.00 / 1.00 / 0.80 offline (min 0.80 = the bar).

After:

- `_MOTION_KEYWORDS` keeps every old entry and adds plain motion verbs and
  camera moves: move/moves/moving/movement, pan/pans/panning,
  tracking/tracks, drift(s/ing), creep(s/ing), step(s/stepping) forward,
  approach(es/ing), travel(s/ing/ling), wander(s/ing), tilt(s/ing),
  turn(s/ing), sway(s/ing).
- Matching is **word-bounded** (`_MOTION_RE`), not substring: "remove",
  "improvement", "span" no longer read as motion (the old substring test
  would have passed "remove" via "move" had "move" been in the table, which
  is why it was not).
- **The floor**: `_MOTION_NEGATION_RE` blanks a negated motion phrase before
  matching — "the camera does not move", "no panning", "never moving",
  "without any camera movement" — so a prompt that echoes motion vocabulary
  while describing a static shot still fails with the same
  `backrooms clip missing a motion keyword` reason (the message now lists
  pan/moves and says a negated phrase does not count). The camera-keyword
  requirement and the `instruction_echo` check are unchanged, so the three
  things the gate existed for — an empty/echoed prompt, a static shot, a
  prompt with no camera at all — are still rejected.
- New `has_motion_keyword(text)` is the single entry point; the gate calls
  it. `_is_drone_or_cinematic` bypass, duration checks: unchanged. The gate
  still runs pre-render (25j).

Applied by `runtime/roadmap_20260926/_edit_gate_26e.py` (2 exact anchors)
plus `_edit_gate_26e_fix.py`: the first script was fed through a shell
heredoc that stripped its backslashes, so the two `re.compile` blocks were
first written without `\b` / `\s` (every probe returned False); the fix
script rewrote exactly those two blocks and asserts no control characters
remain. Both kept as the record.

Smoke (module import, no test harness):

| video_prompt | before | after |
|---|---|---|
| "The handheld camcorder gradually moves along the hallway, panning slowly." (row 265) | fail | **pass** |
| "Handheld camcorder walk forward down the hallway." | pass | pass |
| "pov camcorder push-in" | pass | pass |
| "handheld camcorder, the camera does not move, locked off on the wallpaper" | fail | fail |
| "handheld camcorder with no panning, static" | fail | fail |
| "handheld camcorder; remove the improvement" | fail | fail |
| "handheld first-person camcorder turns the corner" | fail | pass |
| "a still photograph" | fail | fail |

## 2. Tests (`local_agent/test_dspy_orchestrator.py`, CRLF kept; `_edit_gate_tests_26e.py`, 3 anchors)

- 25j's `test_backrooms_prompt_without_motion_keyword_skips_gpu` used row
  265's wording as its motionless example; it now uses "holds on the
  wallpaper; the camera does not move" (the negation floor) and still
  asserts `skipped GPU`, `video_path` None, render/prepare never called.
- New `test_backrooms_row_265_phrasing_now_renders`: the exact row-265
  `video_prompt` reaches `render_fn` with the built-in gate and no error.
- New `RelaxedMotionTableTests` (6): row-265 wording passes; pan / tilt /
  turn / drifting pass; three negated phrasings fail with "motion keyword";
  "remove the improvement across the span" fails; a prompt with motion but
  no camera keyword fails on the camera reason only; the instruction-echo
  floor still fires.

`python -m unittest test_dspy_orchestrator` → **48/48 OK** (16.2 s; was 40).
Log: `runtime/roadmap_20260926/tests_26e_orch.log`.

## 3. Stale TODO gates closed (`TODO.md`, CRLF kept; `_edit_todo_26e.py`, bounded region + 3 anchors, counts asserted)

CHANGELOG `2026-09-22j` (operator decision, START OVER) states: "The C-series
still-recovery items (C016–C027) and their 'Do not start videos' gates are
superseded; they do not block the fresh run", "the pending Flux smoke grant
`gpu_a38b751666c5` is stale … superseded", and "the hash-bound 204-still
approval no longer refers to a completed set". Each checkbox line below was
matched against that text before closing:

| closed (now `[x]` + "Superseded by 2026-09-22j START OVER …; closed 2026-09-26e") | count | section(s) |
|---|---|---|
| `- [ ] Do not start videos.` | 18 | C027 (14z), C024 last/start (14v/u), C023 last/start (14t/s), C022 last/start (14r/q), C021 last/start (14p/o), C020 last/start (14n/m), C019 last/start (14l/k), C018 last/start (14j/i), C017 last/start (14h/g), C016 last (14e) |
| `- [ ] Run and review the one bounded C026 recovery. Do not start videos.` | 1 | C026 (14x) |
| `- [ ] Next: C026 start Mode B recovery. Do not start videos.` | 1 | C025 (14w) |
| `- [ ] Formal hash-bound approval of the complete 204-still set remains pending; do not begin videos before it.` | 1 | C001 operator review gate (11a) |
| `- [ ] WAITING operator sidebar approve **gpu_a38b751666c5** then retry Flux smoke PNG` | 1 | Grok 2026-09-06k |

22 lines. The script asserts the C016–C027 region holds no other open item
afterwards.

**Left open on purpose:**

- `C003_last is paused after two reviewed whole-frame failures … do not
  regenerate by seed alone` (2026-09-11q) — explicitly excluded by the
  prompt; verbatim, asserted present.
- C002 "Operator visually reviews and explicitly accepts or rejects that
  exact C002_start hash. Do not proceed to C002_last before this decision."
  (2026-09-11m). 22j's body says the restart is "from the beginning (C001
  forward)" but TODO's own START OVER summary says "C016 forward" and names
  only C016–C027; with the two texts disagreeing on whether C002 is inside
  the restart, the line is not closed here. Operator: confirm and it can go.
- The four "After Rhine restarts …" items (06k/l/n, 07b) are server-restart
  chores, not per-clip video gates; not touched.

Also flipped: the motion-keyword decision line in the GVD judge section is
now `[x]` with a pointer here.

## Not changed

- `evaluate_live_candidate`'s order, `passes_curriculum`, the camera table,
  `instruction_echo`, `media_accuracy_gate`: untouched.
- No MIPRO history row rescored; row 265's 0.02 stands as recorded evidence.
- `git` warns `dspy_orchestrator.py` "LF will be replaced by CRLF" — that is
  the repo's autocrlf setting, not this edit; the file on disk is LF as before.
