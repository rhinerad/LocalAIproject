# Codex — paste everything below the line

---

You are operating the **Equal Shares** film pipeline. Working directory:

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

This folder is the canonical working tree. The `outputs` folder one level up is a stale fork frozen at 2026-08-10 01:43 — never read state from it.

Python for everything: `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe`

## Read before acting

`docs/VOICE_CLONING_MODULE.md`, then `CLAUDE.md`, `docs/PROMPT_STYLE_RULES.md`, `docs/MANUAL_COMFYUI_SETTINGS.md`. Skim `PROJECT_CONTINUATION_BRIEF.md` for state.

## Your task

Get every speaking character a voice reference sample, stop at the human approval gate, and after a human approves, clone the voices. `work/voice_manager.py plan` has already run; `voice_approval_gate.json`, `render_priority.json` and `voice_sample_clips.json` exist.

### Step 1 — extract what already exists

```powershell
& $Py work\voice_manager.py extract --all
```

`00A`, `11B`, `13B`, `14D`, `22B` are rendered, giving Narrator, Kent, Doris, Terminal voice and Doris recording. Thirteen will report "not rendered yet" — expected, not an error.

Then `& $Py work\voice_manager.py review` and report the table.

### Step 2 — render the remaining thirteen

Twelve VOX clips (specs in `outputs/equal_shares/voice_sample_clips.json`) plus story clip `25A` for Avery.

**Before launching anything**, verify all three:

1. running `python`/ComfyUI processes
2. whether port 8188 is listening
3. the tail of `outputs/equal_shares/runtime/render_supervisor.log` against the current clock

If that log is advancing, a render is alive — monitor it, never start a second. Exactly one process may hold port 8188 and the GPU.

For each VOX clip: prompt text is the `prompt` field plus the `dialogue_timing` line, or use the ready-made files at `A:\Users\rhine\Desktop\EQUAL_SHARES_GENERATION_LIST\vox_prompts\<CLIP_ID>.txt`.

**Non-negotiable settings, every clip:**

- `ResolutionSelector`: aspect_ratio `16:9 (Widescreen)`, megapixels `0.3`, multiple `32`
- 20 steps, `res_multistep` / `simple`, denoise 1.0, 24 fps, 8-bit
- Model `minimax_h3_fl2va_pruned_int8_convrot.safetensors`. Never Turbo — no Turbo model, node or LoRA.
- Frame count rounds up to the next value congruent to 5 modulo 17. The specs already contain the correct `frames`.
- **VOX clips are SINGLE ANCHOR. Leave the last-frame input disconnected.** A closing frame forces the take to arrive at a pose, which fights thirteen seconds of talking.

The saved workflow ships with `1:1 (Square)` in `ResolutionSelector`. It has never matched what actually ran, because the runner overwrites that field. Set it by hand every time.

VOX renders go to `story/VOX_<CHARACTER>/`. **Do not add VOX clips to `story_config.json` or `manifest.json`** — they are not part of the film and must not reach the completion audit.

After rendering, run `& $Py work\prompt_integrity.py verify --since <today>` and report anything corrupted in transit.

### Step 3 — extract the rest, then STOP

```powershell
& $Py work\voice_manager.py extract --all
& $Py work\voice_manager.py review
```

**STOP HERE. Do not approve anything.**

The approval gate exists because a human has to *listen* to each sample. You cannot evaluate audio. Do not set `approved: true`, do not edit `voice_approval_gate.json`, do not run `voice_manager.py approve`, and do not run `clone`.

Report: which characters have samples, their durations, which are still missing and why. Then tell the human to run:

```powershell
.\work\voice_review.ps1 -Listen
```

and wait.

### Step 4 — after the human approves

Confirm the gate is open before anything else:

```powershell
& $Py work\voice_manager.py gate    # exit 0 open, 1 closed
```

If it exits 1, stop and report why. If 0:

```powershell
& $Py work\voice_manager.py clone --character Narrator
```

Do **one** character first. Inspect the full API response before looping — the upload and clone response envelopes are unverified, and the code's field extraction may need adjusting to what the account actually returns. `MINIMAX_API_KEY` comes from the environment; never write a key to disk or into any file you commit.

Then clone the remaining approved characters one at a time, reporting each.

## Standing rules

- Never delete a raw attempt. Everything stays under `A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\`.
- Never hand-edit `manifest.json` or `visual_audit.json` while a render is active.
- Mechanical validity is not acceptance. "N/124 valid clips" counts renders, not approvals; never report it as an acceptance count.
- Reject footage for warped or duplicated bodies, broken faces or hands, identity or wardrobe drift, unintended people, wrong blocking, severe flicker, or visible gibberish text.
- A VOX clip only needs to be *audibly* good. Judge it on speech, not composition — it is never seen.
- If a VOX clip produces gibberish speech, that IS a failure for this purpose, unlike normal clips where H3 audio is discarded.

## Reporting

Concise plain language at meaningful changes and roughly once a minute during long work: current clip or stage, status, pass or fail with reason, next step, updated counts. No raw log dumps. Do not stop working merely to report — except at the approval gate, where stopping is the point.

Begin with Step 1 and report the review table.
