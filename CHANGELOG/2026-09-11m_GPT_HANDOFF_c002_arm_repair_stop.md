# GPT HANDOFF — C002 arm repair stop (2026-09-11)

## Operator decision
**STOP C002 repair. Leave production paused.** No v5a3, no v5b, no donor path for now. Stills-only; no video.

## Scope / IDs
- Task: `f8f7f70e364d40c0`
- Revision: `72a7c2e51de194b3da9a717c4d02f288a634d0075f9d8a240eafce3f7496194a`
- Repo: `COMFYUI_STORY_HANDOFF_2026-08-09` on DuranGamingPC
- Supervisor must be: `python work/run_prompt_pack_production.py --cid f8f7f70e364d40c0` (never `-m`)
- GPU ceiling 82°C; never delete attempt evidence

## Accepted anchor (unchanged)
- **C001_last** attempt `6e12ff2ab0b84085b765b7dd07a6bd4c`
- SHA-256 `1302d430636908f50d6d3c2815559a7161300d9d2a5ab96320dd80c95260b4b6`

## Goal that failed
C002_start must match C001_last actor/room/clothes/framing; **only** lower the raised left arm. No camera gear.

## What we did (repair ladder)

| Policy | Attempt | Still SHA-256 (prefix) | Result |
|--------|---------|------------------------|--------|
| v1 ipadapter arm-down | `2c0ad89d…` | `f11ab6ba…` | Visual reject: teal/blue glow |
| v2 OpenPose grow2 | `ce34caa7…` | `4f733d45…` | Teal glow again |
| v3 union mask | `e6d13d26…` | `f0ddefb4…` | Dark-green blob / bad hand |
| v4a erase-only | `f5a64310…` | `407cd675…` | Curtain rectangle glitch |
| v4b hang on v4a | `8bb167e1…` | `8f50fe5c…` | Grey-green oval |
| v5a bgnoise→SD (VAEEncodeForInpaint) | `372f98ca…` | `2b8136b5…` | Flat light-blue polygon; VLM false pass |
| v5a2 bgnoise + **VAEEncode+SetLatentNoiseMask** | `1fd665a4…` | `956bace5…` | Bluish-grey translucent smear; encode fix confirmed; still unusable |

All failed attempts have evidence on disk under `…/stills/pack_…_c002_start/<attempt>/`. Operator rejects written for v1, v5a, v5a2.

## Root-cause findings
1. **Teal/blue blobs (v1–v5a):** `VAEEncodeForInpaint` zeros the masked hole in latent → fill from empty latent. Prefill on the PNG never reached the sampler.
2. **v5a2 encode fix worked** (graph: node4=`VAEEncode`, node23=`SetLatentNoiseMask`, KSampler latent=`["23",0]`), but **SDXL still cannot cleanly fill this large raised-arm hole** — leaves a bluish-grey smear.
3. Classical OpenCV erase (Telea/NS/hpull/seamless/strip) also failed visually (streak/blur). No LaMa custom node in Rockernow/Comfy installs.
4. **Do not trust VLM alone** on this edit — it passed v5a/v5a2 while humans saw obvious blobs.
5. **Do not run v5b** hanging-arm on a bad erase plate.

## Code landed (keep)
- `work/image_render.py`: `use_latent_noise_mask` / `--use-latent-noise-mask` → VAEEncode+SetLatentNoiseMask
- `work/run_prompt_pack_production.py`: `write_bgnoise_prefill_plate`, C002 ladder v1…v5a2→v5b
- Tests: `work.test_still_retry_not_stop` + `work.test_image_render` (55 OK at last run)
- Changelogs: `2026-09-11d` … `2026-09-11m` under `CHANGELOG/`
- Debug stills: `work/_debug_c002_inspect/`

## Production state (as of stop)
- No live `run_prompt_pack_production` supervisor
- Operator: **paused / stop C002 repair**
- MERGED pack production watch remains paused
- Local agent health watch still armed (~every 5m); agent r98 on :8760 typically healthy
- Comfy :8188 often down when idle (owned backend starts per render)

## If resumed later (not now)
Ranked leftovers: (1) operator Photoshop/donor erase of raised arm on C001_last, hash-pin; (2) much smaller hand-only mask + higher denoise latent-mask; (3) install LaMa / better hole-fill; (4) then v5b hang only on a *visually* clean erase plate. Bound supervisor to C002_start only — success does not auto-stop before C002_last.
