# Google Drive source manifest — local-agent architecture

Checked 2026-08-24. These Drive documents are the preserved Claude-authored
source prompts for the local checked-in design copies below. Read the local copy
for work in this repository; use the Drive link for provenance or revision
comparison. A Drive document does not override `CLAUDE.md` render safeguards.

| Local working copy | Google Drive source | Purpose |
|---|---|---|
| `09_media_gpu_queue.md` | [Drive document](https://docs.google.com/document/d/1Z3Wdu3Xcj1AAUdEjSQPepQsy7WKvZKbJ5GoC59KmzQU/edit?usp=drivesdk) | Tiered GPU-only sensory queue and watcher. |
| `12_resource_and_safety_hardening.md` | [Drive document](https://docs.google.com/document/d/1sgMlp75p1Y6OysP3laKDXaX5OexP1HS5O1uLAItEhGU/edit?usp=drivesdk) | Keep-alive, pre-emption, priority and safety hardening. |
| `15_vram_arbitration.md` | [Drive document](https://docs.google.com/document/d/1PJOklNvegWbcGrHplksk0_5C6YbnpYcg41hu_tJM8UA/edit?usp=drivesdk) | Required chat-to-media VRAM reclaim ladder. |

## Persistent invariant

A real render always wins: a live render owner or ComfyUI on port 8188 means
media waits. When no render owns the GPU, queued media must not remain blocked
solely by an idle chat model: coexist if a vision tier fits, otherwise downgrade
14B chat to 8B, then evict chat if necessary, drain the batch, and release
vision. Never interrupt a streaming chat, never evict a render, and never
delete queued media or its source.
