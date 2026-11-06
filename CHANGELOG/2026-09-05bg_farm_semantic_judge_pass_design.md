# 2026-09-05bg — Farm semantic LLM-judge pass: design only; local-Ollama sub-decision closed

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05bg**.

## Sub-decision closed

TODO “Decide on an LLM-based judge pass… whether secondary machines get
their own local Ollama install or call back to the workstation's”:
**secondary machines use their own local Ollama.** Already true on
Louises-MBP: LaunchDaemon `system/com.local-agent.ollama` on
`127.0.0.1:11434`; `qwythos_evaluate` / summarize / embed call
`FARM_OLLAMA_HOST`; Qwythos keep_alive verified `2026-09-05o`/`aq`.
Workstation `:11434`/`:11435` callback is out of scope for this pass.

## Design (no build, no live judge)

`docs/design_notes/FARM_SEMANTIC_JUDGE_PASS_2026-09-05.md`:

- Follow-up Celery task on the existing `judge` queue, after mechanical
  `judge_transcript` (`judge_rubric.py` unchanged).
- Model: Mac CPU Qwythos-9B at local `:11434` (`num_gpu: 0`,
  `num_thread: 4`, `num_ctx: 8192`, `keep_alive: 30m`) so a second 8B
  does not evict the farm tool-calling resident (16 GB swap at 14.1 GB,
  `2026-09-04h`).
- Checks the TODO hole the regex cannot see: `bad_reasoning`,
  `weak_inference_on_vague_request`, `plausible_wrong_answer`, plus
  `judge_eval.FLAGS` overlap. Score 0–5.
- Advisory sidecar `farm-judge-semantic-verdict-v1` with `advisory:
  true`, `auto_accepted: false`; same four isolation layers as
  `judge_eval.py` (`2026-09-05af`/`aj`). Does not write `chats/`,
  `learning.record`, or mechanical `status`. Durable default **off**.
- No implementation, no `judge_transcript` run on real chats, no
  `APP_REVISION` bump.

## Files

- `docs/design_notes/FARM_SEMANTIC_JUDGE_PASS_2026-09-05.md` (new)
- `docs/design_notes/LLM_AS_JUDGE_PRESCORE_2026-09-05.md` (sibling pointer)
- `TODO.md` (decide item closed; build still gated)
- `CHANGELOG/README.md`
