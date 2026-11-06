# 2026-11-06b — `test_native_tool_calling` depended on git-ignored project data

Follow-up to `2026-11-06a` section 4, second bullet, which predicted the
suite would pass on the workstation because the durations file exists
there. It failed there too. Branch `claude/jolly-dirac-9impbq`. Id claimed
with `scripts/next_changelog_id.py`.

## 1. Cause

`test_multiple_calls_one_hop_and_named_results` drives two real
`duration_ladder` calls with `{"clip": "00B"}` / `{"clip": "00A"}` and
asserts each tool message starts with `[` (the ladder's JSON list). The
`clip=` form reads `outputs/equal_shares/audio_pass_durations.json`, and
`outputs/` is git-ignored (`.gitignore` line 48). Every checkout other than
the original main one, including the workstation's gateway worktree, has no
such file, the tool raises `ToolError("no duration row for 00B")`, the hop
records `ERROR: no duration row for 00B`, and the assertion fails. The
earlier "box-specific, data" diagnosis was right about the mechanism and
wrong about the scope: it is checkout-specific, not machine-specific.

The test is about native tool-calling plumbing (two calls in one hop, one
named result message each), not about this film's durations.

## 2. Change

`local_agent/test_native_tool_calling.py`, that one test: the two calls now
use `{"seconds": 10}` and `{"seconds": 12}`, the tool's documented
data-free form, with a comment saying why. The real tool still runs end to
end through `work/duration_ladder.py` (versioned since `2026-11-05b`); the
result is still a JSON list, so the assertions are unchanged. No production
code changed. The test file is 159 KB, more than this cloud session can
push whole, so the 7-line change travels as a patch applied and committed
from the workstation; this entry is pushed from here first.

## 3. Evidence (this Linux session, no `outputs/`)

    python test_native_tool_calling.py   Ran 118 tests ... OK   (was FAILED (failures=1))

`tools.duration_ladder({"seconds": 10})` returns `[\n  {\n    "rung": 0,
"nominal_seconds": 10.0, "frames": 243, ...`; the sibling SSE hop-index test
that also names `duration_ladder` keeps its `clip=` arguments because it
asserts only on event shape and already passed with the `ERROR:` content.

## 4. Unverified / next

- Not yet run on the workstation. Expected in the gateway worktree:
  `Ran 118 ... OK` (was `FAILED (failures=1)` there on 2026-11-06, see
  `2026-11-06a` section 5).
