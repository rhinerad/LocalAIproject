# Local Agent current handoff — 2026-08-30

## Read order

1. `CLAUDE.md` — binding safety, evidence, thermal, and paused-render rules.
2. This file — latest handoff for general local-agent work.
3. `local_agent/README.md` — current product architecture and runtime rules.
4. `TODO.md` — authoritative remaining work.
5. `CHANGELOG/README.md` — same-session change evidence.

## Active product scope

Equal Shares is a preserved, optional specialist profile. Its pipeline is
paused: do not start ComfyUI, resume a render, or alter its evidence/manifests.
The active product is the general-purpose local desktop agent: tools, file
work, multimodal analysis, model routing, GPU ownership, persistent memory,
phone access, and background-worker infrastructure.

## PowerInfer — prepared but not active (2026-08-31)

Native RTX 5080 PowerInfer is mechanically functional. ReluLLaMA-7B remains
diagnostic after failing instruction quality; Bamboo-DPO has no source-backed
chat contract. TurboSparse has a verified local ChatML tokenizer contract and
safe pipeline/quality-gate preparation, but its `20260830b` edit used eight
synthetic pairs. It is not eligible for predictors, conversion, a proxy, or
the local-agent picker until a new immutable edit is made from 32+ approved
pairs and passes the strict two-turn JSON tool-call gate plus human review.

## Multi-node worker farm — first peer verified 2026-09-02

Mac (`celery@Louises-MacBook-Pro.local`, `10.90.90.2`) is the first verified
secondary worker node. End-to-end state as of 2026-09-02:

- WireGuard hub running on workstation `10.90.90.1:51820`; Mac peer
  registered (public key `H0IsFuY1eREqu4jWXz94fKR9oC+4qdcBU7d83shvNzo=`).
- Tunnel relay: `local_agent/worker_farm/relay/tunnel_relay.py --bind-ip
  10.90.90.1` forwarding `10.90.90.1:6379 → 127.0.0.1:6379`, **64
  concurrent connections** (was 8; raised to fix result-backend timeout).
- `mac_worker` Redis ACL user: `on`, `+@all` minus destructive ops, `~*`
  keys, scoped to `probe` queue credential only. In-memory — re-run
  `Add-Phase1SecondaryWorkerCredential.ps1` after any Redis container restart.
- `connectivity_probe` task returned `hostname: Louises-MacBook-Pro.local`
  from task ID `720fc45b`. CHANGELOG: `2026-09-02a_mac_worker_probe_verified.md`.

**Known issue:** relay is not autostarted. After a reboot, run
`python local_agent/worker_farm/relay/tunnel_relay.py --bind-ip 10.90.90.1`
from the worker-farm venv before the Mac worker can connect.

**Still needed:** ACL DENY probe; autostart for the relay; additional peers
(.3, .4, ...) following the same Add-WireGuardPeer + credential script pattern.

## Response relevance incident — 2026-08-31

A general request (“im trying to test how fast you can do things”) was answered
with unrelated Unity/paywall content. Cause: cross-chat retrieval scored generic
words and injected a prior assistant response. `local_agent/chat_retrieval.py`
now requires two meaningful topic terms and exposes only prior operator messages.
`local_agent/agent.py` treats injected continuity as non-instructional and
withholds stale access-bypass assistant text from live model context without
altering the saved conversation. Regression coverage is in
`test_chat_retrieval.py` and `test_general_assistant.py`; see
`CHANGELOG/2026-08-31_prior_chat_retrieval_relevance_fix.md`.

## CPU fallback readiness — 2026-08-31

The general-agent server is live on loopback `127.0.0.1:8760`. While the
existing ComfyUI backend holds port 8188, routing deliberately stays on the
CPU-only Ollama tier at `127.0.0.1:11435` using
`huihui_ai/qwen3-abliterated:8b`; the CPU tier is now verified available. The
launcher tolerates Ollama's initial local-catalogue hydration, so it must not
misreport that tier as down during a normal cold start. This remains a CPU-only
path (`size_vram: 0`) and never authorizes a GPU model load.

Greetings and explicit agent-speed checks in a new/near-empty general chat now
use a deliberately narrow no-tool fast path, rather than carrying the full
tool catalogue and specialist/sensory rules. Requests involving a path, URL,
file, action, media, research, permission, or project stay on the complete
guarded route.

See `CHANGELOG/2026-08-31_cpu_tier_startup_readiness.md`.

## Phone automatic model routing — 2026-08-31

Sideband is the supported phone interface. An unpinned paired phone identity
now re-evaluates the normal automatic GPU/CPU route on every message. A chat
first created while ComfyUI owns port 8188 may have an 8B fallback recorded as
its saved display model, but that historical value must never pin later phone
turns to CPU. Explicit per-identity model pins remain honored. The bridge
labels a ComfyUI-caused CPU route as temporary. Coverage:
`local_agent/test_lxmf_bridge.py`; change record:
`CHANGELOG/2026-08-31_phone_auto_model_routing.md`.

## Phone queued-media completion delivery — 2026-08-31

Queued Sideband sensory requests now return their completed caption,
transcript, or action log to the same paired phone conversation. The queue job
contains only trusted bridge-injected return metadata; it is not model-selected
and does not expand phone permissions. `lxmf_agent.py` records one delivery
hash row per media job in `runtime/lxmf/media_completion_delivery.jsonl` to
avoid duplicate radio messages. Older Sideband-upload jobs can be recovered
only by matching their immutable upload request directory to the existing
attachment audit. See `CHANGELOG/2026-08-31_phone_media_completion_delivery.md`.

## VLM residency reporting — 2026-08-31

The exact Qwen2.5-VL runtime is released automatically only when the watcher
has a matching ownership record. A listener already present on its loopback
port is left untouched and explicitly reported as resident, so the router does
not claim the GPU is available. This is intentional safety behavior; see
`CHANGELOG/2026-08-31_vlm_residency_status_truth.md`.

The lazy VLM launcher now atomically records a spawned server before accepting
it as usable, and cleans up its own PID on record-write failure or readiness
timeout. This prevents future unowned VLM orphans from blocking GPU chat; see
`CHANGELOG/2026-08-31_vlm_orphan_prevention.md`.

The measured controlled lifecycle now passes: exact V4 GGUF+mmproj cold-load
24.047 s, first analysis 30.875 s, warm follow-up 0.969 s, and confirmed
release 2.047 s to an 81 MB VRAM baseline. The metadata-only report and
evidence are in `CHANGELOG/2026-08-31_exact_vlm_lifecycle_live_validation.md`.

## PowerInfer status — do not route yet

### ReluLLaMA-7B

The native RTX 5080 PowerInfer build passed mechanical serving checks, but its
candidate failed 9/10 bounded instruction/format cases. It remains diagnostic,
unregistered, and unavailable to the local-agent router/picker.

### TurboSparse-Mistral projected ablation

Use only:

`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`

Never use the non-`b` directory. The streaming `safe_open` path verified 32/32
`o_proj` edits, unchanged `down_proj`, max Frobenius drift 2.1e-4, and a finite
one-layer Bamboo/ReLU forward. Its eight synthetic calibration pairs are
exploratory only. Predictors/activations were not rebuilt and no quality
benchmark is authorized until operator-approved harmful/harmless pairs exist.

### Bamboo-DPO 7B candidate

Candidate root:

`A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake`

- Exact Q4 PowerInfer GGUF SHA-256:
  `9661890635b4f986ebe523eba10404cbb5481be57266cb6d5a894fb63cac527c`
- The pinned intake and its original/predictor/activation sources are
  byte-verified.
- Frozen source proves Bamboo dReLU:
  `relu(gate_proj(x)) * relu(up_proj(x))` before `down_proj`.
- Isolated native mechanical gate passed with CUDA sparse loading and 3,024 MiB
  FFN GPU offload; GPU was released on exit.
- The first run exposed a system-Python split failure. The repaired runner
  scopes the matching PowerInfer venv and requires nonzero FFN GPU offload to
  pass; that failure remains preserved in validation evidence.
- Frozen tokenizer has no `chat_template` and the source README has no explicit
  instruction-format marker. The local prompt-contract receipt is
  `validation/bamboo_dpo_prompt_contract_20260830_233100.json`, status
  `prompt_contract_unresolved`.
- The frozen model code also contains one plain-continuation generation
  example. The addendum receipt
  `validation/bamboo_dpo_prompt_contract_addendum_20260831_000001.json` records
  that a bounded raw-completion diagnostic is source-backed. It does **not**
  establish a chat or instruction-following format.

Therefore: do not invent `[INST]`, Alpaca, or another chat wrapper; do not run
the ten-case instruction gate; do not start a server; and do not register,
route, or show the candidate in the local-agent picker. Source-backed prompt
format evidence is required first.

## Evidence and tooling

- `tools/powerinfer/run_bamboo_dpo_mechanical_gate.ps1` — one bounded native
  raw-completion smoke; refuses ComfyUI/port 8188, duplicate native runners,
  invalid hashes, unsafe temperature, absent activation files, or missing
  sparse-split evidence.
- `tools/powerinfer/classify_bamboo_dpo_prompt_contract.py` — source-only
  classifier; never loads a model.
- `tools/powerinfer/run_bamboo_dpo_raw_completion_diagnostic.ps1` — requires
  `-Execute`, a fresh GPU-owner decision, the source-contract addendum, and a
  clear ComfyUI/native-runner state. It captures one unscored raw completion;
  it cannot start a server or promote the candidate.
- `tools/powerinfer/test_verify_bamboo_dpo_intake.py` — 3 tests passed.
- `tools/powerinfer/test_classify_bamboo_dpo_prompt_contract.py` — 3 tests
  passed.
- `CHANGELOG/2026-08-30_bamboo_dpo_mechanical_gate_passed.md` and
  `CHANGELOG/2026-08-30_bamboo_dpo_prompt_contract_gate.md` — full evidence.

## Current boundaries

- Existing Ollama routes are the production fallback.
- The local-agent PowerInfer proxy remains loopback-only and unlaunched.
- No candidate is in the PowerInfer production registry.
- Never substitute a dense/Qwen model for a sparse candidate.
- Any model load must first verify GPU ownership, port 8188, thermal headroom,
  and the absence of a competing backend.
- A transient Ollama model loaded by the operator may own GPU VRAM; observe it
  and do not stop or evict it without an explicit request.

## Remaining work

1. Only after a fresh GPU decision, optionally run
   `run_bamboo_dpo_raw_completion_diagnostic.ps1 -Execute`. It must not be
   reported as instruction-following quality.
2. Obtain an exact source-backed Bamboo-DPO chat/instruction format before any
   chat-routing or instruction-quality review.
3. Require a separate human promotion decision before any registry, server,
   proxy, picker, or router change.

All other remaining general-agent, phone, worker-farm, archival, portfolio, and
3D tasks remain tracked in `TODO.md`.
