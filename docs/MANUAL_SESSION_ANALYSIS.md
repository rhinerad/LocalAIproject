# Your manual ComfyUI session — reconstructed

Recovered from ComfyUI's own PNG metadata. Every generation writes a PNG beside the video, and ComfyUI embeds the entire API graph in that PNG's `prompt` text chunk, so the session is fully recoverable — clip, anchors, duration, aspect ratio, seed, steps, and the exact prompt text that was submitted.

**24 attempts, 20:31 to 01:46. 7 videos kept. 29 % keep rate.**

## What you did, in order

| Time | Clip | Anchors | Attempts | Kept |
|---|---|---|---|---|
| 20:31–22:17 | `00A`/`00C` hybrid — **not a configured pair** | `narrator_close_v3` → `entry_start_v2` | 8 | `MiniMax_H3_00002` |
| 22:32–00:25 | `00B` revised pull-back — **not a configured pair** | `narrator_close_v3` → `boundary_00_v2` | 7 | `00003`, `00006` |
| 00:32 | `00C` | `boundary_00_v2` → `entry_start_v2` | 1 | `00007` |
| 00:40–01:15 | `00D` | `entry_start_v2` → `boundary_01_v2` | 5 | `00008` |
| 01:28–01:38 | `00D2` | `boundary_01_v2` → `boundary_02_v2` | 2 | `00009` |
| 01:46 | `00E` | `boundary_02_v2` → `boundary_03_v2` | 1 | `00010` |

**You left off having just rendered `00E`. Next in story order is `00F`.**

`00D` cost five attempts and `00B` seven — the same clips, roughly the same ratio as the automation's history. `00C`, `00D2` and `00E` came quickly.

## Three problems the metadata exposes

**The first eight runs were rendered at 1:1 Square.** Every run from 20:31 to 22:17 has `ResolutionSelector.aspect_ratio = "1:1 (Square)"`. You fixed it at 22:32 and everything since has been 16:9. This is the trap in `MANUAL_COMFYUI_SETTINGS.md`: the saved workflow ships with 1:1 and the automation only ever looked correct because the runner overwrites that field at submit time. Roughly two hours of work went into square renders. **Worth fixing the value inside both graph files so it cannot happen again.**

**Seven prompts arrived wrapped in quotation marks** — including the most recent, the `00E` run at 01:46. The submitted text begins `"One continuous unbroken take.` and ends `…never leaves the window."`, so the entire prompt is one quoted string.

That is almost certainly a copy-paste artefact: CSV wraps any field containing commas or newlines in double quotes, so copying a cell out of the raw `generation_list.csv` in a text editor brings the escaping with it. It matters because the prompt also says *spoken words appear only inside quotation marks* — wrapping the whole prompt in quotes tells the model the entire thing is a line to be spoken. This is very likely a contributor to the random speech you noticed.

**Fixed:** there is now a `prompts\` folder with one `.txt` per clip, 124 files, containing exactly the column-U text with no escaping. Copy from `prompts\00F.txt` rather than from the CSV.

**Rejected raws were deleted.** The video numbering has gaps — `00001`, `00004`, `00005` are gone — and only 7 of 24 attempts survive. That is your call in your own workspace, but it does mean the failed attempts can no longer be compared against the keepers, and it is the one house rule the project otherwise holds firmly. The automation preserves every attempt.

## What your workflow does that the automation does not

Comparing your graph against `proven_manual_minimax_h3_api.json`, the model stack is identical — same UNet, same `qwen3vl_32b` text encoder, both VAEs, `res_multistep` / `simple`, 20 steps, denoise 1.0, 0.3 MP. You have not changed resolution.

You added three things:

**1. Automatic frame count.** A `PrimitiveFloat` duration feeds a `ComfyMathExpression`:

```
max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17
```

That is exactly the 5-mod-17 rule, computed in the graph. You type 8.0 and the length derives itself. The runner already does this in Python, so the automation matches — but this is a real improvement for manual work and removes the one number that is easy to get wrong by hand.

**2. Last-frame extraction.** `SaveVideo` → `GetVideoComponents` → `GetImageSize` → `ComfyMathExpression` (`min(max(int(a if a >= 0 else b + a), 0), b - 1)`, with `a = 361`, which clamps to the final frame) → `ImageFromBatch` → `SaveImage`. Every generation also saves its own last frame, so the end of one shot can become the opening anchor of the next.

The automation had no equivalent. It does now — `work\save_last_frames.py` does the same thing with ffmpeg, which keeps the proven graph untouched and works retroactively on clips rendered before the idea existed.

**3. A dead node.** `ImageScaleToTotalPixels` at 1 MP (node 119) feeds only a `GetImageSize` that feeds nothing, and its own image input is unconnected. It has no effect on generation. If that was an attempt to upscale the reference images, it never took — worth deleting or wiring up deliberately.

## Two anchor pairings that are not in the config

Your `00B` runs use `narrator_close_v3` → `boundary_00_v2`. The config has `00B` as **single-anchor** from `boundary_00_v2` with no last frame. Your pairing is the corrected pull-back and it is better, but the automation will not reproduce it until the config is changed:

```json
"first_frame": "frames/scene_000/boundary_narrator_close_v3.png",
"last_frame":  "frames/scene_000/boundary_00_v2.png"
```

Your first eight runs use `narrator_close_v3` → `entry_start_v2`, which is not any configured clip. It spans what the config splits into `00A` and `00C`. I have not guessed at what you intend — if those two are merging into one shot, the config needs to say so, and `00A`'s and `00C`'s durations and narration need reconciling.

## New tools

`work\scan_manual_runs.py` — regenerates this whole analysis from the PNGs at any time, including the resume point. Read-only.

```
python work\scan_manual_runs.py --since 2026-08-10T18:00
```

`work\save_last_frames.py` — the last-frame chain, as a post-step.

```
python work\save_last_frames.py --only 00E
python work\save_last_frames.py            # every clip in the manifest
```

Both tested. Output lands in `outputs\equal_shares\frames\derived_last_frames\`, and those are derived images, not approved references — inspect before using one as an anchor, and never overwrite anything in `frames\scene_###`.

## To resume the automation at `00F`

Decide the two config questions above first, then:

```powershell
$Py = "A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe"
& $Py ".\outputs\minimax_story_runner.py" ".\outputs\equal_shares\story_config.json" --check
& $Py ".\work\render_until_complete.py"
```

The supervisor picks the first unresolved clip from the manifest, so it will not redo `00A`–`00E`. Note that it renders from `story_config.json`, not from column U — the prompt rewrites live in the CSV and have **not** been written into the config. Running the supervisor as-is will use the *old* prompts. Ask before doing that if the point is to test the new ones.
