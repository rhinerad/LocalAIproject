# Reference — the official MiniMax H3 documentation, captured locally

Saved 2026-08-16 so the pipeline does not depend on network access or on pages
that may change. **These are the sources. `docs/H3_PROMPT_RULES.md` is what this
project actually does with them.**

| File | Source |
|---|---|
| `COMFYUI_MINIMAX_H3_TUTORIAL.md` | <https://docs.comfy.org/tutorials/video/minimax/minimax-h3> |
| **`MINIMAX_PROMPT_GUIDE_ref.md`** | MiniMax official **R2V** guide — **the one this project follows** |
| `MINIMAX_PROMPT_GUIDE_base.md` | MiniMax official base-mode guide (T2VA/I2VA/FL2VA/L2VA) |

MiniMax also publishes installable H3 skills, not captured here:
<https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills>

## The five things in here that changed this project

1. **`retention_analysis` with `<Audio N>: reference`** (ref guide §4.2) — fixed
   the doubled voice. Nothing had told H3 the master was a reference rather than
   a source to copy.
2. **Dialogue is `<d>[English] …</d>`** (base §4.4) — quotes mean on-screen text.
3. **`[Shot N]` marks a cut, not a beat** (base §4.2) — a continuous take is one
   `[Shot 1]` with no timestamp.
4. **The mouth closes in the clause right after `</d>`** — visible in two of the
   ref guide's three worked examples.
5. **`ref_image_size: max`** keeps a 2048px short edge for stronger identity
   fidelity (tutorial, R2V tips). This project has always run `match`, which
   downscales references at the moment identity is decided. **Untested here.**

## What the docs do NOT explain

Nothing in any of them addresses H3 filling unallotted time with invented speech.
That was found by measurement on this machine and is documented in
`docs/H3_PROMPT_RULES.md` §9: render only as long as the line needs, pad silence
at assembly.
