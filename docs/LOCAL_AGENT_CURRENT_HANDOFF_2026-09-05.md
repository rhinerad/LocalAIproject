# Local Agent current handoff — 2026-09-05 (evening)

## Read order

1. `CLAUDE.md` — binding safety, evidence, thermal, and paused-render rules.
2. This handoff — current general-agent state as of **2026-09-05 evening**,
   organized by thread. It **supersedes** the earlier same-day snapshot
   (`CHANGELOG/2026-09-05br_current_handoff_2026-09-05.md`), which stopped
   around letter `bs` and is now stale.
3. `local_agent/README.md` — product/runtime architecture.
4. `TODO.md` — authoritative execution queue.
5. `CHANGELOG/README.md` then the lettered `CHANGELOG/2026-09-05*.md`
   files (through `do` plus this `dp` handoff).
6. `HANDOFF_STATUS.md` — generated mechanical snapshot. Regenerated as
   part of this refresh via `python scripts/write_handoff_status.py`.

Yesterday: `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-04.md`.

## Current state

Equal Shares remains a **preserved, paused** specialist profile. Do not
resume its audio pipeline, launch a Stage-1 render, or alter
evidence/manifests. The live product is the localhost general-purpose
assistant (`127.0.0.1:8760`).

`APP_REVISION` is **`2026-09-05-queued-activity-r80`** (`server.py`).
That bump is the queued-media restamp (`dn`), after activity-trace v1
`…-activity-trace-v1-r79` (`cn`).

Unlike the morning handoff’s “several threads waiting on go,” several
of those have since **shipped or live-verified**, and a few new ones
are mid-flight. The farm is still **one Mac spoke**. Pixel G10 is the
main operator-in-progress edge item. Encrypted archive is waiting on
the operator’s SHA-256 check, then unplug D:.

---

## Thread A — Visible activity trace

**Done**

- Design `q`/`s`. v1 GUI shipped `cn` (`APP_REVISION` r79): SSE
  `route` / `progress` / `tool` / `tool_result` / `note` / `queued` /
  `error` / `done` → expandable lifecycle cards. Plans stay
  “Proposal — not proof of execution.” Tool args redacted. Persist
  `activity` on the assistant message; restore on `openChat`.
- Live cards `da`: failed-tool (`Observed error`), permission-wait,
  queued-media announce. Farm Qwythos live stream `de`: first `route`
  at **39.8 s** (Qwythos still waits **before** `emit("route")`);
  tool announce/result cards did fire on farm hops. Desktop
  `POST /api/send` **pins a model**, so a normal GUI new-chat turn
  **cannot** `backend=farm` (farm needs `model is None` + `CAP_TOOL`).
- **Qwythos empty hop-limit answer** was not “9B is dumb”:
  `dj` diagnosed a `prune_large_text` / `read_artifact` loop
  (4000-char slice > 2400-char prune budget → nested pointers until
  hop 6). **`dl` shipped:** do not prune `read_artifact` results.
  117 tests OK. No CAP_LOGIC / farm-routing change.
- **Queued-media restamp `dn`:** watcher never talks to chat SSE.
  Reconcile on `GET /api/chat` + poll while an announced queued card
  is on screen. Terminal jobs become `state=result` or `error`.
  `APP_REVISION` r80.

**Open / this round**

- Hop-index on SSE + **pre-Qwythos** `emit("route")` — scoped `cw`,
  **not built**. Worth a later small PR (wire+GUI+fallback semantics).
  Must not change `try_qwythos_on_farm` fail-closed fallback.
- Orange `tracing.py` SQLite logger is a **sibling**, already closed
  (`l`–`ap`). No `trace_id` on SSE. No Phoenix viewer.

---

## Thread B — Farm

**Done**

- Still **one spoke**: Louise’s Mac `10.90.90.2` /
  `celery@Louises-MBP`. Re-audited `bi` then `dc` with live
  `farm_health`, overlay, and credential files. `hub.conf` one
  `[Peer]`; only `.env.mac_worker.generated`. Not a failed join of
  the other 3+ LAN boxes — **never started**. Pixel is a different
  overlay (`10.90.91.0/30`), not Celery.
- Mac keep_alive **30m** live (`o`, `aa`, `aq`/`ar`): LaunchDaemon
  `OLLAMA_KEEP_ALIVE => 30m`.
- Semantic judge **v1** workstation `bo` (advisory, default **off**,
  extra flags `bad_reasoning` / `weak_inference_on_vague_request` /
  `plausible_wrong_answer`). **`dm`:** live Mac worker now
  **registers** `judge_transcript_semantic` (code copy + restart;
  `.env` untouched; control still defaults off). No live chat was
  judged.
- Dashboard LAN bind **reviewed** `dk`: `:8765` on
  `192.168.50.208` is the **coded default** (never loopback, never
  `10.90.90.x`). GET-only, **no auth/TLS**. Does not submit Celery
  jobs. Redis stays loopback + tunnel-relay. LAN is for a browser on
  another `192.168.50.x` host.

**Open / this round**

- Dashboard bind/hardening follow-up from the EOD sweep (`dh` item 4)
  — review landed; a bind change was **not** in `dk`. Treat any LAN
  exposure of `:8765` as known, not accidental.
- GUI exposing farm-eligible routing: scoped **later, not now, not
  never** (`dg`). Farm is unreachable from a pinned desktop send.
- Multi-node expansion and the 10-node cluster plan: deferred (see
  back-burner).

---

## Thread C — Encrypted archive

**Done**

- Runbook `docs/ENCRYPTED_ARCHIVAL_RUNBOOK.md`. Primer `bk`. Disk
  map: A: Toshiba 16 TB (sources), C: Lexar NVMe, D: **Seagate
  Portable USB** disk 2 UniqueId `3E543346485A464B` (~1.2 TB free) —
  a real second spindle (`bu`/`by`/`cc`).
- Five-field local-only `ARCHIVE_DECISION.md` (gitignored; tree has
  no `.git`). First-pass roots: `outputs/equal_shares/`,
  `outputs/stories/`, `docs/GOLDEN_REFERENCE/`, Desktop Equal Shares
  packs. **Not** `ComfyUI-Shared\output`.
- Restic **0.19.1** via winget. Repo
  `D:\restic-local-agent-evidence` **inited** (`cp`).
- Operator: **backup and restore both succeeded** after the visible-TTY
  stop. **Final SHA-256 comparison of the drill files is still the
  operator’s step.** Then unplug D: and store it elsewhere.
  `prune`/`forget` remain forbidden.

**Open**

- Operator SHA-256 verify + unplug D: (EOD `dh` still saw D: plugged).
- Recurring schedule / second destination beyond A: live + D: restic.
- Password manager install (custody plan: phone-synced manager +
  offline paper). Never log the repo password.

---

## Thread D — Android companion

**Done**

- PR **0**: operator accepted A1–A14 (`bb`/`bf`).
- PR **1** `bf`: `apk_review.py` (SHA-256, v2/v3 cert, fail-closed
  dangerous permissions).
- PR **2** `bp`: `adb_install.py` refuse-by-default vs
  `runtime/lxmf/adb_trusted_devices.json`.
- PR **3** `bv`: static permission gate (removed
  `MANAGE_EXTERNAL_STORAGE` from overlay spec; source walk tests).
  No companion APK compile in PR 3.
- PR **3b** `di`: pyjnius SAF **spike APK built** (WSL,
  `safspike-0.0.1-arm64-v8a-debug.apk`, package
  `local.equalshares.safspike`, SHA-256
  `4ed173b9a23ef08421ab0f5772f3b87ff7a246ff9b416e7386b473893c74e6cc`).
  Not the daily-driver companion. NDK r25b (not 28c).

**Open**

- Persistable SAF grants **unverified on-device**. No Pixel install of
  the spike. Companion daily-driver APK / PR 4+ not started.

---

## Thread E — Pixel edge gateway

**Done**

- Model choice `c`; operator **confirmed stay on**
  `huihui-ai/SmallThinker-3B-Preview-abliterated` (`do`). Larger 8B
  candidates deferred until the pipeline is proven.
- Android sparse runtime cross-build `i`/`k`.
- Gateway v1 `ad`/`ai`: phone HTTPS `10.90.91.1:8743`, admin
  `127.0.0.1:8744`, no farm Redis in process.
- **G6–G9 passed** on an independent workstation client (`cb`):
  happy path, idempotent re-claim, mutated complete 409, oversized
  400, revoked 401, no prompt/result text in gateway logs.
- Overlay **phone-side connected** (`dd`): Pixel `tun0` `10.90.91.2/30`,
  TCP to `:8743` works. ICMP to the hub still 100% loss (Windows Echo
  Request off — not required for G10). Token/PEMs/`llama-cli` staged
  under Termux `Android/data` with matching hashes (`bt`/`dd`).
  Worker now requires mTLS client certs.

**Open**

- **G10 real `--once`:** in progress, **pending model fetch** (`do`)
  and Termux hash verification. Earlier blocks (ADB unauthorized,
  no overlay, Allow-without-overlay) are behind us. Do not inject an
  admin job until `--once` is actually run on the phone.

---

## Thread F — External Comfy tools (standalone trial)

**Done (`df`, authorized `cy`)**

- **comfy-pilot** cloned into Rockernow `custom_nodes/comfy-pilot`
  (`a89fc7de…`, 0.1.0 alpha). Node `AgenticPromptGenerator`. Not
  wired into `tools.py` / `agent.py` / `router.py`.
- **comfyui-mcp@0.52.199** standalone (`npx`, HTTP `127.0.0.1:9100`).
  41 named MCP tools. Did **not** call generate / enqueue / restart /
  install-node / model-remove. `local_agent/mcp_client.py` unchanged
  this pass.
- Smoke: queue stayed empty. Pilot chat `PONG` from Huihui-8B.

**Safety notes (real, documented — not theoretical)**

- **VRAM race:** Pilot Ollama chat **promoted Huihui-8B onto the 5080**
  (7623 MiB, 94% util) while ComfyUI was up. Unloaded with
  `keep_alive:0`. Do not Pilot-chat while a render or 14B hop owns
  the card. **One ComfyUI, ever.** Audit `dq`: timeshare occupancy
  checks are **live** nvidia-smi / `/api/ps` (no stale “we loaded X”
  ledger), but **ownership attribution** still treats GPU Ollama as
  this agent’s occupancy — a third-party load is seen as busy, not as
  “someone else.”
- **Lifecycle tools** in MCP full mode can restart Comfy, install
  nodes, delete models. Do not call them from the agent. Equal Shares
  graphs were still present in `/object_info`; do not point Pilot at
  that evidence.
- `custom-nodes` path autodetection misses Rockernow’s layout
  (`found: false`) — fragility, not a crash.
- Clean shutdown verified (`:8188` down, VRAM 73 MiB). Launch later
  only after thermal/8188/owner-PID preflight; Rockernow bat then
  Pilot menu; MCP only after Comfy is up.

**Open**

- Not productized. No agent tool. Operator trial only.

---

## Still current from earlier today (not re-opened)

Carry-forward; details in the morning handoff / their letters.

| Thread | Status |
|---|---|
| Tool-calling (Coder content-JSON promoter; DeepSeek closed; catalog drowning + measured 60 tok/schema + `gpu_core`) | **Shipped** `t`/`u`/`at`/`bn`; live Comfy `ck` |
| `tracing.py` four PRs + mug-image audit link | **Closed** `l`–`ap` |
| Inline media v1 stills + v2 poll/video | **Shipped** `ae`/`aw`, revision r78 then later r79/r80 |
| Sealed chat export v1 (age, sample fixture only) | **Built**; real export still gated |
| Intent-mismatch JSONL button | **Shipped** `bd` (data collection, not a vague-request fix) |
| Phone-call assistant | **No viable live v1** `av` |

---

## Deferred / back-burner

Do not start these opportunistically.

- **PowerInfer Task 1** — operator decision still required
  (ReluLLaMA rejected; TurboSparse parked; Bamboo-DPO prompt-format
  unresolved `cf`; TinyEngine from scratch).
- **3D generation** — contract scoped `au`; `routing_ready` False;
  Trellis/3D-Pack stay `.disabled`.
- **SDXL LoRA** — trainer env exists; **content decision open**
  (`db` menu, no pick). No GPU smoke run.
- **DeepSeek-V4-Flash abliterated** — not a 13B dense card fit:
  ~284B MoE, ~167 GB, vLLM TP=2 / 2×128 GB class (`ci`). **Do not
  download.** KTransformers / PowerInfer MoE feasibility is a
  separate open TODO.
- **Qwen3.8-27B** — eval `bm`, **not** in `router.py` (weights fill
  the 5080; multi-hop template broken).
- **Multi-node farm expansion** — connectivity proven on the Mac;
  other LAN boxes are hands-on, deprioritized. 10-node architecture
  plan remains unauthorized.
- **Instructor library** — skip for `local_agent` (`ce`).
- **Historical chat export** — inventory `cj` metadata only; source
  selection TODO still closed.

---

## What a new session should not do

- Do not start ComfyUI, a render, Equal Shares, or a farm job unless
  the operator’s current ask is that work.
- Do not `restic forget`/`prune`, and do not unplug D: until the
  operator confirms SHA-256 on the restore drill.
- Do not inject a Pixel edge job until G10 `--once` actually runs.
- Do not enable `LOCAL_AGENT_LLM_JUDGE` on live chat without an
  explicit ask (farm semantic defaults off).
- Do not add WireGuard peers or farm ACL users unless asked.

Evidence for this refresh: `cn`, `da`, `de`, `dj`, `dl`, `dn`, `cw`,
`dc`, `dk`, `dm`, `dg`, `bk`/`cp`/`cc`, `bb`/`bf`/`bp`/`bv`/`di`,
`cb`/`dd`/`do`, `df`, `ci`, `db`, `au`, plus `HANDOFF_STATUS.md`
generated 2026-09-05 evening.
