# Operator-approved agent evaluation intake — 2026-08-24

## What changed

- Added `local_agent/operator_eval.py`, a local-only intake and deterministic
  scorer for anonymized operator-written evaluation cases.
- A case starts in `local_agent/eval_cases/pending/` and moves to `approved/`
  only through the explicit `approve` command. The tool does not inspect,
  summarize, or mine any chat history.
- It rejects absolute paths, email addresses, unknown tool names, contradictory
  required/forbidden tool assertions, oversized prompts, and malformed cases.
- Scoring evaluates a manually captured answer and tool trace against the
  operator's required/forbidden tools and required phrases. It cannot judge
  unstated factual quality and therefore does not pretend to be a completion
  grader.

## Safety

This is not an autonomous benchmark runner: it does not call Ollama, load the
vision model, access chats, open HTTP, or start a render. A live model
evaluation remains a separate operator request after an approved, anonymized
case exists.

## Verification

- `python -m unittest local_agent.test_operator_eval` — 2 passed.
- `python -m unittest discover -s local_agent -p 'test_*.py'` — 117 passed.
- `python local_agent/agentic_eval.py` — 5/5 passed with mocked calls; no model
  or render was started.
- `python local_agent/validate_h3_prompt.py --dir
  outputs/equal_shares/prompts_native_r2v` — 124/124 valid.
