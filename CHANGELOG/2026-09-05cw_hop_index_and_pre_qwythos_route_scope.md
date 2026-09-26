# 2026-09-05cw — Hop index + pre-Qwythos route emit: scope only

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05cw**.

Scope only. No `agent.py` / GUI / `APP_REVISION` change. Follow-up to
`2026-09-05s` (deferred cut) and `2026-09-05cn` (v1 shipped without
this). Does not change farm wait, Celery, or Qwythos keep_alive.

**Recommendation: worth building later** as one small PR, not now.
Agent-side is contained; the cost is wire+GUI+fallback semantics, not
farm reliability.

## Where the silence is (live hop loop)

`agent.answer` `for hop in range(MAX_TOOL_HOPS + 1)` (`agent.py`
~1828). Inside each hop, after `router.decide` / reuse of `hop0_route`
and `apply_hop_profile`:

1. If `route.backend == "farm"`: **block** on
   `farm_offload.try_qwythos_on_farm` (~1912). No SSE yet.
2. On empty/error: **re-`decide(skip_farm=True)`** (~1926) — route may
   become local GPU/CPU. Then a `note` about fallback.
3. **Then** `emit("route", json.dumps(route.as_dict()))` (~1941) and
   `progress` review.

So the GUI’s first `route` is the **post-wait** decision. A successful
farm hop is silent for the whole Celery+Ollama wait (cold ~45 s,
`2026-09-05o`; caller ceiling `QWYTHOS_TIMEOUT_S=90`). A failed farm hop
never shows farm at all — only the local fallback.

`try_qwythos_on_farm` already returns None and never raises; the hop
loop already falls back. This cut must not change that.

A second `emit("route")` already exists later in the same hop for
14B→8B `fallback_after_primary_failure` (~2051). Two route events per
hop are therefore an existing pattern for GPU, not for farm.

`hop` is already a loop integer and a tracing span attr
(`tracing.span("hop", hop_index=hop)`). It is **never** put on SSE
(`2026-09-05q` table). Action-resolver / folderless-render / Sonic Pi
early returns emit `tool`/`tool_result` **outside** the hop loop and
often with **no** `route` (`2026-09-05cn` live list_dir path).

`emit` is a two-line nested helper (~1508) that forwards
`on_event(kind, payload)`. Payloads are strings: JSON for
`route`/`progress`/`tool`, raw text for `tool_result`/`token`/`note`.

## 1. Adding `hop` to existing kinds

**Where to thread it.** Do **not** edit every `emit("tool", …)` site
inside `_execute_plan`, prefetch, and the hop body. Wrap `emit`:

```text
current_hop = None  # outside the loop
def emit(kind, payload):
    if on_event:
        on_event(kind, _with_hop(kind, payload, current_hop))
for hop in range(...):
    current_hop = hop
    ...
current_hop = None
```

JSON kinds (`route`, `progress`, `tool`) get `"hop": N` merged into
the object. Text kinds (`tool_result`, `token`, `note`) cannot grow a
field without becoming JSON — **leave those payloads unchanged** or
the GUI/parser breaks. Hop grouping for tools is then: last `route` /
`progress` / `tool` announce carries `hop`; `tool_result` inherits
from the preceding announce (v1 already pairs announce→result).

**Surface area (contained if done that way):**

| Layer | Touch |
|---|---|
| `agent.py` | emit wrapper + `current_hop`; ~15–25 lines. Early-return tools stay `hop: null` (correct: no hop). |
| `server.activity_from_sse` | copy `hop` when present; ignore if missing (old clients). |
| `index.html` | optional `data-hop` / group label; who-line can ignore it. |
| `APP_REVISION` | **bump** — transport-visible extra on JSON kinds (`2026-09-05q` B). |
| Tests | `test_activity_trace` + one `agent.answer` `on_event` log (`test_native_tool_calling` style). |

Not a large rewrite. Do not put `hop` on `token` (high volume, GUI
does not persist tokens as cards). Do not add `trace_id`.

## 2. Route emit before the Qwythos wait

**What it requires.** After `decide()` when `backend == "farm"`,
**before** `try_qwythos_on_farm`:

- `emit("route", farm_decision)` **or** `emit("progress", {stage:
  "decide", label: "Waiting on Mac Qwythos"})` plus a route.
- Leave `try_qwythos_on_farm` call/timeout/fallback **byte-identical**.
- Keep the **existing** post-wait `emit("route")` as the confirmed
  decision (farm success: same dict; farm miss: skip_farm local dict).

**Does the shown route change?** **Yes, on the miss path, and that
already happens internally.** Today the operator never sees the farm
attempt. After this cut they would see `tier=farm` then, if empty or
error, `note` + a second `route` with local GPU/CPU — the same
sequence as the existing 14B→8B second `emit("route")`.

Risks:

- **Who-line flip.** v1 uses the last `route` as the stamp. A 45 s
  “FARM · qwythos” chip then switching to “GPU · 14B” is truthful if
  the first card is `source: proposal` / “attempting farm” and the
  second is `observation`. If both are stamped `observation` (v1
  default for `route`), it looks like the turn *was* farm and then
  *was* GPU. Stamp the pre-wait emit as **proposal**.
- **False farm health.** `decide()` farm means `farm_status.json` was
  ok **at decide time**, not that Celery will answer. Showing farm
  before the wait is “we are about to try,” not “Mac accepted.” Do
  not reuse the cn copy “Mac worker accepted Qwythos” on the
  pre-wait event.
- **No change to fallback correctness.** skip_farm re-decide stays
  after the wait. Do not skip the wait. Do not emit a local route
  speculatively.

A `progress` “Waiting on Mac Qwythos” **without** a farm `route` is
the smaller UX fix (closes silence, no who-line lie). Combining it
with a proposal-stamped farm `route` is better and still small.

## Why not now

v1 (`2026-09-05cn`) just shipped; the live farm-up path was **not**
exercised (pinned 14B). Hop grouping and pre-wait route need an
`APP_REVISION` bump and GUI rules for **two** `route` cards. Farm
timing/reliability must not move. The agent delta is small; rushing
it into the same week as v1 is how proposal vs observation gets
wrong.

**Later PR (when farm-up turns are the pain):** (1) emit wrapper +
`hop` on JSON kinds, (2) pre-wait `progress` + proposal `route`, (3)
keep post-wait observation `route`, (4) tests that `on_event` sees
farm route before the mocked Celery wait and local route after
`skip_farm`. No `farm_offload` timeout change.

No code, no GPU, no Celery kickstart.
