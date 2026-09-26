# Upgrade 17 — Feedback promotion, exemplar retrieval, and dense video actions

## Status

**In progress, 2026-08-24.** Stages 17A, 17B's local storage/retrieval path, 17C's
attribution/lifecycle path, and 17D's deterministic dense-action coverage contract
are implemented and tested. The operator
explicitly approved local ChromaDB plus Ollama `nomic-embed-text` (274 MB); no
external dataset was downloaded or ingested. Dense video-action evaluation (17D)
and any future external corpus remain separately gated.

## Existing foundation

- The GUI feedback controls and `feedback.py` already support explicit feedback.
  Helpful/correction events are audit-only; only an operator-written reusable
  rule is saved to durable memory.
- Feedback records retain a response fingerprint, not raw prompt/output text.
- `extract_video_actions` already provides timestamped action analysis, routes
  through the media queue when ComfyUI owns the GPU, and releases the lazy VLM
  after media work completes.
- The vision runtime is the operator-selected exact Qwen2.5-VL Caption V4 GGUF
  with its matched projector. **MiniCPM is explicitly out of scope.**

## Proposed stages

### 17A — Encrypted, reviewable feedback promotion

Add an atomic structured local feedback store at `local_agent/feedback_store/`
for operator-approved candidates. Records must retain the source conversation,
correction/rating, category, and promotion state. Promotion stays explicit: no
silent chat mining, no automatic training from thumbs-up, and no self-modifying
code.

The default record is **rule-only**: query SHA-256 fingerprint, rating,
operator-supplied distilled rule, category, and no raw transcript. Before any
raw prompt or model output is stored, the operator must explicitly opt in to a
**full-sanitized** payload intended only for later local training-data curation.
That sanitizer must redact home/drive paths, email addresses, authentication
tokens, and API keys before storage.

All feedback records are to be encrypted at rest with authenticated AES-256-GCM.
Encryption runs only in a background worker after CPU and GPU are confirmed idle;
it never competes with a render, chat, or media analysis. Key material must not
sit beside the encrypted records—use an operator-controlled secret or a
Windows-protected local key store. Failed encryption leaves the record safely
pending; it never falls back to plaintext without an explicit operator decision.

### 17B — Curated exemplar retrieval

Add an optional local exemplar store with three categories:

1. video-prompt patterns;
2. ComfyUI workflow topologies;
3. screenplay/story beats.

For applicable requests, retrieve at most two provenance-labelled examples and
inject a clearly labelled `<exemplars>` block capped at 800 tokens. General
ComfyUI examples must stay separate from Equal Shares examples. Templates never
override the operator's actual request or safety boundaries.

Chroma and local `nomic-embed-text` are now installed with operator approval.
Embedding uses the CPU-only Ollama endpoint with `num_gpu: 0`, four threads, and
`keep_alive: 0`; it never competes for render VRAM. The current stdlib BM25
retrieval remains the separate safe baseline for project documentation.

External data must first enter `local_agent/exemplar_staging/pending/` with its
source, license, category, domain, and status. The operator may approve, edit
and approve, or reject each item through a CLI or local GUI. Only approved items
with verified licensing and format compliance may enter an active collection.
Rejected records are retained as rejected, never silently re-staged.

Pre-screen candidates before review: reject malformed workflow JSON, short/spam
video prompts, unavailable local node types, and semantic duplicates. Semantic
duplicate checks query only approved local items and refuse similarity above
0.90. Keep the normalized diff with the staged record so the operator reviews
what would be used.

For a native MiniMax H3 example, validate the result with
`validate_h3_prompt.py`. Do not add `[start-end s]` timing blocks: they are not
native H3 grammar. Use the established six sections, one-based tags, and
`[Shot N]` only where a real cut is intended.

### 17C — Exemplar attribution and lifecycle

When an approved exemplar is injected, record its IDs against that response.
Explicit feedback may update its positive/negative use counters without turning
the response itself into training data. At five or more rated uses, flag an
exemplar below a 0.40 positive-use ratio as `needs_review`. Archiving a stale
example is reversible and must preserve its provenance and review history; do
not hard-delete it automatically.

### 17D — Dense video-action evaluation

Improve output fixtures, timestamp alignment, action-change coverage, and the
prompt-building handoff for short clips. Keep the existing Qwen2.5-VL runtime,
lazy VRAM policy, queueing behind active renders, and evidence rules. Temporary
extracted frames may be cleaned; uploads and other evidence never are.

The dense extractor now passes an exact ordered frame/time table to the VLM and
requires one labelled line per observation window. Its result preserves the
requested windows and reports any missing frame labels explicitly. It does not
fill missing seconds with generated prose. Optional H3 source notes avoid
bracketed timing syntax, which is not native H3 grammar.

## Required safeguards

- HTTP remains `127.0.0.1`; `tools.py` stays a strict whitelist.
- Remote identities remain default-deny for writes, rendering, and ComfyUI stop.
- Never delete raw media, masters, output evidence, or manifests.
- Ordinary text chat never loads the vision model.
- Do not start a render merely to verify this work.
- Retain `validate_h3_prompt.py` at 124/124 valid.

## Acceptance plan

After the required operator approvals, add tests for feedback promotion,
sanitization/encryption state, exemplar provenance/retrieval/token cap, staged
approval/rejection, lifecycle attribution, media queue routing, and timestamped
action formatting. Run the full suite, `agentic_eval.py`, and 124/124 validation.
Measure prompt overhead and usefulness with operator-approved examples before
calling the upgrade complete.
