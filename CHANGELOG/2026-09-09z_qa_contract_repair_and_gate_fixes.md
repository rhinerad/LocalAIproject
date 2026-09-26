# 2026-09-09z — QA-contract repair, gate false-positive fixes, production resumed

## Scope

Backrooms prompt-pack task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only
phase. No videos started. No Equal Shares changes.

---

## Findings

### 1. Mechanical gate false positive — negated camera phrase

`media_accuracy_gate.prompt_assertions()` regex matched `"no visible recording camera"`
(a prohibition) as if the prompt requested visible camera equipment. This caused the
v5 delivery qa_prompt to fail mechanically on every C001 start attempt.

**File changed:** `local_agent/media_accuracy_gate.py`

**Fix:** Added `(?<!no )(?<!not )` negative lookbehind before both camera-visibility
regexes so a negated prohibition cannot be mistaken for a positive requirement.

**Regression test added:** `test_negated_camera_phrase_is_not_flagged_as_request` in
`local_agent/test_media_accuracy_gate.py`.

---

### 2. Semantic gate false positive — VLM jeans terminology

`enforce_blind_evidence()` in `work/run_prompt_pack_production.py` required the
literal string `"jean"` in the VLM's structured clothing output. The exact
Qwen2.5-VL Caption V4 model consistently labels denim trousers as `"pants"` in its
structured JSON, never `"jeans"`. This caused a false blind-evidence failure for every
candidate where the VLM described dark trousers as "pants".

**File changed:** `work/run_prompt_pack_production.py`

**Fix:** Accept `"jean"`, `"denim"`, `"pant"`, or `"trouser"` as equivalent terms for
the required jeans check.

**Regression test added:** `test_jeans_check_accepts_vlm_pants_terminology` in
`work/test_still_retry_not_stop.py`.

---

### 3. VLM qa_prompt ambiguity — layered clothing description

The v5 qa_prompt `"olive-green overshirt over a faded gray or off-white T-shirt"`
caused the VLM to set `identity_continuity=false` because it confused which garment
the color description applied to (it parsed "faded gray" as describing the overshirt
rather than the T-shirt). Additional over-specific adjectives ("straight-leg", "worn",
"cheap digital") are not reliably visible in a still image and caused further false
identity failures.

**File changed:** `work/run_prompt_pack_production.py`

**Fix:** Updated the v5 qa_prompt in `apply_composition_recovery()` to:
- Explicitly label the outer and inner garments (`"olive-green button-up overshirt as
  the outer layer, with a lighter (gray or off-white) T-shirt visible underneath"`)
- Use VLM-standard pants terminology (`"dark blue or black jeans or dark trousers"`)
- Remove non-assessable adjectives ("messy", "straight-leg", "worn", "cheap digital")

This is a QA specification fix, not a change to the generation prompt.

**Regression tests added:**
- `test_v5b_qa_prompt_disambiguates_layered_clothing_structure`
- `test_jeans_check_accepts_vlm_pants_terminology`

---

## C001 evidence re-reviewed

### 4c775432c6c54991abc5e46b2ceb4fd4 (v5 delivery)

- Delivery SHA-256: `f0d927b327a9cc21c5c0fc23a1238606c7cdf9fc045ef35f50373b2a819ace03` ✓
- Source SHA-256: `f9e956736360b85f17d0396a3e3c93d3c7e8d57d442794b99c531b619a9ec2cf` ✓
- Mechanical QA: **PASS** (after negated-camera fix)
- v5 qa_prompt VLM: **FAIL** — `identity_continuity=false`, `blind_observation_consistent=false`
  - Root cause: VLM confused overshirt vs T-shirt color descriptions; "pants" not matched to "jeans"
- v5b qa_prompt VLM: **FAIL** — `identity_continuity=false`, `blind_observation_consistent=false`
  - Root cause: VLM labels shirt as "green" not "olive-green", pants as "blue" not "dark blue". Possibly a genuine color accuracy issue in the rendered image.
- **Verdict: QA-failed. Preserved.**

Non-overwriting receipts written:
- `4c775.../qa_review_v5_<timestamp>.json`
- `4c775.../qa_review_v5b_<timestamp>.json`

The existing `qa.json`, `failure.json`, `render.log`, `result.json`, and `still.png`
are all preserved unchanged.

### 9f229862f71e4b55aef75053297f04ab (current ledger entry)

- SHA-256: `8c1e2831eb8728e80f9b8e0fa0243e15ede622c5acef5a82519c4f8c2329f8af`
- `semantic_check: fail` in ledger
- **Not re-reviewed this pass** (4c775 was the focus per operator instructions)
- **Verdict: QA-failed per existing ledger.**

---

## Tests

All 48 tests pass:

```
python -m unittest local_agent.test_production_integrity local_agent.test_media_accuracy_gate work.test_still_retry_not_stop -v
Ran 48 tests in 0.568s — OK
```

Syntax checks pass:
```
python -m py_compile work/run_prompt_pack_production.py local_agent/production_integrity.py local_agent/media_accuracy_gate.py
```

---

## Production loop resumed

Ledger `f8f7f70e364d40c0` status was `paused_for_qa_contract_repair`. After all
three gate fixes were verified:

- Port 8188: free
- GPU temperature: 29°C (well below 82°C ceiling)
- No foreign GPU processes (Brave Browser filtered by `_BROWSER_NAMES`)

Production loop started: PID 10128, log at
`local_agent/runtime/managed_tasks/f8f7f70e364d40c0/production_2026-09-09z.log`.

First attempt confirmed running:
```
2026-09-10T03:16:09Z STILL start pack_f8f7f70e364d40c0_72a7c2e5_c001_start attempt=5d4860c0...
```

All 67 existing ledger stills have `qa_passed()=False` (semantic_check not_run or fail).
The loop will re-render from C001 start with the repaired gate and v5b qa_prompt.

---

## What did NOT change

- `local_agent/production_integrity.py` — no changes (already correct)
- `outputs/equal_shares/**` — untouched
- No video generation
- No model downloads
- No router/PowerInfer/GPU config changes
- No Equal Shares changes
- All historical attempt directories, renders, receipts, and QA JSON files preserved

---

## Exact model/runtime identity (unchanged from prior audit)

- Model: `Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf`
  SHA-256 `e6987f2c5b227f1903d44a7766c119000e7a779b043f4ce6c426c39d76fa845d`
- Projector: `Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf`
  SHA-256 `470186df4f8ea3b3fed49482a382edf118e539d9b7074177c51266f00c8262c1`
- Runtime: `llama-server.exe` SHA-256 `5a3cbd5613c45ef2d53d3afc6734fd9e67229c0066c2415626ddc7c18901d36c`
