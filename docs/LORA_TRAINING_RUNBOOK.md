# Character LoRA runbook — MiniMax H3

Written 2026-08-11. Two things in here are verified because I ran them: the dataset
builder, and the dataset it produced for the Narrator. **The training config is a
template I could not execute or validate** — no GPU and no ai-toolkit in this
environment. Check every key against the current ai-toolkit H3 guide before you
trust it, and expect the schema to have moved.

---

## Step 1 — build the dataset (verified, ready to run)

```powershell
$Py    = "A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe"
$Story = "A:\Users\rhine\ComfyUI-Shared\output\story"

& $Py work\build_lora_dataset.py --name narrator --trigger ohwx_narrator `
  --caption "a man in his late fifties, lean face, dark hair combed back, dark 1960s suit, white shirt, narrow black tie, black and white television lighting" `
  --sources "outputs\equal_shares\frames\scene_000\boundary_narrator_close_v3.png" `
            "outputs\equal_shares\frames\scene_000\boundary_00_v2.png" `
            "outputs\equal_shares\frames\scene_000\boundary_04_v2.png" `
            "$Story\00A" "$Story\00B" "$Story\00C"
```

Test run result: **40 crops kept, 26 near-duplicates discarded, face sizes 102–167 px
in source.** Output in `outputs\equal_shares\lora_datasets\narrator\` as `.png` +
`.txt` pairs, with `_contact_sheet.jpg` and `dataset_manifest.json`.

The tool samples videos once per second, finds the largest face, crops head and
shoulders at 3.2× face width, drops anything under `--min-face-px`, removes
near-duplicates, and upscales to 1024×1024.

**The size filter is the important part.** In the wide shots the Narrator's head is
about 22 px. Those frames contain no identity information and would teach the LoRA a
blurred average. They are excluded automatically.

### Then cull, by hand

Open `_contact_sheet.jpg`. Delete any crop that is the wrong person, blurred,
mid-blink, or has a second face intruding at the edge — and delete its matching
`.txt`. **Fifteen clean crops beat forty with five wrong faces.**

### One real weakness in this dataset

All 40 crops come from `00A` and `00B` — 34 and 6 — which are the same setup: same
angle, same lighting, same background, same wardrobe. A LoRA trained on it learns
"this man, shot this way." It will be strong for the opening and weak anywhere else,
and it has no profile or three-quarter views at all.

For the Narrator that may be fine, since he only ever appears in that setup. If you
want it to generalise, add varied angles first — which realistically means generating
a character sheet from `references\narrator_master_v1.png` with your Mickmumpitz
workflow and feeding those in alongside these.

---

## Step 2 — check the base model before you spend a night on this

Your inference checkpoint is `minimax_h3_fl2va_pruned_int8_convrot.safetensors` —
**pruned and int8-quantised**. LoRA training wants the base weights.

So: pull the full-precision H3 weights for the training run, then confirm the
resulting adapter actually loads against your quantised checkpoint at inference.
Rank and target-module names have to line up. Do this check on a 200-step throwaway
run before committing to a real one.

If the adapter will not load against the quantised model, your options are to run
inference on the full model too — much slower, more VRAM — or to abandon the LoRA
and use the post-hoc face swap described at the end.

---

## Step 3 — train (template, verify before use)

Install ai-toolkit per its own instructions, then a config along these lines:

```yaml
job: extension
config:
  name: narrator_h3
  process:
    - type: sd_trainer
      training_folder: A:/Users/rhine/lora_training/output
      device: cuda:0

      network:
        type: lora
        linear: 32          # rank. 16-32 is plenty for one face
        linear_alpha: 32

      save:
        dtype: float16
        save_every: 250
        max_step_saves_to_keep: 6

      datasets:
        - folder_path: A:/Users/rhine/Documents/Codex/2026-08-07/referenced-chatgpt-conversation-this-is-an-2/COMFYUI_STORY_HANDOFF_2026-08-09/outputs/equal_shares/lora_datasets/narrator
          caption_ext: txt
          caption_dropout_rate: 0.05
          shuffle_tokens: false
          cache_latents_to_disk: true
          resolution: [512, 768, 1024]

      train:
        batch_size: 1
        steps: 2000
        gradient_accumulation_steps: 1
        train_unet: true
        train_text_encoder: false
        gradient_checkpointing: true
        noise_scheduler: flowmatch
        optimizer: adamw8bit
        lr: 1e-4
        dtype: bf16

      model:
        name_or_path: <full-precision MiniMax H3 weights>
        is_video: true

      sample:
        sampler: flowmatch
        sample_every: 250
        width: 736
        height: 416
        prompts:
          - "ohwx_narrator, a man in a dark 1960s suit addressing the camera in a sterile waiting room, black and white"
          - "ohwx_narrator standing in a spotlight, three-quarter view, black and white"
        neg: ""
        seed: 42
        walk_seed: false
        guidance_scale: 4
        sample_steps: 20
```

Keys I am least confident about, in order: `model.is_video`, the H3 model loader
name, `noise_scheduler`, and whether target modules need naming explicitly for this
architecture. Those are exactly the ones the guide will specify.

Watch the sample images at each save. When the face locks and before the background
starts baking in, stop — usually somewhere between 1200 and 2000 steps at rank 32 on
a set this size. Overtraining shows up as the model reproducing `00A`'s exact
background whatever you prompt.

---

## Step 4 — use it in ComfyUI

Drop the `.safetensors` into `A:\Users\rhine\ComfyUI-Shared\models\loras\`, add a
LoRA loader between `UNETLoader` and `BasicGuider` in your working graph, and put the
trigger word at the front of the prompt:

```
ohwx_narrator. One continuous unbroken take.

CAMERA
...
```

Start at strength **0.6–0.8**. Too high and it flattens expression and drags the
background of the training set in with it.

### Apply it to nine clips, not all 124

The Narrator appears in `00A`, `00B`, `00C`, `00I`, `00K`, `00L`, `00M`, `00N`, `00O`
— and nowhere else in the film. Every one of the 43 accepted clips was rendered
without a LoRA, so the safe move is to load it only for those nine and leave the rest
of the baseline untouched.

**Record it.** A LoRA is a change to the generation stack, and `generation_audit.json`
exists to prove which stack produced which clip. Note the LoRA name, strength, and
which clips used it.

---

## What this will and will not fix

**Will fix:** the Narrator looking like a different man in `00A` than in `00K`. That
is what a character LoRA is for.

**Will not fix:** the morph in the `boundary_03_v2 → boundary_04_v2` shot. He and the
standing man occupy nearly the same screen position between those two anchors, so the
model grows one into the other. A LoRA changes the face the morph arrives at; it does
not stop the morph. That shot still needs the entry-edge, depth cue and
anti-transformation clause.

**Will not fix:** the wides. At 22 px there is nothing for a LoRA to express.

---

## The cheaper alternative, if the base-model check fails

`insightface\inswapper_128.onnx` and the `reactor` nodes are already installed. A
post-hoc face swap onto already-rendered footage, using a canonical Narrator face,
gives cross-clip consistency with no training and no re-render.

It operates at 128 px, so it is good for his close and medium shots and useless in
the wides — which are the shots where his face is unreadable anyway. For a character
in nine shots this is a genuinely reasonable answer, and it is an afternoon rather
than a night.
