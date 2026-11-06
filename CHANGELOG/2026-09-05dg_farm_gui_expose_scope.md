# 2026-09-05dg — Should the GUI expose farm-eligible routing? (scope only)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dg**.

Scope only. No `server.py` / `index.html` / `router.py` / `APP_REVISION`
change. Follows `2026-09-05de` (live farm stream never went through
`POST /api/send`) and `2026-09-05cw` (pre-Qwythos route emit still
unbuilt). Does not implement the Qwythos `read_artifact` loop (Red,
this session).

## Recommendation

**Do not expose farm in the GUI now. Worth exposing later**, after two
gates, as an **explicit unpinned mode** — not by making today’s Auto
quietly skip the pin.

Do **not** leave farm as a forever-hidden `agent.answer(model=None)`
trick. The Decision is real (`CAP_TOOL` + farm-up → Mac Qwythos,
`farm_skip` timeshare). Hiding it forever means the desktop product
cannot use the Mac for the exact turns it was built for. Exposing it
*today* would show the operator a 40 s blank, ~90 s hops, and the
live 645 s empty hop-limit from 2026-09-05de.

**Gates before any GUI farm path:**

1. **Qwythos `read_artifact` loop understood or fixed** (Red). Live de:
   `list_tools` → `read_file` (correct heading) → three
   `read_artifact` hops → farm miss → CPU 8B → hop-limit, **empty
   reply**. That is not a routing bug; it is a bad agent loop. More
   GUI traffic would just surface it more often.
2. **Pre-wait honesty from 2026-09-05cw**: `progress` “Waiting on Mac
   Qwythos” plus a **proposal**-stamped farm `route` *before*
   `try_qwythos_on_farm`; keep the post-wait `route` as observation.
   Without that, v1’s proposal/observation stamps would lie (silence
   looks like a hang; a late farm `route` looks like the turn *was*
   farm the whole time).

## What “Auto” is today

Desktop `POST /api/send` (`server.py` `_send_turn`): new chat with no
model → `router.decide(prefer)` **without the user prompt** → pin that
tag → `agent.answer(..., model=conv["model"])`. Pin is sticky
(`set_model` will not switch).

Farm in `router.decide` (`model is None and capability == CAP_TOOL and
not skip_farm and prefer != "cpu" and _farm_reachable()`). A pinned
Huihui/Coder/DeepSeek chat **never** takes that branch (de: same
README prompt, pinned 14B → GPU 8B).

So Auto is **“pick a local model, then stay there.”** It is not
“may use farm.” Quietly omitting the pin would change Auto’s meaning
and surprise anyone who expects Huihui-14B on a new general chat.

## Options considered

| Path | What it is | Verdict |
|---|---|---|
| **A. Explicit “Auto (may use farm)”** | New picker value: chat stays **unpinned** (`model` null/empty). Each turn `decide(prompt, model=None)`. CAP_TOOL+farm-up → Qwythos; else local as today. Listing already has FARM (`last_tier`). | **The later shape.** Honest, opt-in, does not rewrite pinned chats. |
| **B. Leave farm non-GUI** | Only `agent.answer(model=None)` / benches / phone-if-ever. | **Now, until gates 1–2.** Not forever: farm_skip exists so lightweight tools do not load the 5080. |
| **C. Make Auto unpinned for everyone** | Drop the pin in `_send_turn`. | **No.** Breaks “this chat is 14B.” Farm would appear on ordinary tool asks without consent. |
| **D. Pin Qwythos as a chat model** | Picker tag `richardyoung/qwythos-9b-abliterated:latest`. | **No.** `model is not None` skips farm; that pin would try **host** Ollama, not Celery. Qwythos is not on the 5080 (`_timeshare_would_load_host_gpu` already false for that tag). |

## UX honesty (v1 trace)

v1 (`2026-09-05cn`) stamps `route` as **observation**. Farm wait is
**before** that emit (`2026-09-05s` / `cw` / live de **39.8 s** to first
card, **~90 s** between farm hops). The only live text in that window
is client `Working…` / `Request received locally`. That is a hang.

A GUI farm mode that shipped without cw would violate v1’s own rule:
do not show a plan as proof, and do not leave a real wait unlabeled.
Minimum for later expose: cw’s pre-wait **proposal** farm card +
ticking elapsed (already live-only). Do not tell the operator “Mac
worker accepted Qwythos” until the post-wait observation route.

Hop index (cw) is useful once farm hops are 90 s apart; not a third
gate by itself.

## GPU timeshare / thermal

**Do not block or deprioritize farm-eligible mode because the 5080 is
busy.** That is the point of the farm_skip branch
(`_maybe_comfy_timeshare`): unpinned CAP_TOOL + farm-up does **not**
`POST /free` or load host GPU. Live de: later hops had `gpu_busy:
true`, `8188 listening`, `timeshare.path=farm_skip`; Qwythos still
ran on the Mac.

5080 thermal / ComfyUI owners should not disable farm. If anything,
GPU-busy is when farm is **more** useful.

Deprioritize only on **Mac/farm health**: stale `farm_status.json`,
`should_route(qwythos)` false, or summarize-queue saturation
(Qwythos shares the Mac `summarize` queue, concurrency=1, with
prefetch summarize). That already falls through to local
(`skip_farm` / “farm path unavailable”). GUI farm mode should keep
that fail-open, not add a 5080 veto.

`prefer=cpu` already skips farm. Keep that.

## Interaction with the loop bug

Exposing farm now = more operators on the de path: catalog
`list_tools`, a correct `read_file`, then artifact churn to hop 6,
empty answer, `last_tier=farm` on a failed turn. The FARM badge would
look like success.

Red’s loop investigation is a **hard gate**, not a polish item.

## Later PR shape (not this ticket)

When gates 1–2 pass, one GUI PR:

- Picker: **Auto (may use Mac farm)** vs pinned models. New chats only;
  do not unpin existing Huihui chats.
- `_send_turn`: that mode stores empty/`null` model and passes
  `model=None` into `agent.answer`.
- cw pre-wait proposal route + progress label; post-wait observation
  route unchanged.
- No 5080 busy veto; keep existing farm_status fail-open.
- Tests: GUI create-unpinned; pinned 14B still not farm; activity
  stamps proposal then observation on a mocked Qwythos wait.

Until then: farm stays a **capability with a live receipt**
(`2026-09-05de`), not a desktop default.

No code, no GPU, no Celery kickstart.
