# Local Agent current handoff — 2026-09-04

## Read order

1. `CLAUDE.md` — binding safety, evidence, thermal, and paused-render rules.
2. This handoff — current general-agent state as of 2026-09-04 (end of day),
   organized by thread rather than by changelog letter.
3. `local_agent/README.md` — product/runtime architecture.
4. `TODO.md` — authoritative execution queue. Two stale "not started" pointer
   entries under "To be considered — dynamic model routing & harness
   efficiency" were corrected today; they had drifted out of date the moment
   the underlying work (Threads 1 and 3 below) actually shipped.
5. `CHANGELOG/README.md` then individual `CHANGELOG/2026-09-04*.md` entries
   (28 entries today, letters `a`–`ab`; one collision at `c` — see the full
   index at the bottom of this doc).
6. `HANDOFF_STATUS.md` — the generated mechanical snapshot. Regenerated today
   via `python scripts/write_handoff_status.py` as part of this handoff.

The previous handoff is `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-03.md`. Read
it for the full history of changes made on 2026-09-03. This document
supersedes it as the current handoff and carries forward only what is still
current, adding everything done on 2026-09-04.

## Current state

Equal Shares remains a preserved, paused specialist profile. Do not resume its
audio pipeline, launch a Stage-1 render, or alter evidence/manifests. The
active product is the local general-purpose assistant.

Today was the single largest day of feature work in this project's recent
history: a full dynamic capability-based model routing system (pull → build →
live-verify), the comfyui-mcp third-party tool integration exercised across
its **entire** risk ladder (read-only through irreversible), harness profile
switching for small-model tool-calling efficiency, two real production bugs
found and fixed via live investigation (not just unit tests), and a full
GPU/ComfyUI time-sharing feature that went through two rounds of post-ship
review catching real correctness bugs before they mattered. Two proposed
"efficiency" changes were also tested and correctly rejected with real
measurements rather than built on assumption. Every thread below is closed;
none are mid-flight.

A parallel-session coordination near-miss is worth flagging explicitly for
whoever reads this next: multiple Grok sessions were operating against the
same shared ComfyUI instance without a hard lock, and one session's restart
briefly looked like an unexplained crash to another. Nothing was corrupted,
but "One ComfyUI, ever" (`CLAUDE.md`) is a real constraint that needs an
actual coordination mechanism if multiple agent sessions become routine, not
just an operator manually tracking which session currently "owns" ComfyUI by
memory.

---

## Thread 1 — Capability-based dynamic model routing (done, live-verified)

**What:** `router.py` extended with task-type capability routing across three
specialized models: a lightweight tool-calling/classification model on the
farm worker (`richardyoung/qwythos-9b-abliterated`), a reasoning model
(`huihui_ai/deepseek-r1-abliterated:14b-qwen-distill`) and a coding model
(`josiefied-qwen2.5-coder-14b:q4_k_m`, built locally via `ollama create` since
no ready Ollama tag existed) both host-GPU-resident. Since the GPU holds only
one 14B at a time, swapping between the two host models sends `keep_alive:0`
to the currently-loaded model and polls `/api/ps` until eviction is confirmed
before loading the next — reusing the pattern `context_compactor.py` already
established rather than inventing a second one.

**VRAM sizing:** `MODEL_VRAM_BUDGET.md` — Q4_K_M @ `num_ctx=8192` recommended
(11.74GB total, 4.3GB headroom). Q8_0 fails outright; the 32B alternative
fails at every tested quant/context combo; the 8B alternative fits with large
headroom but is a reasoning-depth tradeoff, not a sizing one.

**Live-verified, not just unit-tested:** a real tool-routing request reached
Qwythos on the farm and got a real response back (62.4s cold load). A real
DeepSeek→Coder swap was captured end to end: `keep_alive:0` POST captured,
`/api/ps` confirmed empty (70 MiB) before Coder loaded (10149 MiB) and
answered correctly.

Evidence: `CHANGELOG/2026-09-04h_capability_routing_model_pulls.md`,
`2026-09-04i_capability_model_routing.md`,
`2026-09-04k_capability_routing_live_verify.md`.

## Thread 2 — comfyui-mcp integration, full risk ladder exercised

**What:** the third-party `comfyui-mcp` Node.js MCP server is wired into
`local_agent/tools.py` behind seven individually-named, whitelisted wrapper
tools (`comfy_generate`, `comfy_workflow`, `comfy_assets`, `comfy_models`,
`comfy_nodes`, `comfy_system`, `comfy_process`) — no raw "call any MCP tool"
passthrough. `local_agent/mcp_client.py` is a minimal hand-rolled
JSON-RPC-over-stdio client (spawns `node npx-cli.js` directly, not
`npx.cmd` via `cmd.exe`, which dropped the handshake on first live spawn).

**Verification followed an explicit risk ladder, one tier at a time:**
mocked tests first → one live read-only call (`comfy_system`) → one live
generation (`comfy_generate`, real 512×512 PNG, verified via `/view`) →
the three state-changing tools, each exercised separately with real refusal
conditions forced first (GPU heat, a fake owner-lock byte-for-byte restored
and sha256-verified) and every "success" case run against a throwaway
artifact only — a no-op custom-node pack, a 37-byte dummy model file. No
real operator weights, references, or evidence were ever touched.

**Two bugs found along the way, both fixed:**
- `comfy_generate` wasn't audit-logged at all, and a separate investigation
  (see Thread 4) traced two "mystery" red-mug images to unrelated Grok
  test/probe scripts writing into the same shared output folder as real
  jobs with colliding default filenames. Fixed: `comfy_generate` now appends
  to `comfy_mcp_audit.jsonl` like the other state-changing tools, and
  probe/test scripts write to an isolated `output/mcp_test/` subfolder via a
  dedicated non-tool enqueue path instead of sharing the operator's real
  output root.
- `filename_prefix` silently not taking effect on image generation was
  traced to a genuine upstream `comfyui-mcp` limitation (its image-generation
  action never forwards that field to the workflow composer, confirmed
  against the pinned package's own source and the official tool schema) —
  correctly *not* worked around by rebuilding comfyui-mcp's graph
  construction ourselves.

Evidence: `CHANGELOG/2026-09-04c_comfyui_mcp_integration_plan.md`,
`2026-09-04e_comfyui_mcp_client_and_tools.md`,
`2026-09-04j_comfyui_mcp_live_generate.md`,
`2026-09-04t_comfy_generate_audit_and_probe_output.md`,
`2026-09-04v_comfy_process_live_restart.md`,
`2026-09-04w_comfy_nodes_live_install.md`,
`2026-09-04x_comfy_models_live_remove.md`.

## Thread 3 — Harness profiles (done, live-verified, two layers)

**What:** when a request routes to a CPU- or farm-served model,
`tools.profile_for(decision)` now selects a compact 3-meta-tool schema
(`list_tools`/`describe_tool`/`call_tool`, following comfyui-mcp's own
"compact mode" precedent) instead of the full ~67-tool, 40,511-character
schema. The GPU-resident model is unaffected. Profile selection happens
fresh per hop off the live routing decision, not frozen at turn start.

**A test-suite hazard was caught and closed, not left as a caveat:** both
existing regression suites defaulted their routing mock to the CPU tier, so
once schema selection keyed off that decision, the suites passing would not
by itself prove the GPU path still sent the full schema. New spy tests
explicitly forcing `tier=gpu` and asserting the full 67-tool schema were
built before this was called done (`test_native_tool_calling.py` grew
65→76→80 across the two layers; `test_action_resolver.py` grew 29→46).

**Two layers, because the first alone wasn't enough:** shipping the
meta-tool schema-switching mechanism (Layer A/v1) alone left a real
performance cliff — a live compact-profile directory-listing request took
**589.6 seconds** because the small model had to discover through
`list_tools`→`describe_tool`→`call_tool` that a listing tool existed at all.
Layer B added deterministic pre-resolution (reusing the existing
`action_resolver.py` pattern) for the specific request shapes measurement
showed were actually costing hops — the same request then took **4.3
seconds**. Destructive-guess intents (`write_file`, `run_code`, render
actions) were deliberately not added to the deterministic path.

Evidence: `CHANGELOG/2026-09-04l_harness_profiles_scoping.md`,
`2026-09-04o_harness_profiles_v1.md`, `2026-09-04p_cpu_resolver_intents.md`.

## Thread 4 — Two real bugs, found via live investigation

**Empty-completion bug.** A chat turn could complete with real generated
tokens (HTTP 200, hundreds of tokens) and still get persisted as an empty
reply — root cause was `chat_stream` never reading `message.thinking` and
the hop loop treating "no content + no tool_calls" as a finished, successful
answer, rather than a fault. This was a pre-existing gap that harness
profiles' CPU compact schema made more likely to trigger (the 8B model plans
in its thinking channel instead of calling `call_tool` more often under the
reduced schema) but did not introduce — confirmed by not reverting the
compact schema to "fix" it. Fixed: the hop loop now retries once with
`think:false` on an empty/no-tool completion, and persists a visible
`_EMPTY_COMPLETION_REPLY` instead of ever storing `""`; `chat_stream` now
sends `think:false` on CPU/chat tool hops, matching the existing KV-cache
probe's own precedent for why that's necessary. A farm hop returning empty
content with no tool_calls is now also correctly treated as not-successful.

A related, separately-diagnosed **wrong-image scare** turned out to be
nothing: two red-mug images the operator saw appear during a stalled chat
turn were unrelated Grok live-verification/probe artifacts sharing the same
output folder (see Thread 2's audit-logging fix), not a hallucinated or
mis-wired generation from the operator's actual request — no scene
generation had actually occurred yet when the mugs appeared, since the chat
was still stuck in the empty-completion bug above.

**CPU-only Ollama silently advertising the GPU.** The dedicated CPU-only
Ollama instance (port 11435) was dying/falling through during GPU discovery
despite `CUDA_VISIBLE_DEVICES=-1`, which is why a turn sometimes fell through
to the GPU-serving instance (11434) and attempted a real GPU model load while
ComfyUI held the card. Root cause: Ollama 0.32.15's `CUDA_VISIBLE_DEVICES=-1`
only disables CUDA discovery, not Vulkan (confirmed against upstream
`ollama#16508`) — the "CPU-only" server was advertising the RTX 5080 over
Vulkan the whole time. Fixed in the actual launcher
(`START_LOCAL_AGENT_GUI.ps1`'s `Start-Server`, not a manual workaround):
`OLLAMA_VULKAN=false` and `GGML_VK_VISIBLE_DEVICES=-1` added alongside the
existing `CUDA_VISIBLE_DEVICES=-1`. Verified through the actual patched
function (not a hand-rolled replica): before, `library=Vulkan` and the RTX
5080 discovered; after, `library=cpu`, `total_vram="0 B"`, and the original
fallthrough no longer reproduces.

Evidence: `CHANGELOG/2026-09-04r_empty_completion_guard.md`,
`2026-09-04y_cpu_ollama_11435_disable_vulkan.md`.

## Thread 5 — GPU/ComfyUI time-sharing (done, including two post-ship fix rounds)

**Problem:** `router.gpu_busy()` treats any ComfyUI process listening on port
8188 as "GPU busy," full stop — a deliberate, coarse, race-condition-safe
default (a render can claim the port before its backend finishes loading a
model; a naive VRAM check would read "idle" mid-claim). This meant the
agent's own GPU-routed models always yielded to ComfyUI even when ComfyUI
was sitting completely idle with nothing loaded.

**A VRAM-threshold refinement (option A) was proposed, measured, and
correctly killed before implementation.** Real instrumentation across
ComfyUI's idle/loading/loaded-idle/generating phases showed used VRAM stayed
flat at 345 MiB through three of those four phases (ComfyUI's own
DynamicVRAM staging keeps weights on CPU until first sampler use), with a
~29-second lag after generation genuinely started before `nvidia-smi` moved
at all. A VRAM threshold could not have distinguished "truly idle" from
"actively claimed, about to load" — exactly the race the original blunt
check exists to prevent.

**Option B shipped instead:** explicit time-sharing via `comfy_system`'s
`clear_vram` (`POST /free`), gated on real ownership signals — a live PID in
any of three owner-lock files stays authoritative and blocks the claim; an
empty ComfyUI queue (checked via cheap `urllib` first, MCP only as fallback)
is required; only then does the hook `/free` ComfyUI's VRAM, verify it
dropped to ≤800 MiB via `nvidia-smi`, and proceed to load the agent's model.
No explicit ComfyUI reload after `keep_alive:0` — the next real
`comfy_generate` call reloads lazily, at a documented ~17-29s cost. A kill
switch (`EQUAL_SHARES_COMFY_TIMESHARE=0`) restores today's blunt behavior
with no code revert needed.

**Two post-ship review rounds caught real bugs before they mattered, not
after:** PR 2 fixed a queue-check ordering issue, a host-GPU-gate hole that
incorrectly triggered for farm/CPU-only routing, and stripped stale
VRAM-threshold-era occupancy checks. Both PR 1 and PR 2 were independently
live-verified (six cases each: idle claim, same-hop reuse, live-owner
refusal, post-generate claim, farm-turn no-op, kill-switch restore) — the
second pass specifically re-exercising the bugs PR 2 fixed, live.

**Two deliberately-deferred follow-ups shipped today too, closing the loop
completely:** the `status()` badge now shows a real third state ("8188 up,
idle, agent may claim") derived only from the owner+queue signals already
computed — no extra network call from `status()` itself — and `agent.py`
now correctly calls `gpu_gate.request()` (the sidebar "ask every time"
permission card) before an idle-8188 claim proceeds, closing the interim
permission bypass that had been logging a `WARNING` on every claim since the
feature first shipped. Live-verified: the WARNING log came back empty on the
final test run, confirming the gate is actually intercepting the claim now.

**One residual risk is documented, not solved, and the record says so
plainly:** a TOCTOU window between confirming the queue is empty and the new
model finishing its load remains — a manual "Queue Prompt" click in
ComfyUI's own UI during that window has no PID file to be caught by. The
live-verify record explicitly flags a case where `clear_vram.ok=True` at a
345→345 no-op was *not* counted as evidence of a real free, specifically to
avoid overstating what was actually closed.

Evidence: `CHANGELOG/2026-09-04q_comfyui_gpu_timeshare_clear_vram.md`,
`2026-09-04s_comfy_gpu_timeshare_clear_vram.md` (PR 2 alignment-spec design),
`2026-09-04u_comfy_timeshare_live_verify.md`,
`2026-09-04z_comfy_timeshare_pr2_live_verify.md`,
`2026-09-04aa_timeshare_status_badge_and_gpu_gate.md`.

## Thread 6 — Two efficiency proposals tested and correctly rejected

**Mac worker `--concurrency=2`:** measured against a real 8-job embed batch.
Wall-clock throughput barely moved (+1.3%: 90.973s → 89.769s) while per-job
latency nearly doubled (11.3s → 20.8s mean) — a real regression against the
farm's 30-second interactive ceiling for no real gain. Reverted same day,
left at `--concurrency=1`, full numbers kept in the record.

**Offloading `run_code` to the farm:** no evidence existed that host CPU
contention from `run_code` was a real bottleneck. A forced worst-case test
(a synthetic 8-second CPU-bound spin loop running alongside live model
inference) showed only a 2% throughput dip. No offload code was written; the
ticket closed with the measurement as its own resolution.

Evidence: `CHANGELOG/2026-09-04n_mac_celery_concurrency_2_reverted.md`,
`2026-09-04m_run_code_cpu_contention_not_worth_building.md`.

## Thread 7 — Portfolio showcase (non-functional, job-search deliverable)

Not part of the local agent's runtime behavior — a redacted, standalone,
git-initialized showcase repo built from this session's real work, for the
operator's own job search. Two case-study docs (general-audience and
technical) and five genericized code excerpts (GPU arbitration, thermal
guard, Celery farm config, the MCP client, harness-profile switching).
Lives at `outputs/portfolio/local-agent-platform-showcase/`, outside the
main project tree. Tracked in `TODO.md` under its own "Portfolio —
job-search deliverable" section, not the general execution queue. Still
needs the operator's own read-through before anything is sent externally or
made public — that review was explicitly left as the operator's call.

---

## Full CHANGELOG letter index, 2026-09-04

| Letter | File | Thread |
|---|---|---|
| a | `post_reboot_recovery_inspection` | (carried from reboot-recovery work, not detailed above) |
| b | `wsl_redis_live_docs` | (carried from WSL Redis work, not detailed above) |
| c | `comfyui_mcp_integration_plan` | Thread 2 |
| c *(collision)* | `wsl_redis_phase_d_second_boot_pass` | (carried from WSL Redis work) |
| d | `durangamingpc_repeat_reboot_readonly_diag` | (reboot diagnostics, not detailed above) |
| e | `comfyui_mcp_client_and_tools` | Thread 2 |
| f | `farm_efficiency_evaluation` | Thread 6 (evaluation doc) |
| g | `model_vram_budget` | Thread 1 |
| h | `capability_routing_model_pulls` | Thread 1 |
| i | `capability_model_routing` | Thread 1 |
| j | `comfyui_mcp_live_generate` | Thread 2 |
| k | `capability_routing_live_verify` | Thread 1 |
| l | `harness_profiles_scoping` | Thread 3 |
| m | `run_code_cpu_contention_not_worth_building` | Thread 6 |
| n | `mac_celery_concurrency_2_reverted` | Thread 6 |
| o | `harness_profiles_v1` | Thread 3 |
| p | `cpu_resolver_intents` | Thread 3 |
| q | `comfyui_gpu_timeshare_clear_vram` | Thread 5 |
| r | `empty_completion_guard` | Thread 4 |
| s | `comfy_gpu_timeshare_clear_vram` | Thread 5 (PR 2 alignment-spec design) |
| t | `comfy_generate_audit_and_probe_output` | Thread 2 / Thread 4 |
| u | `comfy_timeshare_live_verify` | Thread 5 |
| v | `comfy_process_live_restart` | Thread 2 |
| w | `comfy_nodes_live_install` | Thread 2 |
| x | `comfy_models_live_remove` | Thread 2 |
| y | `cpu_ollama_11435_disable_vulkan` | Thread 4 |
| z | `comfy_timeshare_pr2_live_verify` | Thread 5 |
| aa | `timeshare_status_badge_and_gpu_gate` | Thread 5 |

Letters `a`, `b`, `d` are carried-forward reboot/WSL-Redis diagnostic work
from earlier in the day, not detailed thread-by-thread in this handoff since
they're continuations of Thread 6 material from the 2026-09-03 handoff, not
new threads.
