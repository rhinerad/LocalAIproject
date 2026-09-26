# 2026-08-26 — local-agent GPU permission gateway

## Added

- `local_agent/gpu_gate.py`: persistent, stdlib-only operator gate. Default is
  `ask`; an approval grants exactly one local-agent GPU model-load attempt.
- Sidebar GPU gateway card showing the current policy, router-observed GPU
  state/process evidence, pending workload requests, and approve/deny actions.
- Local-only APIs: `GET /api/gpu_gateway`, `POST /api/gpu_gateway/mode`, and
  `POST /api/gpu_gateway/decision`.
- `local_agent/test_gpu_gate.py` verifies request de-duplication, one-shot
  approval, block mode, and allow mode.
- `local_agent/file_edit_gate.py`: explicit, one-shot content-fingerprint
  approval for `.ini`, `.cfg`, `.json`, `.bat`, and `.vbs` writes. The GUI
  shows the path, size and hash, never the contents in its approval card.

## Safety boundary

The gateway controls workloads initiated by the local agent. It exposes safe,
known controls for resident Ollama models, queued media, and ComfyUI. It does
not attempt to terminate arbitrary Windows processes merely because they appear
in telemetry.

## Verification

- `python local_agent/test_gpu_gate.py`
- `python -m py_compile local_agent/gpu_gate.py local_agent/server.py local_agent/agent.py`

## Follow-up: conversation refresh persistence

- The conversation files and `/api/chats` listing were confirmed intact. The UI
  had been resetting to a blank new-chat view on browser refresh. It now stores
  only the active conversation id in browser local storage and reopens it after
  refresh; New chat and Delete intentionally clear that selection.

## Follow-up: cross-chat continuity

- Added local lexical retrieval over relevant excerpts from prior desktop chats.
  The agent marks the reuse in its activity trace and labels it non-authoritative,
  so it can avoid repeating discovery without turning an old answer into proof.
- `python local_agent/test_chat_retrieval.py` passes (2/2).

## Follow-up: difficult-task planning assist

- An 8B abliterated chat can request one bounded 14B abliterated planning
  assist for a clearly difficult request without changing the model pinned to
  the conversation. The existing GPU gateway still decides whether that load
  is allowed; GPU-owned and CPU-only routes skip it deterministically.
- Planner output is accepted only as an inert structured checklist and is
  explicitly non-authoritative. Tool results remain the only evidence of a
  completed action.
- `python local_agent/test_difficulty.py` passes (2/2).

## Regression evidence — 2026-08-26

No model was loaded and no render was started for this regression pass.

- Native structured tool calling and render preflight: 21/21.
- GPU/CPU router switching: 20/20.
- GPU arbitration, media pre-emption, exact-Qwen lazy watcher, queue gate,
  cross-chat retrieval, difficulty routing, LXMF Tier B guard, and launcher
  revision tests: all passed.
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`:
  **124/124 valid**.

## Test-state isolation repair

- Native tool-calling tests now redirect the GPU-gate state file to a temporary
  directory for each test. Synthetic chat and render approvals can no longer
  leave misleading cards in the operator's live GPU sidebar.
- Cleared nine already-created synthetic pending cards; no real GPU workload
  was started. Re-ran native tool calling: 21/21 passed and the live pending
  card count remained zero.
