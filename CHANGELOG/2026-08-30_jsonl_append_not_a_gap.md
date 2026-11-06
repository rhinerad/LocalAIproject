# 2026-08-30 — JSONL append in learning.py / phone_scheduler.py is not a gap

Closes the loose end from
`CHANGELOG/2026-08-30_architecture_refactor_reverify.md`: two of the 14
audited writers still use `open(..., "a")` for JSONL. Production code was
not changed.

## What those files actually re-read

**`learning.py`**

- `record()` appends one JSON object + newline to `runtime/learning/failure_ledger.jsonl`.
- It then updates `runtime/learning/self_review.json` with
  `atomic_write_text`.
- `_load()` / `prompt_block()` read **only** `self_review.json`
  (`json.loads(REVIEW.read_text(...))`, empty dict on any exception).
- Nothing in `learning.py` parses the JSONL ledger. A truncated last ledger
  line is unused forensic residue; the counts that affect prompts live in
  the atomically replaced JSON file.

**`phone_scheduler.py`**

- Durable job state is `runtime/lxmf/phone_schedules.json` via `_load` /
  `_save` → `atomic_write_text`.
- `_load` already treats `JSONDecodeError` as empty `{jobs: {}}`, so a
  corrupted **state** file fails closed rather than poisoning dispatch.
- `_audit()` appends to `phone_schedule_audit.jsonl`. `dispatch_due`,
  `list_for_identity`, `create`, and `cancel` never read that file.
- The only JSONL parse in-tree is a test helper:
  `json.loads(AUDIT.read_text().splitlines()[-1])` in
  `test_audit_records_the_counter_that_was_queued`. That is not a runtime
  reader.

A crash mid-`write()` of a JSONL line can leave a truncated **last** line.
That cannot destroy earlier lines, and it cannot break the next operational
read, because those reads do not parse the JSONL files.

Atomic tmp-replace of the whole log would be the wrong tool: it rewrites
history on every event. Skipping a truncated last line would only matter if
something replayed the ledger; nothing does.

## Tests this session

```
python local_agent/test_phone_scheduler.py -v
Ran 14 tests in 0.804s
OK
```

`learning.py` has no dedicated test file. `test_prompt_prefix.py` only
mentions learning in passing and was not needed for this read-path check.

## Verdict

Not a gap. No writer or reader change.
