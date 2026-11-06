# Local Agent current handoff — 2026-09-02

## Read order

1. `CLAUDE.md` — binding safety, evidence, thermal, and paused-render rules.
2. This handoff — current general-agent state as of 2026-09-02 (end of day).
3. `local_agent/README.md` — product/runtime architecture.
4. `TODO.md` — authoritative execution queue.
5. `CHANGELOG/README.md` then individual `CHANGELOG/2026-09-02*.md` entries
   (18 entries today, letters `a`–`r`; several letters collided across
   parallel sessions — see the full list at the bottom of this doc).

The previous handoff is `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-01.md`. Read
it for the full history of changes made on 2026-09-01. This document carries
forward only what is still current and adds everything done on 2026-09-02.

**This revision supersedes an earlier same-day draft of this file that only
covered CHANGELOG entries `a` and `b`.** Everything below through "Changes on
2026-09-02" is new or corrected in this revision.

## Current state

Equal Shares remains a preserved, paused specialist profile. Do not resume its
audio pipeline, launch a Stage-1 render, or alter evidence/manifests. The active
product is the local general-purpose assistant.

`APP_REVISION` as of this handoff: `2026-09-01-action-resolver-r76` — unchanged
since the action-resolver landed. The launcher `START_LOCAL_AGENT_GUI.ps1`
expects the same revision.

**Phase 1 (engine architecture evaluation) is closed** as of today — see
below. **Phase 2 (context/memory optimization)** is where most of today's
work landed: RAG Stages 1, 2, and 4 are implemented and test-verified; Stage 3
(reranker) is researched but not built; the worker farm's `summarize`/`embed`
queues are built and now live end-to-end on `mac_worker`, but nothing in
`agent.py` calls them yet.

---

## Changes on 2026-09-02

### Phase 1 (engine architecture evaluation) — closed

Operator directive added Phase 1 (active/blocking) and Phase 2 (blocked)
sections to `TODO.md` (`CHANGELOG/2026-09-02d_engine_evaluation_phase_gate.md`).
Three inaccuracies in the operator's framing were corrected rather than
accepted at face value: PowerInfer wasn't "square one" (ReluLLaMA already
failed its quality gate; TurboSparse is parked pending operator-approved
calibration pairs); "TinyEngine" literally (`mit-han-lab/tinyengine`) is
microcontroller-only and not viable — the likely intended target is
`mit-han-lab/TinyChatEngine` instead, flagged for operator confirmation
(`CHANGELOG/2026-09-02e_phase1_engine_evaluation_progress.md`); and "swarm
offload to The Farm" was assumed to need building from scratch when the
Celery/Redis/WireGuard transport was already live.

**TinyChatEngine intake plan written** (not built/cloned/downloaded):
`tools/tinychatengine/INTAKE_PLAN_2026-09-02.md`, a staged Stage 0–7 plan
based on reading the actual upstream README. Key risks found: CLI-only (no
HTTP server — would need a proxy wrapper built), CUDA backend only supports
W4A16/int4 AWQ on Llama-2-gen/CodeLlama (no Llama-3, Mistral, or VLM on GPU),
the Windows CUDA build is upstream-labeled "Experimental" and predates
Blackwell/`sm_120` (the single biggest unverified risk), no batching/
concurrency support, no tagged releases.
(`CHANGELOG/2026-09-02f_tinychatengine_intake_plan.md`)

**Phase 1 closed, operator decision (`CHANGELOG/2026-09-02j_...`):** stay on
Ollama with the current model family (Qwen, gpt-oss); no PowerInfer route, no
TinyChatEngine pursued "for now." This unblocked Phase 2.

Separately, `karpathy/autoresearch` was catalogued in `TODO.md` as a
bookmarked resource, not an active dependency — correcting an assumption that
it was a context/tool-orchestration harness (it's actually an autonomous
ML-training-experiment loop). Two more plausible actual fits flagged instead:
a template for a future Supervisor Loop, or for automating PowerInfer's own
predictor/calibration tuning. Nothing cloned or run.
(`CHANGELOG/2026-09-02g_autoresearch_resource_note.md`)

### judge_evaluation workflow — built, then verified live end-to-end

Built earlier this session as the first real worker-farm workflow:
`judge_rubric.py` (pattern-matching, no model call — 4 rules: unverified
completion claims, work dumped on the operator, specialist-project leakage,
unexecuted direct-action requests), a `judge_transcript` Celery task, and
`submit_judge_batch.py` (ledger-tracked incremental resubmission). Operator
explicitly authorized sending real, unfiltered chat transcripts (including
NSFW) to secondary worker machines — a deliberate trust-boundary decision,
not inferred. 10/10 rubric unit tests, 32/32 combined suite (3 skipped).
(`CHANGELOG/2026-09-02c_judge_evaluation_workflow.md`)

**Then run live end-to-end** (`CHANGELOG/2026-09-02d_judge_evaluation_end_to_end_verified.md`):
- **Bug found and fixed:** `celery_app.py` had `judge` in `task_routes` but
  missing from `task_queues` — silent routing failure. (This is the same
  class of bug later found again and explicitly guarded against when adding
  the `summarize`/`embed` queues — see below.)
- Mac worker's prior `worker_farm/` directory had been deleted; its running
  process was serving stale pre-`judge_transcript` code from memory. SSH
  access established (new ed25519 key), fresh environment rebuilt at
  `~/worker_farm/` on the Mac, worker restarted with `--queues probe,judge`.
- 3 real `judge_transcript` tasks submitted, all SUCCEEDED (16–68ms on the
  Mac). Real findings returned — e.g. the 85-message chat correctly flagged 4
  instances of ComfyUI/H3 content leaking into turns where the user hadn't
  invoked that project.
- **ACL DENY probe — an honest, documented, still-open gap:** `mac_worker`'s
  Redis ACL uses `~*` (all keys) because Celery/Kombu generates unpredictable
  internal key names, so a pattern-scoped ACL isn't practical. Sentinel test
  confirmed `mac_worker` *can* read the `distill` queue's envelopes and any
  `celery-task-meta-*` result key, though `NOPERM` correctly blocks admin ops
  (`ACL SETUSER`, `CONFIG GET`, etc.). Mitigating factor: the worker still
  needs the admin Redis password to connect at all. Accepted as a tolerable
  trade-off at current scale given the operator's own trust-boundary
  decision above — not a closed gap, and not to be treated as one.
- 30 of 33 discovered chats remain unjudged; next unlimited `submit_judge_batch`
  run will queue them.

### Worker farm — hardware inventory + per-worker model policy established

Doc-only pass added a "per-worker model choice — no fleet-wide fixed model"
policy and a "known worker machines" table to `local_agent/worker_farm/README.md`:
model choice per node is a hardware-fit decision made when that node is set
up, not a global config, and any future workflow dispatching a model choice
(e.g. an LLM-based judge pass) must not assume a uniform model across
workers. First entry: `mac_worker`, 2019 MacBook Pro, 16 GB RAM, macOS
13.7.8 x86_64 — WireGuard-connected, `probe`+`judge` queues granted.
(`CHANGELOG/2026-09-02h_worker_farm_hardware_inventory.md`)

### `summarize`/`embed` worker-farm queues — built, then made live on mac_worker

Implements `HARNESS_OPTIMIZATION.md` §4a (see below). Built in three passes
today:

1. **Task code written** (`CHANGELOG/2026-09-02o_summarize_embed_farm_queues.md`):
   `summarize_conversation` (reuses `context_compactor.summarize_old_messages`,
   degrades gracefully to `{"summarized": false, ...}` rather than failing if
   no model is installed) and `embed_chunks` (stateless — embeds `{id, text}`
   chunks, returns vectors only, does not touch `retrieval.py`'s on-disk
   embedding cache) added to `worker_farm/tasks.py`, registered on new
   `summarize`/`embed` queues in `celery_app.py` — this time added to **both**
   `task_queues` and `task_routes` together, with an explicit code comment
   warning against repeating the `judge`-queue bug found above. Tests written
   to `test_farm_core.py`, not executed this pass (no shell access).

2. **Per-worker model override added** (`CHANGELOG/2026-09-02q_summarize_queue_per_worker_model.md`):
   The initial version hardcoded `context_compactor.MODEL` (`llama3.1:8b`)
   fleet-wide, which would have silently broken on any worker running a
   different model. Fixed: `context_compactor._installed()` and
   `summarize_old_messages()` gained `model=`/`host=`/`timeout=` overrides
   (defaults unchanged for existing workstation callers — regression-guarded
   in new `test_context_compactor.py`); `_summarize_messages()` in
   `worker_farm/tasks.py` now reads the model from that worker's own
   `FARM_SUMMARIZE_MODEL` environment variable, falling back to the
   workstation default only if unset. `embed_chunks` stays fixed on
   `nomic-embed-text` — embedding doesn't have the same per-worker
   refusal-risk rationale that motivates the summarizer choice (see next
   paragraph). Tests written, not executed this pass either.

3. **Deployed and verified live** (`CHANGELOG/2026-09-02r_summarize_embed_queues_live.md`):
   `mac_worker` is recorded as running **`krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS`**
   (~6.8 GB) for summarization specifically — a deliberately non-safety-tuned
   model, so it won't refuse to summarize sensitive conversation content
   under the same trust-boundary decision that governs `judge_transcript`
   above. Set via that worker's own `FARM_SUMMARIZE_MODEL` env var, per the
   per-worker-model policy — this is not a fleet-wide default and future
   workers may choose differently. Both queues confirmed live with real task
   IDs:
   - `summarize_conversation` — task `05015820-cc65-41d4-9166-f0e5a7f4ca83`,
     returned a structured `{goal, decisions, open_questions, ...}` summary.
   - `embed_chunks` — task `6509195d-c718-4179-9e58-0453ade2b23f`, returned
     768-dim vectors for two chunks via `nomic-embed-text:latest`.
   First-call latency ~55s (cold model load + inference on a 2019 Intel Core
   i9 Mac CPU, no GPU); mistral-nemo-abliterated inference alone ~18.5s once
   loaded; nomic-embed-text embed ~0.58s once loaded. Deployment notes
   (SSH username correction, an MLX runner bug found and fixed, the model not
   being pre-installed, a PowerShell array-syntax gotcha) are in the
   changelog entry. `.env.mac_worker.generated` was deleted from the
   workstation after confirming the Mac's own `.env` worked, per that file's
   own header instruction not to leave it there.

   **Still not built:** anything in `agent.py` that decides when to route a
   summarize or embed call to the farm vs. running locally. The queues are
   reachable and verified; nothing calls them automatically yet. This is the
   one open item left in TODO.md's swarm-offload entry.

### RAG upgrade — Stages 1, 2, and 4 implemented and test-verified; Stage 3 researched only

Gap analysis first (`CHANGELOG/2026-09-02i_rag_evaluation.md`, `RAG_EVALUATION.md`
at repo root): confirmed `retrieval.py` was pure BM25 lexical search,
`EmbeddingScorer` was a literal `NotImplementedError` stub, and no
hybrid-fusion/reranking/agentic loop wrapped `search_docs` — though the
agentic-loop pattern already existed and was proven out in `deep_research.py`
(bounded, `MAX_ROUNDS=4`), just wired to web search only, not local docs.
5-stage staged proposal written; added to `TODO.md` Phase 2, explicitly
BLOCKED by Phase 1 at the time.

**Stages 1–2, implemented once Phase 1 closed** (`CHANGELOG/2026-09-02j_...`,
verification in `CHANGELOG/2026-09-02k_rag_embedding_tests_verified.md`):
- **Stage 1 — real `EmbeddingScorer`** in `retrieval.py`: nomic-embed-text
  via the same CPU-only Ollama endpoint pattern `exemplar_embeddings.py`
  already proved out. Disk-cached (`knowledge/retrieval_embeddings.json`),
  keyed by chunk id + text hash so an edited file only re-embeds changed
  chunks.
- **Stage 2 — `HybridScorer`**: fuses `LexicalScorer` + `EmbeddingScorer` via
  Reciprocal Rank Fusion (rank-based, since BM25 and cosine scores aren't
  directly comparable). Deliberately not naive RRF over the whole corpus — a
  relevance floor (BM25>0 or cosine≥0.35, an unverified heuristic, flagged
  for revisit) gates entry into the fused pool, preserving the "empty result
  means local docs don't establish the claim" safety contract. Falls back to
  lexical-only ranking if the embedding endpoint errors.
- **Neither is wired as the default** — `search`/`search_docs` still use
  `LexicalScorer` unless a caller explicitly opts in, pending a Stage 5
  human quality comparison.
- **Verified by the operator directly, corrected count:** 7 tests (an
  earlier note claimed 9; wrong), all passed —
  `python -m unittest local_agent.test_retrieval_embeddings -v`.

**Stage 4 — agentic self-correction, implemented and test-verified**
(`CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md`; the 8/8 pass
result is confirmed in `TODO.md`, not in a dedicated changelog entry — if
that's surprising, the omission is real, but the pass result itself is
recorded twice independently and both agree): `agentic_retrieval.py` /
`agentic_search_docs()`, a bounded retrieve→grade→retry loop mirroring
`deep_research.py`'s pattern (`MAX_SUBQUERIES=4`/round, `MAX_ROUNDS=3`, dedup
against tried queries). Uses `HybridScorer`; the model self-grades
sufficiency via trailing JSON; includes an anti-hallucination guard that
strips/rejects fabricated file-path citations and forces `sufficient=False`
rather than trusting an ungrounded "yes." Wired into `tools.py` as a new
`agentic_search_docs` tool, added to `PROJECT_ONLY_TOOLS`, deliberately
excluded from `CONCURRENCY_SAFE_TOOLS` (it calls the model). **Executed by
the operator 2026-09-02: 8/8 passed**, same run re-confirmed
`test_retrieval_embeddings.py`'s 7/7 still passing after the Stage 4 changes
— no regression.

**Stage 3 — reranker, researched only, not implemented**
(`CHANGELOG/2026-09-02m_rag_stage3_reranker_research.md`): selected
**FlashRank** (ONNX-optimized `ms-marco-MiniLM-L-6-v2`, ~80MB) as the
best-fit candidate — CPU-only, no heavy ML framework. Not built because it's
a genuinely new runtime dependency (`onnxruntime`), gated behind explicit
operator approval per this project's intake-decision pattern. Design
sketched (`RerankedScorer` reordering `HybridScorer`'s fused top-N) but not
written.

**Stage 5 (human quality comparison before Hybrid/Agentic becomes default
for `search_docs`) remains open.**

### `HARNESS_OPTIMIZATION.md` — audit + spec, no code

Headline finding: most of the original ask (context compaction, progressive
tool disclosure, concurrency-safe parallel execution, bounded
coordinator/worker fan-out) **already exists and is mostly tested** in the
codebase. The real, narrower gap was that the worker farm didn't yet route
`summarize`/`embed` task types — closed by the work described above. One
correction made along the way: a proposed fixed "6000 token" compaction
threshold would have been worse than the adaptive `prompt_tokens > num_ctx`
trigger already in use, so the adaptive trigger was kept. A named source
("RoboCFO") could not be verified as a real project and was flagged rather
than invented; two other named sources (OpenHarness, Revfactory) were
confirmed real. `TODO.md` item 2 (sliding-window summarizer) marked
resolved/already-built with no new code needed.
(`CHANGELOG/2026-09-02n_harness_optimization_spec.md`)

### `LLMOPS_AUDIT.md` — audit + spec, no code

Read `ollama_client.py::chat()` end-to-end: confirmed it already receives
but discards `eval_count`, `prompt_eval_count`, `total_duration`, and
`eval_duration` from Ollama's own response — a sharper finding than "no
tracking exists," since the data is already there and thrown away. Proposal:
(a) a dependency-free SQLite span logger (`tracing.py`, OTel-shaped fields,
proposed not built); (b) extending (not replacing) `operator_eval.py` with
an advisory LLM-as-judge pre-score tracked for correlation against human
scores, never auto-accepted; (c) Reason→Act→Observe pseudocode with tracing
spans. One concrete required code change identified but not yet made: stop
discarding those token/duration fields. New `TODO.md` "LLMOps / observability"
section with 3 tracked items, all unimplemented.
(`CHANGELOG/2026-09-02p_llmops_audit_spec.md`)

### Source citation contract

The agent now requires source-backed factual claims and preserves provenance
through context pruning. See `CHANGELOG/2026-09-02b_source_citation_contract.md`.

**What changed:**

`agent.py` — `# Source citation` section added to `CONVERSATION_RULES`:
- Web / internet claims must name the URL or page title.
- Project documents claims must cite file path and section heading.
- Files and system state must include the file path or directory.
- Memory and prior chats must note that provenance explicitly.
- Unsupported pre-training knowledge must be labelled "from model knowledge"
  or "unverified".
- Exception: casual chat, creative writing, brainstorming, and code generation
  do not require source labels unless a specific factual claim is made within them.

`agent.py` — `_tool_source_label(name, result) -> str | None` — new helper
that extracts provenance from the raw tool-result string for six tool types:

| Tool | Label extracted |
|---|---|
| `fetch_url` | Final URL from leading `[url]` bracket |
| `web_search` | Backend + query from leading `[backend: query]` bracket |
| `search_docs` | `"docs: path1, path2, …"` from JSON `source` fields |
| `read_file` | File path from leading `[File: path]` header |
| `list_dir` | Directory path from first line of result |
| `list_memory` / `remember_fact` | `"persistent memory"` |
| All other tools | `None` — no label, no format change |

`artifacts.py` — `prune_large_text(kind, text, limit=2400, source_label=None)`:
optional `source_label` keyword argument (backward compatible). Pruned pointer
now embeds `source=<label>` when a label is supplied, so provenance survives
context compaction into the artifact pointer.

`tools.py`:
- `read_file` now prepends `[File: {resolved_path}]\n\n` before content.
- `list_memory` now prepends `[Source: persistent memory]\n` to both return paths.

Both `prune_large_text` call sites in `agent.py` (main tool loop + specialist
retry path) now pass `source_label=_tool_source_label(name, result)`.

Post-tool follow-up user message strengthened to: "cite the source (URL, file
path, or tool name) visible in the tool results above; label unsupported
conclusions 'unverified' or 'from model knowledge'."

**New test file:** `local_agent/test_source_citation.py` (24 tests, all pass):

| Class | Tests |
|---|---|
| `SourceLabelExtractionTests` | 11 — extraction across all six tracked tool types, redirect handling, empty results, untracked tools |
| `ArtifactSourceLabelTests` | 4 — label in pruned pointer, no label leaves format unchanged, small result as-is, label survives fetch-sized result |
| `ToolResultSourceHeaderTests` | 3 — `[File: …]` header present and extractable, `[Source: persistent memory]` present |
| `AgentCitationContractTests` | 5 — CONVERSATION_RULES has `# Source citation`, covers web, docs, memory, creative exception |
| `NoStaleSpecialistSourceTests` | 1 — specialist scope guard discards stale H3/ComfyUI reply |

**Remaining gap:** GUI source cards. Provenance is present in the model reply
text and artifact pointers, but the browser UI does not render it as distinct
structured cards (a planned "Visible agent activity trace" item in TODO.md).

### Misc corrections/fixes (no feature change)

- **First-bot status sync** (`CHANGELOG/2026-09-02d_first_bot_watch_status_sync.md`):
  found `GROK_STATUS.md` stale (claimed `r73`, actual `APP_REVISION` was
  `r76`) and corrected it. Inspect-only, no code changes. First-bot
  stop-until-go gate still held; Harmontown still paused; PowerInfer
  ReluLLaMA still fails its 9/10 quality gate.
- **Stale elevated process kill fixed** (`CHANGELOG/2026-09-02e_stale_agent_elevated_kill.md`):
  root-caused a launcher failure to a leftover elevated `python.exe` holding
  port 8760 that an unelevated kill couldn't touch. Fixed
  `START_LOCAL_AGENT_GUI.ps1`'s `Stop-StaleAgent` to do a one-shot
  UAC-elevated `taskkill` then continue unelevated; also fixed a
  `NativeCommandError`-under-strict-error-action-preference bug hit along
  the way. Verified: replacement server came up unelevated,
  `app_revision=2026-09-01-action-resolver-r76` confirmed live.

---

## Carried-forward state from 2026-09-01

The following sections summarize state that has not changed since the prior
handoff. Read `LOCAL_AGENT_CURRENT_HANDOFF_2026-09-01.md` for full detail.

### Specialist scope guard (runtime, not prompt-only)

`agent.py` blocks specialist tools before execution and discards one stale
specialist reply/tool path before retrying whenever the current operator message
does not explicitly ask about ComfyUI, H3, MiniMax, Equal Shares, rendering,
batch jobs, story-image generation, clips, prompt sets, or active image/video
status. Verified by the 57-test `test_native_tool_calling.py` suite. `APP_REVISION`
is `2026-09-01-specialist-scope-guard-r74`; superseded on the same day by the
action-resolver at `r76` (revision bumped, guard preserved).

### Action-resolution layer

`local_agent/action_resolver.py` classifies direct operator requests into
deterministic `(tool_name, args)` plans before the model drafts prose. Five
intents handled in priority order: `comfyui_stop`, `jsonl_repair`,
`calibration_continue`, `list_dir`, `read_file`. Covered by 29 tests in
`test_action_resolver.py`.

### Image generation (real renders verified)

`work/image_render.py` + `render_story_image` / `story_image_job_status` tools
are wired and tested against a real ComfyUI backend. Two real t2i renders have
completed:
- t2i denoise forced to 1.0 (haze bug fixed, confirmed on real render)
- Hi-res fix pass added automatically for all t2i renders (crossed-eyes fix,
  confirmed on real render — eyes correctly aligned, sharper)
- CLI UTF-8 crash fixed
- Three image profiles: `realvisxl` (default), `alicemix_sd15`, `realpro_flux`

Inline image preview in chat is implemented (`GET /api/story_image_file`,
`POST /api/reveal_story_image`). Not yet exercised against a real render in this
session.

### General image models

| Profile | Architecture | Status |
|---|---|---|
| `realvisxl` | SDXL checkpoint | Default; two real renders completed |
| `alicemix_sd15` | Complete SD 1.5 checkpoint | Static graph verified; no live output yet |
| `realpro_flux` | Flux UNet-only | Static graph verified; no live output yet |

### PowerInfer

ReluLLaMA-7B failed nine of ten basic instruction/format cases — not eligible
for promotion. Preserve as diagnostic evidence. TurboSparse-Mistral projected
abliteration is parked at
`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`
(do not use the earlier non-`b` directory). Do not dump, train, convert, or
bench it until operator-approved pairs exist and a fresh GPU gate is granted.
Per today's Phase 1 closure (above), no further PowerInfer route work is
planned "for now."

Bamboo-DPO Q4 runtime intake: native sparse loading + CUDA + 3,024 MiB FFN
offload verified; `prompt_contract_unresolved`; 2026-09-01 raw-completion
diagnostic completed unscored with CUDA/sparse evidence; VRAM released. Does not
qualify for any route. Obtain source-backed prompt-format evidence before any
instruction/format comparison.

### SDXL LoRA environment

`A:\Users\rhine\kohya_ss\.venv-local-agent` is ready (Python 3.11.15, Torch
2.7.0+cu128, CUDA 12.8). No checkpoint loaded, no training started. Waiting on:
operator-selected training objective, dataset, trigger token, and explicit GPU
approval for a smoke run.

### DeepSeek-V4-Flash abliterated

`cebeuq/DeepSeek-V4-Flash-0731-abliterated` — not started. A hardware/tooling
mismatch was found before any download; needs an operator decision. No file
downloaded, no engine installed, no model registered.

### Worker farm — WireGuard hub state

- Hub: workstation at `10.90.90.1:51820`, hub public key
  `ABIeyNucK9ctn5hPaDWMkworftoxKfg02kHX9RRl9mM=`
- Mac: `10.90.90.2`, public key `H0IsFuY1eREqu4jWXz94fKR9oC+4qdcBU7d83shvNzo=`
- `mac_worker` ACL scoped to `probe,judge` queues (updated 2026-09-02d) —
  `summarize`/`embed` are live and verified but the ACL/queue-grant scope for
  them specifically is documented in `CHANGELOG/2026-09-02r_...`, not repeated
  here; check that entry before assuming `mac_worker`'s exact granted queue
  list without re-reading it.
- Mac worker running at `~/worker_farm/` on `celery@Louises-MBP`, Python 3.11
  venv; SSH access via workstation key `~/.ssh/workstation_to_mac` (ed25519,
  added to Mac's `authorized_keys`)
- Tunnel relay: `10.90.90.1:6379 → 127.0.0.1:6379`, `MAX_CONCURRENT_CONNECTIONS=64`
- Connectivity probe verified 2026-09-02a; judge_evaluation verified 2026-09-02d;
  summarize/embed verified 2026-09-02r
- ACL DENY probe run 2026-09-02d — real, documented, accepted-not-closed gap
  (see above)
- Remaining: relay autostart, additional machines (.3, .4, ...), and the
  `agent.py`-side caller that actually routes summarize/embed calls to the farm

### Usability gap (open, needs operator input)

Operator feedback 2026-09-01: "Claude, Claude Code, GPT are all very good at
inferring what to do when I'm not super specific and I really want the local
agent to be like that. Right now it feels hard to use."

Not diagnosed yet — needs concrete before/after examples (an actual vague
request and what the local agent did versus what was expected) before it is
actionable. The failure mode may be a small local model capability ceiling rather
than a prompting/routing problem; that distinction requires examples to assess.

### Broad regression state

As of 2026-09-02, tests known to have actually been executed (not just
written) and their results:
- `test_native_tool_calling.py` — 57 pass
- `test_source_citation.py` — 24 pass
- `test_action_resolver.py` — 29 pass
- `test_retrieval_embeddings.py` (RAG Stages 1–2) — 7 pass (operator-run,
  corrected from an earlier miscount of 9)
- `test_agentic_retrieval.py` (RAG Stage 4) — 8 pass (operator-run per
  `TODO.md`; same run reconfirmed the 7 embedding tests, no regression)

Written but **not yet executed** this session (no shell/bash access in the
sessions that wrote them): `worker_farm/test_farm_core.py`'s
summarize/embed-queue additions, `local_agent/test_context_compactor.py`.
Run commands are in each relevant CHANGELOG entry and in `TODO.md`.

No GPU, render, model load, PowerInfer process, or download was started during
any of today's work.

---

## Execution gates (open items that need operator input)

- **SDXL LoRA**: operator-selected objective/dataset + explicit GPU approval
- **Bamboo-DPO / PowerInfer**: source-backed prompt-format evidence + GPU approval
  (deprioritized — Phase 1 closed on staying with Ollama "for now")
- **TurboSparse**: ≥32 operator-approved calibration pairs before any GPU dump
  (draft pairs prepared under `review-only/`, unapproved — see `TODO.md`)
- **DeepSeek-V4-Flash**: operator decision on hardware/tooling approach
- **Archive destination**: real historical export source selection, destination,
  and key-custody decision before staging any real export
- **Usability gap**: concrete vague-request examples from the operator
- **TinyChatEngine**: confirm this (not the microcontroller-only
  `mit-han-lab/tinyengine`) was the intended target before any Stage 1 work,
  even though Phase 1 is otherwise closed
- **RAG Stage 3 (reranker)**: approve or decline the new `onnxruntime` +
  FlashRank dependency
- **RAG Stage 5**: human quality comparison of Hybrid/Agentic search vs.
  lexical-only before either becomes the `search_docs` default
- **Worker farm `agent.py` caller**: design/build the decision point that
  actually routes summarize/embed calls to the farm — no operator decision
  blocking this, just not yet built
- **Worker farm ACL DENY gap**: `mac_worker`'s `~*` Redis ACL pattern is an
  accepted trade-off, not a fix; revisit if the trust boundary or scale
  changes
- **Worker farm ACL / autostart / additional nodes**: no code gate, just
  operational steps (run probe, update scripts, repeat per machine)
- **LLMOps tracing/judge**: 3 unimplemented items in `TODO.md`'s new
  "LLMOps / observability" section, gated behind operator prioritization
  against everything else here, not a hard blocker

`docs/LOCAL_AGENT_OPERATOR_DECISIONS.md` turns these gates into a single concise
response template; it is documentation only and grants no capability.

No background worker, phone, renderer, ComfyUI instance, or PowerInfer process
may be started merely to clear an unchecked box.

---

## Full CHANGELOG index for 2026-09-02

For reference — several letters were reused by parallel sessions per
`CLAUDE.md`'s warning about concurrent agents; where two files share a
letter, both are listed and both are real, distinct entries.

`a` mac_worker_probe_verified · `b` source_citation_contract ·
`c` judge_evaluation_workflow · `d` first_bot_watch_status_sync ·
`d` engine_evaluation_phase_gate · `d` judge_evaluation_end_to_end_verified ·
`e` phase1_engine_evaluation_progress · `e` stale_agent_elevated_kill ·
`f` tinychatengine_intake_plan · `g` autoresearch_resource_note ·
`h` worker_farm_hardware_inventory · `i` rag_evaluation ·
`j` rag_embedding_scorer_and_phase1_close · `k` rag_embedding_tests_verified ·
`l` rag_stage4_agentic_self_correction · `m` rag_stage3_reranker_research ·
`n` harness_optimization_spec · `o` summarize_embed_farm_queues ·
`p` llmops_audit_spec · `q` summarize_queue_per_worker_model ·
`r` summarize_embed_queues_live
