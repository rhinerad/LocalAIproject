# 2026-08-19 — local_agent first live run: from built to working

## What changed and why

### 1. router.py — browser false-positive in GPU busy detection

**Problem:** On Windows WDDM mode, `nvidia-smi --query-compute-apps` lists ALL
processes with a GPU context, including Brave Browser (WebGL/display). Without
a filter, Brave permanently flagged the GPU as busy even with no render running.

**Evidence:** Real nvidia-smi output showed:
```
C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe
C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe
A:\Users\rhine\ComfyUI-Installs\Rockernow\standalone-env\python.exe
```
All three matched the "foreign process" check. Brave has no CUDA compute role.

**Fix:** Added `_BROWSER_NAMES` frozenset (`brave`, `chrome`, `firefox`,
`msedge`, `edge`, `opera`, `safari`, `iexplore`, `microsoftedge`, `vivaldi`,
`arc`). Foreign-process check now filters using `Path(p).stem.lower()`.
ComfyUI python.exe correctly remains in the "foreign" list.

**Safety preserved:** Port 8188 and queue-owner signals fire before the process
check in every test scenario. The filter is belt-and-suspenders, not the primary
guard.

### 2. router.py — model preference lists updated for installed models

**Problem:** CPU_MODELS and GPU_MODELS did not include the four actually-installed
models: `qwen3.6:latest` (23 GB MoE, 36B params), `dolphin3:latest` (4.9 GB),
`qwen3:8b` (5.2 GB), `qwen2.5-coder:14b` (9.0 GB). The fallback `_pick()`
logic would have returned the model with no preference ordering.

**Fix:**
- CPU_MODELS: `dolphin3:latest` first (4.9 GB, reliable tool protocol), then
  `qwen3:8b`, then legacy names, then `qwen2.5-coder:14b` as last resort.
- GPU_MODELS: `qwen2.5-coder:14b` first (9 GB, fits in 16 GB VRAM cleanly),
  then `qwen3.6:latest` (23 GB MoE, spills to RAM), then `qwen3:8b`, `dolphin3`.
- `qwen3.6:latest` moved to GPU-after-14B because at 23 GB it cannot fully reside
  in the RTX 5080's 16 GB VRAM; `qwen2.5-coder:14b` is the cleanest GPU model.

### 3. agent.py — tool result message prevented follow-up tool calls

**Problem:** After receiving a tool result, the user-turn injected into the
conversation said "Now answer the operator in plain prose." This prevented the
model from making a second tool call when the first result was insufficient.
Example: `clip_info` returns base seconds; to answer "what is the ladder?" the
model still needs to call `duration_ladder`. The old message caused it to answer
in prose with approximate values instead.

**Fix:** Changed to "If you now have everything needed to answer, do so in plain
prose. If you still need data from another tool to give an accurate answer, call
it now. Do not describe what a tool would return — call it."

### 4. agent.py — CONVERSATION_RULES strengthened for mandatory tool use

**Problem:** qwen3:8b (with Qwen3 thinking mode) would reason through answers
using the algorithm it learned from the system prompt, giving approximate values
rather than calling tools. Example: gave "14, 13, 16, 12..." as duration ladder
rungs instead of calling `duration_ladder` for the 17k+5 frame-quantized values.

**Fix:** Added explicit NEVER statements:
- "NEVER provide duration ladder rungs without calling duration_ladder"
- "NEVER give clip durations or frame counts from memory — call clip_info"
- "NEVER give project counts from memory — call project_state"

### 5. Model selection: dolphin3 over qwen3:8b for CPU tier

**Evidence:** qwen3:8b has thinking capability (`["thinking", "tools", ...]` in
model metadata). Its reasoning loop leads it to compute answers from algorithms
in the system prompt rather than calling tools. Gave wrong ladder rungs (integers
without frame quantization) on two separate attempts.

`dolphin3:latest` (4.9 GB, instruction-tuned, no thinking mode) correctly called
`duration_ladder {"clip": "00B"}` on first attempt and returned exact quantized
values: 14.375s/345f base, 13.375s/328f at rung 2, etc.

CPU_MODELS updated to prefer dolphin3 before qwen3:8b.

---

## Verified (this session, against real hardware)

| Check | Result |
|---|---|
| `router.py` reports real nvidia-smi output | ✓ RTX 5080, 16303 MB, parsed correctly |
| Port 8188 busy signal | ✓ ComfyUI running → GPU BUSY |
| Queue-owner PID busy signal | ✓ live PID → BUSY; released PID → idle |
| nvidia-smi VRAM busy signal | ✓ 5704 MB > 2500 MB → BUSY |
| Browser processes filtered (not flagged as busy) | ✓ Brave excluded, python.exe kept |
| GPU model evicted on CPU routing | ✓ `unloaded_gpu_model: qwen2.5-coder:14b` in route event |
| Forced GPU refused while render running | ✓ `reason=GPU requested but unavailable` |
| Forced CPU always honoured | ✓ |
| CPU tier picks dolphin3 (correct preference) | ✓ |
| New chat with id=null does not crash | ✓ |
| Conversation persists across server restart | ✓ |
| Rename, delete (to `_deleted/`) | ✓ |
| Stop mid-generation | ✓ 44 chars + `[stopped]` |
| Regenerate | ✓ re-ran from same user message |
| File attachment read by model | ✓ |
| duration_ladder called (not computed from memory) | ✓ dolphin3, exact quantized values |
| clip_info called for clip detail questions | ✓ |
| run_build check_config called for drift check | ✓ |
| classify_voices called for speaker questions | ✓ |
| General knowledge answered without tools | ✓ |
| Guard rails: 5/5 refused | ✓ |
| 124/124 prompts still valid | ✓ |
| 18 speakers = 10 recurring + 8 one-off | ✓ |
| draft_prompt validates and catches failure | ✓ E12: missing `<Audio 1>`, `safe_to_use: false` |
| START_LOCAL_AGENT_GUI.ps1 Ollama path correct | ✓ `A:\Users\rhine\AppData\Local\Programs\Ollama\ollama.exe` |
| CPU Ollama server starts on 11435 | ✓ CUDA_VISIBLE_DEVICES=-1 applied |

## Still unverified

- **GPU-idle → GPU-tier routing end to end.** ComfyUI was running on port 8188
  throughout this session. The GPU-free code path was not exercised. The eviction
  evidence (`unloaded_gpu_model` in the route event) confirms the CPU path works;
  the GPU-idle routing follows from code review but has not been exercised on a
  live idle card. Close ComfyUI and run `python local_agent\router.py` first.

- **Speed on GPU tier.** CPU tier measured: human-readable token rate on
  dolphin3:latest (4 threads, 4.9 GB). GPU tier speed is untested since the card
  was occupied throughout.

- **Whether the GPU model (qwen2.5-coder:14b) follows the tool protocol.** Only
  dolphin3:latest was tested on this session. If GPU routes to qwen2.5-coder:14b
  and it also ignores tools, switch to dolphin3 on both tiers or adjust the GPU
  preference list.

## Launcher (START_LOCAL_AGENT_GUI.ps1)

The PS1 script was not run as a unit in this session (the CPU server was started
manually from bash to avoid blocking the agent). The individual components were
all verified. The PS1 is structurally correct:
- Ollama path: verified to exist
- Environment variable inheritance via `[Environment]::SetEnvironmentVariable`:
  pattern is correct for PowerShell
- `Test-Server` early-exit if already running: works (GPU server was already up)
- Log paths use `$PSScriptRoot`: resolves to `local_agent/`
- The 30-second startup wait loop (700 ms × 30 iterations): conservative, should
  be sufficient

To use as the operator: run `.\local_agent\START_LOCAL_AGENT_GUI.ps1` from the
project root in a PowerShell terminal. It will start the CPU Ollama server if not
already running, rebuild the knowledge pack, and open the browser.

---

## Addendum — file and web access (same session)

Operator request: *"will you make sure that the agent will have file access and
internet access when available. I would like it to be able to reference
information from the internet. I also would like it to be able to change things
in my file system just like chatgpt desktop can."*

### What was added

Five new tools in `tools.py` (standard library only — nothing to install):

| Tool | What it does |
|---|---|
| `read_file` | Reads any text file by path (absolute or relative to project root). Max 12 000 chars. Refuses binary files. |
| `write_file` | Writes or creates a file. Refuses to overwrite protected records: manifest.json, audio_pass_manifest.json, visual_audit.json, generation_audit.json, voice_requirements.json, render_queue_owner.json, agent_questions.md. |
| `list_dir` | Lists a directory, up to 200 entries. |
| `fetch_url` | Fetches a URL via `urllib`, strips HTML to text via `html.parser`, returns up to 8 000 chars. Handles network errors gracefully. |
| `web_search` | Searches via DuckDuckGo Lite (no API key required). Returns numbered results with titles and snippets. |

HTML stripping (`_Stripper`): skips script/style/noscript/select/option/textarea/iframe; adds line breaks for block elements; collapses whitespace-only lines.

### Verified

| Check | Result |
|---|---|
| web_search calls through model | ✓ called `web_search {"query":...}`, returned real results |
| read_file calls through model | ✓ called `read_file {"path":"..."}`, correctly read content |
| write_file writes new file | ✓ created test file, confirmed content |
| write_file refuses manifest.json | ✓ ERROR: protected file |
| fetch_url refuses file:// | ✓ ERROR: url must start with http(s) |
| web_search refuses empty query | ✓ ERROR: query is required |
| read_file refuses non-existent | ✓ ERROR: not a file |
| 14 actions listed in /api/status | ✓ |
| example.com fetch + strip | ✓ clean text returned |

### Unverified

- Speed/quality of web_search answers with the CPU model on a longer fetch.
- How the model handles very large files (max_chars truncation path).
- write_file behavior on a file inside `ComfyUI-Shared/output/story/` — the
  protection is by filename only, not by path. Raw renders are in that tree but
  named as MP4/PNG, not in _PROTECTED_NAMES. If the operator asks to write a
  text file there, it will succeed.
