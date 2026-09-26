# 2026-09-21p I2V receipt gate

- `gvd_qa/i2v_gate.py` `apply_qa_gate` runs before `--dry-run` and before Comfy submit. Missing receipt or `blocked.json` returns 4. Accepted receipt hash-locks the start frame.
- `generate_video.py` no longer skips the gate on dry-run.
- `master_batch_runner.py --qa-loop` accepts `--qa-receipt` or `--qa-candidate` (with `--qa-local`) as well as a generation graph. Ungated batches still pass `--allow-ungated-i2v`.
- Live: C017 start `blocked.json` refuses I2V; C017 end `accepted.json` binds `candidate.png`. Report: `local_agent/runtime/gvd_qa/smoke_i2v_receipt_gate.json`.
- Tests: `python local_agent/test_gvd_qa_i2v_gate.py`.
