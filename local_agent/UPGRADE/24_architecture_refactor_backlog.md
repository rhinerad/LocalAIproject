# Upgrade 24 — pay down the architecture debt. No internet needed.

Paste everything below the line into Claude Code. Run any time; nothing here is
gated on another upgrade, though Job 5 touches the same function UPGRADE 12's
pre-emption/queue-priority work will touch — sequence them together rather than
as competing edits if both are in flight.

---

Read `docs/design_notes/architecture_audit_2026-08-27.md` first. It has the full
diagnosis with exact file:line evidence for every item below; this prompt is the
fix list distilled from it, in the same priority order (cheapest/safest first,
biggest/riskiest last). Nothing in the audit has been implemented yet.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## Ground rule

Every job below is a **structural extraction, not a behavior change**. Existing
tests are the contract: for jobs 1–4, the relevant test file must produce the
*same* pass count before and after your change, run red/green. If a test's
expected value has to change for your refactor to pass, stop and treat that as
a signal you changed behavior, not just structure — that is not what this
upgrade is for.

## Job 1 — one shared atomic-write helper (do first)

The tmp-write-then-`os.replace()` pattern is independently reimplemented under
four different names in 14 files: `agentic_state.py`, `exemplar_curator.py`,
`exemplar_embeddings.py`, `exemplar_lifecycle.py`, `gpu_gate.py`, `learning.py`,
`media_queue.py`, `media_watcher.py`, `memory.py`, `phone_scheduler.py`,
`remote_security.py`, `retrieval.py`, `router.py`, `store.py`.

Add `local_agent/atomic_io.py` with one function, `atomic_write_text(path: Path,
text: str) -> None` (parents created, `.tmp` sibling, `os.replace`), and a thin
`atomic_write_json(path: Path, data) -> None` on top of it for the many callers
that just do `json.dumps(...)` first. Migrate all 14 files to call it — either
by having each file's existing private helper (`_atomic`, `_save`,
`_write_atomic`, `_atomic_write`) delegate its body to the shared function, or
by replacing call sites directly. Either is fine; the on-disk output format and
every existing call site's signature must not change.

**Verify:** every test file for the 14 modules above stays green, individually.
There's no single command that covers all of them — run them as a batch and
list which passed.

## Job 2 — cache the Chroma client (write the concurrency test first)

`exemplar_embeddings.py:_client()` opens a brand-new `chromadb.PersistentClient`
on every call. `_collection()` calls it fresh each time, and `retrieve()`'s
per-category loop (line 108) opens one client **per requested category, per
call** — and this isn't just a background-thread cost: `exemplar_curator.py`'s
approve path and `exemplar_filter.py`'s staging path both call into this
synchronously, in the request path.

Before changing anything, write a test that races the existing 20-second
background `_worker()` against a foreground `retrieve()`/`semantic_duplicate()`
call against the same on-disk `exemplar_store/chroma` directory. This is the one
claim in the audit flagged as an unverified risk rather than a confirmed bug —
find out first whether it's real.

Then add a module-level singleton client guarded the same way `_WORKER`/
`_WORKER_LOCK` already guard the background thread, and have `_client()` return
the cached instance instead of constructing a new one. `retrieve()`,
`semantic_duplicate()`, `embed_record()`, `sync_approved()` must return exactly
the same shapes they do today.

**Verify:** `test_exemplar_embeddings.py`, the new concurrency test, and
`test_optional_deps.py` (the chromadb-absence guard reloads the module via
`sys.modules` stubbing — confirm the singleton doesn't break that reload path).

## Job 3 — deduplicate router.decide()'s fallback branches

`router.py:687–697` (primary-reasoning-pair CPU handoff) and `router.py:698–717`
(coding-model CPU handoff) resolve a paired CPU fallback, choose between the
CPU-tier store and the GPU-tier store with `num_gpu=0`, and build an
explanatory `why` string, in near-duplicate shape. Extract one shared helper
both branches call — same inputs (model, the two configured pair names, the
CPU/GPU installed-model lists) in, same `(selected_model, why_fragment,
detail_updates)` shape out.

**Verify:** `test_router_switching.py`, all 20 tests, run before and after —
this is the test that makes this extraction safe rather than a guess.

## Job 4 — one `num_ctx` value, not three

`router.py:221` (`CPU_OPTIONS`), `router.py:223` (`GPU_OPTIONS` base default),
and `ollama_client.py:52` (`DEFAULT_OPTIONS`) each independently declare
`num_ctx: 16384`. The third copy already carries a comment asking whoever edits
it to keep it in sync by hand — replace that comment with an import. Pick
`router.py` as the source of truth (it's the policy module), have
`ollama_client.py` import the value instead of redeclaring it, and add a test
asserting `ollama_client.DEFAULT_OPTIONS["num_ctx"] ==
router.CPU_OPTIONS["num_ctx"]` so a future edit to one side fails a test instead
of drifting silently.

**Verify:** the new equality test, plus `test_router_switching.py` and any
existing `ollama_client` tests stay green.

## Job 5 — decompose agent.answer()'s prefetch stage (biggest item; do last)

`agent.answer()` (agent.py:671–1047) runs five independent, hand-rolled
"inject context into `msgs`" blocks before the model ever sees the turn: URL
evidence (`add_supplied_url_evidence`), project-doc retrieval
(`_prefetch_requested_project_evidence`), prior-chat retrieval (the inline
`chat_retrieval` block), difficulty-based 14B escalation (the inline block using
`difficulty.needs_escalation`), and approved-exemplar retrieval
(`_prefetch_approved_exemplars`) — each with its own char-budget constant
(`MAX_TOOL_RESULT_CONTEXT_CHARS`, `MAX_URL_EVIDENCE_CHARS`,
`MAX_EXEMPLAR_CONTEXT_CHARS`, `DEEP_RESEARCH_RESULT_CONTEXT_CHARS`,
`MAX_CONTINUITY_TURN_CHARS`).

Pull these five behind one small interface — a `context_prefetch.py` module is
enough, it doesn't need to be elaborate — with a single named budget policy
replacing the five scattered constants. **Keep the call order and observable
behavior inside `answer()` identical at first.** This is purely making the
seams visible, not changing what gets injected or when.

This is explicitly allowed to be its own session if time runs out. If you stop
here, say so plainly in the CHANGELOG rather than claiming it — a partial
extraction left half-migrated is worse than not starting it, so either finish
cleanly or leave `agent.py` exactly as it was and note why.

**Verify:** `test_native_tool_calling.py` (27 tests) and `test_context_resilience.py`
stay green, unchanged pass count.

## Job 6 — fix the drifted status docs

`local_agent/UPGRADE/00_INDEX.md` row 12 still lists `propose_file_diff` as an
unbuilt "review item" — it is fully implemented and registered right now
(`tools.py:772–793`, schema at `tools.py:1519`). Correct that row. Then look at
whether `BUILD_STATUS.md`'s own superseded-banner target
(`docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-30.md`) is itself current; if it
isn't either, say so in the CHANGELOG rather than silently trusting the chain.
Do not try to unify all four status documents into one in this pass — that's a
bigger decision than this job — just fix the one concrete wrong claim and flag
what else you find drifted.

## Job 7 — optional, only if time remains

`chat_retrieval.py`'s bespoke term-overlap scorer duplicates what
`retrieval.py`'s `ScorerProtocol`/`LexicalScorer` already does properly. Not
required for this upgrade to be considered done; do it opportunistically if
Jobs 1–6 finish with room to spare, and skip it without comment if not.

---

## Verify — full regression sweep

- [ ] every test file touching the 14 Job-1 modules still passes
- [ ] the new Job-2 concurrency test, plus `test_exemplar_embeddings.py` and
      `test_optional_deps.py`
- [ ] `test_router_switching.py` — 20/20, run before and after Job 3
- [ ] the new Job-4 `num_ctx` equality test
- [ ] `test_native_tool_calling.py` (27 tests) and `test_context_resilience.py`,
      if Job 5 was attempted
- [ ] `python local_agent\validate_h3_prompt.py --dir outputs\equal_shares\prompts_native_r2v`
      still **124/124** — the standing gate, unrelated to this upgrade but never
      skipped
- [ ] `python -c "import tools; print(len(tools.schemas()))"` still **48** —
      nothing here adds or removes a tool

## Rules

- Never weaken a safeguard to make a test pass — the GPU-busy check keeps
  failing safe, `tools.py` stays a whitelist, the CPU thread cap stays at 4.
- Never delete a raw generation, reference, manifest, audit record, or source
  audio. Nothing in this upgrade should touch any of those anyway.
- Work through the jobs in order. 1–4 are small and independently safe; do them
  even if 5 doesn't happen. 6 can happen any time, including first, since it's
  documentation-only.
- Finish each job with a `CHANGELOG/` entry: what changed, why, the test
  evidence, what's still unverified. One entry per job is fine, or one entry
  covering all jobs completed in the session — either way, no job is "done"
  without its evidence recorded.

## Do not stop

Work straight through Jobs 1–4 and 6 in one session if possible. Job 5 is the
one legitimate place to stop and hand off to a follow-up session — but only
after 1–4 are complete and green, and only with a plain CHANGELOG note saying
exactly that.
