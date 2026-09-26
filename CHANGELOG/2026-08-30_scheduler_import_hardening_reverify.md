# 2026-08-30 — UPGRADE 23 scheduler + import-hardening re-verified

Fresh verification pass against `local_agent/UPGRADE/00_INDEX.md` row 23 and
`CHANGELOG/2026-08-28_scheduler_import_hardening_verification.md`. No production
code was edited. `router.py`, `tools/powerinfer/`, `work/`, `context_prefetch.py`,
atomic-write helpers, and Chroma singleton code were not touched. No GPU, no
downloads, no Equal Shares, no Harmontown, no PowerInfer, no Sideband live
phone test.

## What changed

Nothing in the product. Evidence only. This session re-ran the scheduler suite
and independently probed import-hardening in a new Python process.

## Why

Row 23 still cites the 2026-08-28 claim: missing ChromaDB/cryptography leaves
`agent` and `server` importable with actionable capability status, and "all 12
scheduler safety/wiring tests pass." The count 12 was not trusted; the live
phone job remains flagged unverified and was skipped.

## The evidence

Interpreter: PATH `python` 3.12.10
(`A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe`).
cwd: `local_agent/`.

### 1. Scheduler suite (real count this session)

```
python -m unittest test_phone_scheduler -v
Ran 14 tests in 0.760s
OK
```

All 14: registration (2), source-binding (4, including
`test_counter_only_phone_request_defaults_to_counter_template`), dispatch (6),
bridge wiring (2). Failures: 0. Errors: 0.

The 2026-08-28 note said **12**. The suite grew (already visible in
`CHANGELOG/2026-08-30_architecture_refactor_reverify.md`). The safety claims
still hold; the number 12 is stale.

No other `test_*scheduler*` or `test_*import*` files exist. Import-hardening
lives in `test_optional_deps.py`.

### 2. Import-hardening unit tests

```
python -m unittest test_optional_deps -v
Ran 22 tests in 35.509s
OK (skipped=2)
```

Skipped because chromadb and cryptography **are** installed, so the
`capabilities` absence-path tests cannot fire in-process. The three
subprocess import-survival tests passed.

### 3. Independent new-process probe (not the unit test)

Packages were **not** uninstalled. A new interpreter set
`sys.modules["chromadb"] = None` and `sys.modules["cryptography"] = None`
(plus submodules), put `local_agent/` on `sys.path`, then imported `agent`
and `server`.

First probe attempt ran the script from `logs/` without adjusting `sys.path`
and died with `ModuleNotFoundError: No module named 'agent'`. That is a
probe-path trap, not a product crash. Second run inserted `local_agent/`
first. Result:

```
agent import: OK
server import: OK
exemplar_embeddings._CHROMADB_AVAILABLE = False
exemplar_embeddings._CHROMADB_REASON = chromadb is not installed (pip install chromadb). Exemplar retrieval and semantic deduplication are unavailable.
feedback_manager._CRYPTOGRAPHY_AVAILABLE = False
feedback_manager._CRYPTOGRAPHY_REASON = cryptography is not installed (pip install cryptography). Feedback records cannot be encrypted or stored.
semantic_duplicate: {"available": false, "reason": "...chromadb...", "install": "pip install chromadb"}
embed_record: {"status": "unavailable", "reason": "...chromadb...", "install": "pip install chromadb"}
sync_approved: {"unavailable": true, "embedded": 0, "reason": "...chromadb..."}
retrieve exception type: RuntimeError
retrieve exception: chromadb is not installed (pip install chromadb). ...
feedback_manager.status: {"available": false, "last_error": "...cryptography...", "install": "pip install cryptography"}
decrypt_envelope: {"available": false, "reason": "...cryptography...", "install": "pip install cryptography"}
find_spec('chromadb') = None
find_spec('cryptography') = None
capability('exemplar_retrieval'): {"available": false, "reason": "chromadb is not installed", "install": "pip install chromadb"}
capability('feedback_encryption'): {"available": false, "reason": "cryptography is not installed", "install": "pip install cryptography"}
```

Did not crash. Status objects name the package and the install command.
`find_spec` returns `None` when `sys.modules[pkg] is None`, so
`capabilities.py` reports the same absence under this simulation.

## What was verified after

- Scheduler wiring/safety: **14/14 OK** this session.
- Optional-dep suite: **22 ran, 2 skipped, 0 failed**.
- Simulated missing chromadb + cryptography: `agent` and `server` still
  import; public functions and `capabilities.capability(...)` return
  actionable unavailable status instead of a traceback.

## What is still unverified

- Real phone delivery (five messages / cancel / restart). LXMF queueing is
  not delivery. Operator-side Sideband test remains required. Skipped on
  purpose this session.
- `validate_h3_prompt.py` 124/124 was not re-run (standing gate, not this
  row's job).
- GUI start + answering a normal question with packages actually absent
  (the original UPGRADE 23 checklist item). Import + capability status
  were watched; a live GUI click was not.

## Verdict on the 2026-08-28 claim

**Holds**, with a count correction: scheduler tests are 14/14, not 12.
Import-hardening holds under `sys.modules` simulation without uninstalling
anything. No rewrite.
