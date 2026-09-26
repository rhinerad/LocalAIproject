# Design note — distributed / offload compute assessment

_Authored 2026-08-24. Assessment of moving the agent LLM (and Whisper) off the RTX 5080
rig onto secondary machines so the 5080 stays dedicated to ComfyUI/diffusion. Verdict:
worth doing for text; vision is the catch. No prompt written yet — operator paused it._

## Verdict: yes, for the text/agent LLM

- It turns VRAM contention from a software-arbitration problem into an **architectural
  non-issue** for text: if the chat/reasoning LLM lives on the 64 GB box, it never
  touches the 5080 — ComfyUI keeps all 16 GB at full speed.
- **The router already models this.** `router.py` addresses two Ollama endpoints —
  `EQUAL_SHARES_GPU_HOST` (default `127.0.0.1:11434`) and `EQUAL_SHARES_CPU_HOST`
  (`…:11435`). Pointing the CPU tier at `http://<64GB-box-IP>:11434` is mostly config +
  health-check + graceful fallback, not a rewrite.
- Whisper offload to a lighter box is a modest bonus (already CPU + small).

## The catch the article glossed over

The heaviest *secondary* workload is **vision** (Qwen2.5-VL on images/video), which wants
a GPU. On a CPU-only 64 GB box it is painfully slow; the Intel MacBook can't run it well
either. So unless the second box has its own GPU, **vision stays on the 5080** and the
VRAM-arbitration work (UPGRADE 09/15) is still needed for vision. Offload solves the
*chat* contention completely and the *vision* contention only partly.

## Do / don't

- **Do:** discrete dedicated services per box (Ollama on the 64 GB box for chat; optional
  Whisper server elsewhere).
- **Don't:** llama.cpp RPC / Petals model-splitting across machines — Gigabit latency
  bottlenecks token generation; the source itself admits this.
- **Security:** `OLLAMA_HOST=0.0.0.0` exposes an unauthenticated model server to the LAN.
  It is the model backend, not the tool-executing agent (which stays `127.0.0.1`), so it
  is lower-risk on a trusted home LAN — but bind to the LAN interface + firewall to the
  subnet, not wide open.

## Trade-off to accept

CPU inference on the 64 GB box is slower (~4–12 tok/s depending on model/quant) than the
5080, but diffusion renders run uninterrupted at full speed. The 64 GB RAM does let you
run larger (30B–70B) quantized reasoning models than the 16 GB card could.

## If pursued

A prompt would: (1) integrate the remote endpoint into the router's existing tier system
with a health-check + graceful fallback when the box is offline; (2) produce a setup
runbook/script for the 64 GB box (install Ollama, LAN-bind + firewall, pull models);
(3) optionally offload Whisper; (4) keep vision local (with arbitration) unless the
second box has a GPU. Open question that gates the design: does the 64 GB box have a GPU?
