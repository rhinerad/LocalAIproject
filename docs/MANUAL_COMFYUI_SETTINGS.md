# Driving the H3 graph by hand in ComfyUI

Two traps that only bite when you run the workflow manually rather than through
`minimax_story_runner.py`. Both were hit on 2026-08-10.

## Trap 1 — the saved workflow says 1:1 (Square), and always has

`ResolutionSelector` is stored as `1:1 (Square)` in **both** graph files:

- `outputs/equal_shares/runtime/proven_manual_minimax_h3_api.json` — node 115
- `outputs/equal_shares/runtime/proven_manual_minimax_h3_workflow.json`

The automation never produced square video because the runner overwrites that
field at submit time from `story_config.json`:

```python
selector["aspect_ratio"] = config.get("aspect_ratio", "16:9 (Widescreen)")
selector["megapixels"]   = float(config.get("megapixels", 0.3))
selector["multiple"]     = int(config.get("resolution_multiple", 32))
```

So **the file on disk has never matched what actually rendered.** Load it in the
GUI and you inherit a setting every automated run discarded.

Set it by hand every time:

| field | value |
|---|---|
| aspect_ratio | `16:9 (Widescreen)` |
| multiple | `32` |
| megapixels | see below |

`1:1` cannot give you 736×416. 736×416 is 1.769 — essentially 16:9. At 1:1 and
0.3 MP the selector returns roughly 544×544.

Worth fixing the two graph files so they say `16:9 (Widescreen)`, since the
runner overrides the field anyway and the stored value serves no purpose except
to mislead whoever opens it next.

## Trap 2 — resolution is megapixels, not width and height

`{{WIDTH}}` and `{{HEIGHT}}` are only used when no `ResolutionSelector` exists in
the graph. This graph has one, so those tokens are dead. Editing width and height
changes nothing.

| megapixels | output at 16:9, multiple 32 | vs baseline |
|---|---|---|
| 0.30 | 736×416 | everything rendered so far |
| 0.59 | 1024×576 | 1.9× pixels |
| 1.43 | 1600×896 | 4.6× |
| 1.54 | 1664×928 | 5.0×, about the native size of the reference frames |

## Use the real reference frames, not the thumbnails

The anchors are **1672×941**:

```
outputs\equal_shares\frames\scene_###\boundary_##.png
```

The 520×293 files in `EQUAL_SHARES_GENERATION_LIST\thumbs\` on the Desktop are
downscaled copies made for browsing the HTML list. They are 3.2× smaller on each
edge. Feeding one to the model discards detail for nothing, and it will
invalidate any test of whether resolution drives the face failures.

`index.html` prints the full original path under every image.

## Frame count is yours to compute when running manually

The runner normally derives it. By hand, round the frame count **up to the next
value congruent to 5 modulo 17**:

```python
base = round(duration * 24)
frames = base + (5 - (base % 17)) % 17
```

8 s → 192 frames (already 5 mod 17). 12 s → 288 → 294. 15 s → 360 → 362.

Recompute it if you change duration. It does not change with resolution.

## Everything else to hold constant

Model `minimax_h3_fl2va_pruned_int8_convrot.safetensors`, text encoder
`qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`, video VAE
`minimax_h3_video_vae_fp16.safetensors`, audio VAE
`minimax_h3_audio_vae_fp32.safetensors`, `res_multistep` / `simple`, denoise 1.0,
20 steps, 24 fps, 8-bit, SageAttention on. Never a Turbo model, node, or LoRA.

## And the prompt itself

Use the `optimized_prompt` column from `generation_list.csv` — the manual-paste
variant, which carries the dialogue once. The `optimized_prompt_for_runner`
column omits the spoken line because the runner appends its own AUDIO LOCK; that
variant is wrong for manual use. See `PROMPT_REPETITION_RULE.md`.
