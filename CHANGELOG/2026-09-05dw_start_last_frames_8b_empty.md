# 2026-09-05dw — START/LAST frames turn: CAP_LOGIC 8B empty completion

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dw**.

Diagnosis only. No `APP_REVISION` / router / GUI change.

Transcript: `local_agent/chats/e33dc77b94e4450c.json` (newest by mtime).
Pinned `huihui_ai/qwen3-abliterated:14b`, workspace `auto`. Last route
matches the live who-line: GPU / 8B / ctx 32768 / `capability=logic` /
`GPU free — media VRAM pressure` / `backend=ollama`.

## Operator prompt (not retyped)

First user message starts:

```
AGENT TASK: make START and LAST still frames for an 8-clip POV scene.
Do not generate video yet. Images only.
```

Then four attached reference images with the desktop instruction
`Call analyze_image on this path now`. Prompt length **5139** chars
(attachments included). Asks for 16 stills (`clip01_start.png` …
`clip08_last.png`), photoreal, identity lock, then stop (no video).

Assistant stored content is only `_EMPTY_COMPLETION_REPLY`.
`tool_evidence` and `media_artifacts` are empty. Activity is two hops
of route/review/decide on 8B, then `complete` — no `tool`, no `write`.

## 1. Why CAP_LOGIC, not an image-tool path

`classify_capability` does **not** look for still-frame / Comfy /
`plan_story_image` / `render_story_image` / `comfy_generate` keywords.
Order:

1. pinned Qwythos → tool; DeepSeek → logic; Coder → code
2. `_CODE_SIGNAL` → code
3. `difficulty.needs_escalation(text)` → **logic**
4. else **tool**

`difficulty.needs_escalation` is:

```
len(text) >= 700  or  len(_SIGNALS.findall(text)) >= 2
```

Reproduced on this prompt: `len=5139`, **zero** `_SIGNALS` hits
(`architect|refactor|implement|debug|…`), `needs_escalation=True` from
**length alone**. Same result unpinned. Image words are present
(`still frame`, `image`, `generate`, `ComfyUI` in a filename) and never
consulted.

For this **pinned Huihui-14B** chat, `CAP_LOGIC` does **not** swap in
DeepSeek (`want_capability_gpu` requires unpinned or a DeepSeek/Coder
pin). The stamp is labeling only; the GPU schema stays the full tool
catalog. The miss is: a 5k-char image-generation brief is classified
as “deep logic” because it is long, not because image-gen regex failed.

Unpinned `auto_farm` would also be `CAP_LOGIC` here, so it would **not**
go to Qwythos (`CAP_TOOL` only). That is a separate product question.

## 2. Why “media VRAM pressure” demoted 14B → 8B

`router.decide` (after picking PRIMARY 14B on a free GPU):

```
if media_pressure() and selected is PRIMARY:
    selected = 8B, reason = "media VRAM pressure"
```

`media_pressure()` is true iff `local_agent/runtime/media_vram_pressure.json`
exists. The watcher sets it in `_prepare_vision_batch` on
downgrade/evict **before** the VLM is proven up, and clears it only in
`_release_vision_batch` after `vision_ran`. If `ensure_qwythos`/VLM
start fails, `tier is None`, `vision_ran` stays false, **the file is
leaked**.

Live file at diagnosis: `{"at": 1788645468.241625}` — same timestamp as
the earlier `see_image` chat `018792416a6a4baa` (queued, watcher never
completed). This START/LAST turn is ~90 minutes later. Route detail:
`gpu_busy=false`, `8188 closed`, `vram_used_mb=9679`, resident **8B**,
Brave + llama-server. Not a Comfy render. The 8B demotion is a **stale
watcher flag**, not a live media job on this turn.

8B on GPU uses `num_ctx=32768` (fallback reasoning). That matches the
who-line ctx.

## 3. Empty 7-item list vs empty completion

Same harness as cn/de: `if not hop_calls and not reply.strip()` → retry
once with think disabled → `_EMPTY_COMPLETION_REPLY`. Activity shows
exactly that two-hop empty pattern (no tools, no write). The stored
answer is the fallback string, not a numbered list.

The operator-visible “7 blank items” were **not** saved. Best fit: the
seven activity cards (route, review, decide, route, review, decide,
complete) and/or a think-block enumerating CLIP 1–7 that
`_VisibleTextFilter` discarded so `reply` stayed empty. Not a new
parser bug.

Contributing, not this hop’s failure: attachment copy still says
`analyze_image`; the real tool is `see_image`. If 14B had called the
instructed name it would have been `ERROR: no tool`.

## Root cause (short)

1. Long image-gen brief → `len>=700` → `CAP_LOGIC` (no image-tool class).
2. Stale `media_vram_pressure.json` from a leaked watcher prepare →
   pinned 14B forced to GPU 8B while the card was otherwise free.
3. 8B returned no visible text and no tool_calls twice → same empty-
   completion fallback as today’s 14B hops.

(1) did not by itself pick 8B on a Huihui pin. (2) did. (3) is the 8B
(and often 14B) empty-hop behavior on a huge structured prompt.

## Proposed fix (not built this pass)

**Simple / safe / clearly correct:** treat `media_vram_pressure.json` as
expired after a short TTL (and/or clear it when `_prepare_vision_batch`
returns None). That stops a failed VLM start from demoting every later
14B chat. Do **not** silently change Auto pinning. Do **not** send this
class of prompt to Qwythos just to get `CAP_TOOL`.

A keyword exception in `classify_capability` for still-frame / Comfy
generate is **not** clearly safe here: it would not have kept 14B on
this pinned chat, and unpinned it would farm-route a 16-still job to
Mac Qwythos.

## Files

- `CHANGELOG/2026-09-05dw_start_last_frames_8b_empty.md`
- transcript (unchanged): `local_agent/chats/e33dc77b94e4450c.json`
