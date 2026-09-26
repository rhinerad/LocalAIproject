# SDXL LoRA Training — A Primer

This is background reading, not a build plan. Your project already has a working
Kohya environment (`A:\Users\rhine\kohya_ss\.venv-local-agent`, Python 3.11.15,
Torch 2.7.0+cu128, CUDA 12.8 — verified 2026-09-01) and a dataset/caption
readiness checker already built. What's still an open decision, per `TODO.md`,
is the first real training objective: consented identity or style, dataset
location, trigger token, and evaluation prompts. This doc is meant to help you
make that decision with real understanding, not guesswork.

## What a LoRA actually is

A LoRA (Low-Rank Adaptation) doesn't retrain the base SDXL model. It trains a
small set of additional weight matrices that get added on top of the frozen
base model at inference time. That's why LoRA files are tens of megabytes
instead of gigabytes, and why you can stack or swap them without re-downloading
anything.

## Two kinds of LoRA, two different datasets

**Identity LoRA** (a specific person, pet, or object): teaches the model to
reproduce one consistent subject. Needs 10-30 clear photos of that subject —
varied angles, lighting, and expressions, but the subject always clearly
identifiable. Avoid motion blur, extreme crops, or occlusion.

**Style LoRA** (an art style, aesthetic, or consistent "look"): teaches the
model a rendering style independent of subject. Usually wants 15-30+ images to
capture the range of the style across different subjects/compositions.

In both cases: quality and consistency beat quantity. Twenty sharp, well-chosen
images will outperform seventy-five inconsistent ones. Resolution should be at
least 1024x1024 for SDXL — don't upscale low-res source images to hit that
number; you'd just be training on fake detail. Strip watermarks, logos, and
burned-in captions from training images, or the model will learn to reproduce
them.

## Trigger words and captioning

A trigger word is a unique, otherwise-meaningless token (e.g. `sks person`,
`ohwx style`) that becomes the "handle" for invoking your LoRA's concept. It
needs to be:

- Unique/abstract — not a real word the model already has strong associations
  with.
- Present in **every single** caption for the training set — if it's missing
  from even a few images, the model won't reliably bind the concept to the
  word.
- Followed by natural, accurate description of the rest of the image (for an
  identity LoRA, typically including gender/descriptor right after the
  trigger).

Auto-generated captions are a reasonable starting point but need manual review
— they routinely omit the trigger word entirely or fixate on irrelevant
background details instead of the subject.

## Core training parameters (Kohya / sd-scripts, which your environment runs)

- **Learning rate:** `1e-4` (0.0001) is the standard, reliable starting point
  for SDXL LoRA training. This is the single most impactful setting to get
  approximately right before tuning anything else.
- **Network dimension (rank):** controls how much capacity the LoRA has to
  learn. `32` is a reasonable default for a small/medium dataset; `64` for a
  larger, more varied one. Higher rank = larger file, more capacity, more risk
  of overfitting on a small dataset.
- **Network alpha:** a scaling factor, effectively `alpha / dim`. Setting
  alpha equal to dim is a common, safe starting choice. An alpha lower than
  dim reduces the effective learning rate of the LoRA layers.
- **Steps/epochs:** highly dataset-dependent — there's no universal number.
  The practical approach is to save checkpoints periodically and evaluate
  against your held-out evaluation prompts rather than committing to a fixed
  step count up front.

## What "one bounded smoke run" (your TODO's next step) should look like

Given your project's existing safety posture (GPU-gated, thermal-guarded,
nothing runs without explicit approval), a reasonable first real run is:

1. Pick **one** objective — identity or style, not both.
2. 15-20 well-chosen, correctly captioned images with a unique trigger token
   present in every caption.
3. Conservative defaults: `1e-4` learning rate, `dim=32` / `alpha=32`.
4. A small, fixed set of evaluation prompts decided *before* training starts,
   so you're judging the result against a plan rather than post-hoc vibes.
5. One run, reviewed manually — no automated "looks good" acceptance criteria
   for a first LoRA. Your own eyes are the judge here.

## Sources

- [All-in-One Stable Diffusion Guide — LoRA Training](https://github.com/Haoming02/All-in-One-Stable-Diffusion-Guide/blob/main/LoRATraining.md)
- [LoRA Training Guide 2026 — ZSky](https://zsky.ai/blog/lora-training-guide)
- [Train an Image LoRA Locally (2026): Kohya, SDXL & FLUX](https://localaimaster.com/blog/image-lora-training-local-guide)
- [Kohya SS Wiki — LoRA training parameters](https://github.com/bmaltais/kohya_ss/wiki/LoRA-training-parameters)
- [Understanding LoRA Training, Part 1 — Medium](https://medium.com/@dreamsarereal/understanding-lora-training-part-1-learning-rate-schedulers-network-dimension-and-alpha-c88a8658beb7)
- [Stable Diffusion LoRA Training Settings for Kohya SS — Aituts](https://aituts.com/lora-training-settings/)

## Next step, when you're ready

Once you've decided identity-vs-style, the dataset, and a trigger token, that
directly answers TODO.md's open item ("Select one first training objective...
dataset location, unique trigger token/output name, and evaluation prompts").
At that point I can draft the Grok prompt for the actual bounded smoke run —
it still needs your explicit GPU approval per the project's standing rules.
