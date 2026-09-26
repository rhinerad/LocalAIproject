# 2026-09-05de — Farm Qwythos activity-trace live evidence

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05de**.

Closes the 2026-09-05cn gap: farm routing was only unit-tested
(`activity_from_sse` `backend=farm`) plus the chat-list FARM badge.
This pass drove a real Mac Qwythos turn and checked the GUI contract
against that stream. No Equal Shares. No `/api/send` GPU pin (that
path cannot farm-route; see surprises).

Receipts: `artifacts/benchmarks/2026-09-05_farm_activity_live/`
(`farm_direct.json`, `persist.json`, `gui_restore_dom.html`).

## Decide (live)

Farm `celery@Louises-MBP` snapshot `status=ok`, not stale.
`8188` closed at hop 0; GPU idle **73 MiB**.

| Call | backend | tier | model |
|---|---|---|---|
| `decide("auto", prompt=README heading, model=None)` | **farm** | farm | `richardyoung/qwythos-9b-abliterated:latest` |
| `decide("auto", model=PRIMARY 14B, same prompt)` | ollama | gpu | Huihui **8B** (pinned chat never takes the farm branch) |

Farm requires **`model is None` and `CAP_TOOL`**. Desktop
`POST /api/send` always pins a model before `agent.answer`, so a normal
GUI new-chat turn **cannot** emit `backend=farm`. That is why cn’s
pinned-14B send never showed farm cards.

## Live unpinned turn (real Qwythos)

`agent.answer(..., model=None, workspace=general)` with the 2026-09-05b
README-heading prompt. Wall **644.95 s**. Empty final reply; hop-limit
note.

| t (s) | SSE | Notes |
|---|---|---|
| **39.797** | first `route` `tier=farm` `backend=farm` | **39.8 s silent** before any card — 2026-09-05s: Qwythos runs **before** `emit("route")` |
| 39.813 | `tool` `list_tools` `{search:"read"}` | cpu-profile catalog |
| 39.828 | `tool_result` | observed |
| **129.922** | `route` farm again | ~90 s to next hop (warm-ish Qwythos) |
| 129.922 | `tool` **`read_file`** `{path: local_agent/README.md}` | file starts `# Local Agent` |
| 192.6–326.1 | three `read_artifact` hops | still `backend=farm` |
| 326.1 | farm route with **`gpu_busy: true`** | concurrent desktop 14B turn; 8188 later `listening`; `timeshare.path=farm_skip` |
| **421.938** | note `Mac Qwythos farm path unavailable; falling back locally` | then CPU 8B on `:11434` `num_gpu=0` |
| 644.766 | farm `route` again + **hop-limit** note | `last_tier` still **farm** |

`queued` was not on this turn (no media). Tool announce/result cards
did fire on the farm hops.

## GUI (8760 already on r79)

Did **not** POST `/api/send` for this prompt (would pin GPU and miss
farm). Persisted the captured SSE through `activity_from_sse` into chat
**`c099b0a149744f55`**.

`GET /api/chats` row: `last_tier: "farm"` → listing **FARM** (`.ctier.f`).
`GET /api/chat?id=c099b0a149744f55` restored `activity` beginning
`route`/`farm`/`richardyoung/qwythos-9b-abliterated:latest`, then
`tool_call`/`tool_result` for `list_tools` and `read_file`, later
`blocked` (hop limit) + `complete`. That is `openChat` → `mountActivity`
→ `lifeNode` (same mapping as live `stream()`). Reconstructed first
cards: `gui_restore_dom.html`.

No headless browser was attached to a live `stream()` of a farm turn,
because the desktop send path never leaves `model` as `None`.

## Surprises

1. **Pre-route silence 39.8 s** (then ~90 s between farm hops). Matches
   2026-09-05s; still not fixed (cn did not reorder Qwythos vs
   `emit("route")`).
2. **GUI pin vs farm Decision** — farm is unreachable from a normal
   desktop new chat.
3. Qwythos **did** native `tool_calls` (`list_tools`, `read_file`) but
   then **looped `read_artifact`** until hop 6; empty answer.
4. Mid-turn `gpu_busy` flipped true (other r79 GUI work + 8188 up). Farm
   hops kept `farm_skip` and did not claim the 5080; fallback used 8B
   CPU-only on the GPU Ollama port.

No router/GUI production change. Farm still not a registered chat pin.
