# Ref2VA voice-lock test — ComfyUI setup

One clip. Regenerate `00B` with `00A`'s video-and-audio as a voice reference, and compare
against the `00B` you already have. If the Narrator sounds like the same man in both, the
idea works.

**Everything needed is already on disk. No downloads.**

---

## The one-line change

Your working graph is **fl2va** — first-and-last frame to video+audio. You are swapping it
for **ref2va** — reference to video+audio — which is the checkpoint that accepts voice and
identity references.

```
   BEFORE (what you use now)          AFTER (this test)
   ────────────────────────           ─────────────────
   minimax_h3_fl2va_...int8    ──▶    minimax_h3_ref2va_pruned_nvfp4
   MiniMaxH3ImageToVideo       ──▶    MiniMaxH3ReferenceToVideo
   first_frame + last_frame    ──▶    same, PLUS reference video / reference audio
```

Everything else — text encoder, both VAEs, sampler, scheduler, steps, resolution, frame
maths, save nodes — stays exactly as it is.

---

## Node graph

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │  LOADERS — one change only                                           │
 │                                                                      │
 │  UNETLoader ......... minimax_h3_ref2va_pruned_nvfp4.safetensors ◀── CHANGE
 │  CLIPLoader ......... qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors   │
 │                       type: minimax                                  │
 │  VAELoader (video) .. minimax_h3_video_vae_fp16.safetensors          │
 │  VAELoader (audio) .. minimax_h3_audio_vae_fp32.safetensors          │
 └──────────────────────────────────────────────────────────────────────┘
            │                    │                │            │
            ▼                    ▼                ▼            ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │  MiniMaxH3ReferenceToVideo          ◀── REPLACES MiniMaxH3ImageToVideo │
 │                                                                      │
 │   prompt        ◀── your 00B prompt text                             │
 │   width/height  ◀── ResolutionSelector  (16:9, 0.3 MP, mult 32)      │
 │   length        ◀── ComfyMathExpression (frame maths, gives 362)     │
 │   clip          ◀── CLIPLoader                                       │
 │   vae           ◀── VAELoader (video)                                │
 │                                                                      │
 │   first_frame   ◀── LoadImage: boundary_00_v2.png                    │
 │   last_frame    ◀── leave DISCONNECTED (00B is single-anchor)        │
 │                                                                      │
 │   ─── the new part ────────────────────────────────────────────      │
 │   reference_video ◀── LoadVideo: 1.mp4     ◀── THE VOICE LOCK        │
 │   reference_audio ◀── (fallback, see below)                          │
 │   reference_image ◀── narrator_master_v1.png  (optional, identity)   │
 └──────────────────────────────────────────────────────────────────────┘
            │  conditioning              │  latent_image
            ▼                            ▼
     BasicGuider ◀── UNETLoader    SamplerCustomAdvanced
            │                            ▲   ▲   ▲
            └────────────────────────────┘   │   │
                RandomNoise ────────────────┘   │
                KSamplerSelect (res_multistep) ─┤
                BasicScheduler (simple, 20, 1.0)┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
        VAEDecode                  VAEDecodeAudio
        (video VAE)                (audio VAE)
              │                           │
              └────────► CreateVideo ◀────┘
                         24 fps, 8-bit
                              │
                         SaveVideo
                    prefix: ref2va_test/00B
```

---

## Build checklist

**1. Duplicate your working graph.** Do not edit the proven one. Save as
`ref2va_voicelock_test`.

**2. UNETLoader → `minimax_h3_ref2va_pruned_nvfp4.safetensors`.**
Leave `weight_dtype` at default.

**3. Delete `MiniMaxH3ImageToVideo`. Add `MiniMaxH3ReferenceToVideo`.**
Reconnect: `clip`, `vae`, `width`, `height`, `length`, `prompt`, and the outputs
`conditioning` → BasicGuider and `latent_image` → SamplerCustomAdvanced.

> The exact input names on this node are the one thing I could not verify. Read the labels
> when you drop it in and map by meaning — image reference, video reference, audio
> reference. If it has no `first_frame`, see "If it has no frame inputs" below.

**4. LoadImage → `first_frame`:**
`outputs/equal_shares/frames/scene_000/boundary_00_v2.png`
Leave `last_frame` disconnected. `00B` is single-anchor in the config.

**5. Add the voice reference. This is the whole point of the test.**

`LoadVideo` → `A:\Users\rhine\ComfyUI-Shared\output\video\1.mp4` → `reference_video`

That is your `00A` keeper: 8 s, the Narrator on camera speaking the opening line, with
audio. Well inside the 2–15 s reference range.

*If the node has no video reference input, or wants audio separately:*
`LoadAudio` → `outputs/equal_shares/voices/narrator/reference_sample.wav` (13.25 s,
already extracted and loudness-normalised) → `reference_audio`.

**6. Optional, but try it — identity reference.**
`LoadImage` → `outputs/equal_shares/references/narrator_master_v1.png` → `reference_image`.
This is the sheet built from approved frames. If Ref2VA locks identity as well as voice,
this is where the face problem gets addressed too.

**7. Settings — unchanged, do not vary them.**

| | |
|---|---|
| ResolutionSelector | **16:9 (Widescreen)**, 0.3 MP, multiple 32 |
| Steps | 20 |
| Sampler / scheduler | `res_multistep` / `simple`, denoise 1.0 |
| Duration | 15.0 s → **362 frames** |
| fps / bit depth | 24 / 8 |

The saved workflow ships with `1:1 (Square)`. **Check it every time.**

**8. Prompt.** Paste `prompts/00B.txt` unchanged, then add one line at the top:

```
Use the reference video only for the Narrator's voice — his timbre, pitch and delivery.
Take nothing else from it: not the framing, not the camera move, not the blocking.
```

Per the guide's own rule: give every reference an explicit job.

**9. SaveVideo prefix → `ref2va_test/00B`.**
Keeps it out of `story/` so nothing touches the archive or the manifest.

**10. Check nothing else owns the GPU** before you queue — `runtime/render_queue_owner.json`
and the tail of `runtime/render_supervisor.log` against the clock.

---

## If it has no frame inputs

Ref2VA may treat images as *references* rather than literal boundary frames. If there is no
`first_frame` socket, feed `boundary_00_v2.png` as a reference image and add to the prompt:

```
Image 1 is the exact opening composition. Begin on it precisely.
```

Then check whether the render actually starts on that frame. **If it does not, that is the
finding** — it means Ref2VA buys you voice at the cost of frame-exact continuity, and the
answer is a hybrid: Ref2VA for dialogue shots, fl2va where continuity matters.

---

## How to judge it

Compare against `A:\Users\rhine\ComfyUI-Shared\output\video\2.mp4`, your existing `00B`.

**The one question:** does the Narrator sound like the same man in the new `00B` as he does
in `1.mp4`? Play `1.mp4` then the new render back to back.

Then, in order:

1. **Voice** — same person? That is pass or fail for this test.
2. **Lip sync** — should be inherent; video and audio are generated together.
3. **Face** — did the identity reference help, if you connected one?
4. **Picture quality** — nvfp4 is more aggressive quantisation than your int8 fl2va. Softer?
5. **Opening frame** — did it start exactly on `boundary_00_v2`?

---

## Report back

- the actual input names on `MiniMaxH3ReferenceToVideo`
- whether video-with-audio worked as a reference, or whether it needed audio alone
- whether frame-exact anchoring survived
- voice verdict, face verdict, quality verdict
- render time versus your usual ~8 minutes

That is enough to decide whether this replaces the fl2va path, supplements it, or gets
dropped.
