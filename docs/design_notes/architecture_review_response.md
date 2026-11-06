# Design note — response to the external architecture review

_Authored 2026-08-24. Assessment of an external constructive-criticism list, graded
against the actual codebase. Verdicts: already-built / valid-new / wrong-stack /
philosophy-tension. The five "valid-new" items became UPGRADE 12; two were pushed back
on; several were already built._

| Item | Verdict |
|---|---|
| 1.1 Explicit `keep_alive` on queued jobs | **VALID-NEW** — only `unload()` used it; normal requests kept Ollama's 5-min default. → UPGRADE 12. |
| 1.2 Quantized KV cache at 32K | **VALID-NEW** — flash-attn + q8 KV not configured; reclaims 2–4 GB. → UPGRADE 12 / researched in 18. |
| 1.3 Mid-job render pre-emption | **VALID-NEW** — watcher only checked before load, no mid-pass cancel. → UPGRADE 12. |
| 2.1 Hybrid dense+sparse retrieval | **VALID, already the plan** — BM25-first with a swappable scorer (02/05); prefer SQLite FTS5 over adding Chroma. |
| 2.2 Temporal/metadata filtering | **VALID** — retrieval already excludes archive/superseded; add status/recency metadata. |
| 2.3 Auto project-state summarizer | **PHILOSOPHY TENSION** — conflicts with the evidence-based, in-session CHANGELOG rule; `PROJECT_STATE.json` already covers machine state. Deliberately NOT added. |
| 3.1 Unified diff preview before write | **VALID-NEW** — `propose_file_diff` fits the "propose, don't auto-run" stance. → UPGRADE 12. |
| 3.2 Pydantic/Instructor/FastAPI validation | **WRONG STACK** — app is stdlib `http.server`, not FastAPI; native Ollama function calling already schema-validates with a malformed-arg refusal. Do arg validation in stdlib, no new deps. |
| 4.1 Interactive vs batch queue priority | **VALID-NEW** — a live phone capture should jump background frame extraction. → UPGRADE 12 + 14. |
| 4.2 Background completion alerts | **VALID, re-routed** — 06b already specs notifications; the phone path is now Sideband/LXMF, so phone alerts ride LXMF, not PWA push. |
| 5.1 Cursor/resumable streams | **VALID, on the roadmap** — SSE is localhost-only; mesh needs chunked/resumable (Sideband transport track). |
| 5.2 Identity permission matrix | **ALREADY BUILT** — Sideband Phase 1 built a per-identity permission layer (default-deny state-changing tools). |

**Bottom line:** technically credible and mostly aligned with where the project already
is. About half were already built or planned; the five genuinely new items were folded
into UPGRADE 12. The reviewer named tools the project does not use (FastAPI, Pydantic,
Chroma), which is the tell that it was written from a general description, not the code —
so the intent was adopted, the specifics were corrected to the real stdlib stack.
