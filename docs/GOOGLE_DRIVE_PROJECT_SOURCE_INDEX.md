# Google Drive Project Source Index

Last inventoried: 2026-08-24 (America/New_York).

This is a source map, not a replacement for the project documentation that is
already checked into this handoff.  It records the project-scoped Google Drive
documents discovered through the connected Drive and the date rule used when
their guidance overlaps.

## Authority and date rule

1. Safety constraints in `CLAUDE.md`, the live handoff documentation, and
   explicit operator directions always win.
2. For the local agent, the newest numbered `local_agent/UPGRADE/` design
   document wins over an older document with the same scope.
3. The 2026-08-23 **Project Backup** documents are useful continuity summaries.
   They do not silently override a later, more specific implementation design.
4. Earlier duplicates are retained as history.  They are not deleted or treated
   as an alternative current specification.

## Current local-agent specifications (authoritative by recency/scope)

| Drive source | Created (UTC) | Local repository counterpart | Status |
| --- | --- | --- | --- |
| [15_vram_arbitration.md](https://docs.google.com/document/d/1PJOklNvegWbcGrHplksk0_5C6YbnpYcg41hu_tJM8UA/edit?usp=drivesdk) | 2026-08-23 22:39 | `local_agent/UPGRADE/15_vram_arbitration.md` | Latest VRAM rule: render wins; media may reclaim idle chat VRAM; release vision after the batch. |
| [14_queue_dropdown_ui.md](https://docs.google.com/document/d/1xlLVITELTzCzBEXzmC7Wyyo686AJYQ8KQEaG3dmRBuw/edit?usp=drivesdk) | 2026-08-23 22:27 | `local_agent/UPGRADE/14_queue_dropdown_ui.md` | Queue visibility, waiting reason, and per-item cancellation design. |
| [12_resource_and_safety_hardening.md](https://docs.google.com/document/d/1sgMlp75p1Y6OysP3laKDXaX5OexP1HS5O1uLAItEhGU/edit?usp=drivesdk) | 2026-08-23 19:09 | `local_agent/UPGRADE/12_resource_and_safety_hardening.md` | Resource and safety limits. |
| [02_retrieval_over_tree.md](https://docs.google.com/document/d/1WWoXl0MZkLfi4w2lJ3yPzF-yZBd-tlwbF73R9YWlD78/edit?usp=drivesdk) | 2026-08-23 18:46 | `local_agent/UPGRADE/02_context_and_retrieval.md` | Latest retrieved copy retained; an earlier duplicate exists. |
| [08_gui_ctx_and_gpu_yield.md](https://docs.google.com/document/d/11RZfliueqzAYINizidMQBdY2coDZz9A8MIuR8Rvc1_o/edit?usp=drivesdk) | 2026-08-23 18:46 | `local_agent/UPGRADE/08_gui_ctx_and_gpu_yield.md` | Adaptive context ceiling and GPU-yield behavior. |
| [09_media_gpu_queue.md](https://docs.google.com/document/d/1Z3Wdu3Xcj1AAUdEjSQPepQsy7WKvZKbJ5GoC59KmzQU/edit?usp=drivesdk) | 2026-08-23 02:07 | `local_agent/UPGRADE/09_media_gpu_queue.md` | Media job queue and watcher design. |
| [01_native_tool_calling.md](https://docs.google.com/document/d/1rPxgZWj6VXwxiVM_4DrtH2o6cO5Dmdy6PWj4q0SU1AU/edit?usp=drivesdk) | 2026-08-19 21:11 | `local_agent/UPGRADE/01_native_tool_calling.md` | Native Ollama tool calls and fallback policy. |
| [06b_phone_app.md](https://docs.google.com/document/d/1d_Vtk18q6FM3Bygsvm56xE5_KtmG01B3yyy2NSUb--E/edit?usp=drivesdk) | 2026-08-20 04:26 | `local_agent/UPGRADE/06b_phone_app.md` | Most recent of three Drive copies; phone/remote app plan. |
| [07_batch_renderer.md](https://docs.google.com/document/d/1MG4WgyjdvkVIxCe-rk2pkkRTbL37txTs2eMWyn2qARw/edit?usp=drivesdk) | 2026-08-20 04:30 | `local_agent/UPGRADE/07_batch_renderer.md` | Batch rendering plan; remains subject to the active no-render gate. |
| [00_INDEX.md](https://docs.google.com/document/d/1cAljSCMmt5keoS_Afc6wCKIpn6p6tar4jJ2jeA5yCs8/edit?usp=drivesdk) | 2026-08-20 04:26 | `local_agent/UPGRADE/00_INDEX.md` | Most recent local-agent upgrade index. |

Additional local counterparts are present for `03_memory_and_polish`,
`04_sensory_scaffolding`, `05_models_after_internet`, `06_remote_access`,
`06a_usb_direct`, `10_dynamic_model_fallback`, `11_android_native_app`,
`11_android_sideband_agent`, and `13_image_storyboard_generator`.  They remain
part of the local-agent design set even where a Drive title was not returned by
the scoped title searches.

## Project continuity sources (useful context; not newer than the specifications above)

| Drive source | Created (UTC) | What it covers |
| --- | --- | --- |
| [00 - Project Backup Index](https://docs.google.com/document/d/1F9l_S-QsAsCNzT3LLlPThc-WOfQ7juY1Wvjde2c9JxQ/edit?usp=drivesdk) | 2026-08-23 03:05 | Index of the ChatGPT project-continuity backup. |
| [01 - Creative Story and Video Projects](https://docs.google.com/document/d/1X7VxOVDvaUxSUpIfJXnlD7L4mJk1Nvbu6ssN3OmHNVc/edit?usp=drivesdk) | 2026-08-23 03:05 | Equal Shares and other creative-project continuity. |
| [02 - AI Video and ComfyUI Workflow](https://docs.google.com/document/d/1o_59BaCrAkoYN5Uvvtwpm5hFAex8CQ905KSwBKOCEYU/edit?usp=drivesdk) | 2026-08-23 03:06 | Audio-first production, character/voice continuity, QC, and final-video rules. |
| [03 - RTX 5080 ComfyUI and SageAttention Optimization](https://docs.google.com/document/d/1NXMewqCwYG2K8RiDYrXHcnuj210DCozxmccS5aEUjqY/edit?usp=drivesdk) | 2026-08-23 03:06 | Workstation configuration, observed optimization results, rollback and validation context. |
| [07 - Local AI Coding Assistant and Workstation Setup](https://docs.google.com/document/d/1sI5eqQLnmu_MkVk20XkgO_XZoUcuD6jM5_DPurF_VF0/edit?usp=drivesdk) | 2026-08-23 03:06 | Broader workstation and isolation strategy. |
| [09 - Local AI Agent Architecture and Memory](https://docs.google.com/document/d/1zRmAdEo-GGS2EaIAPvyN4OgRI5btZ-ZWUp4VbTKDhhA/edit?usp=drivesdk) | 2026-08-23 17:04 | Earlier high-level local-agent architecture and memory goals. |

## Equal Shares and H3 source material

- [EQUAL SHARES story — Contextual Dialogue Script, Draft 1](https://docs.google.com/document/d/1AI36DMDjlumWxdE4xh5nTvVWfGmpBWaLNemhKSliblM/edit?usp=drivesdk) — 2026-08-08.
- [HANDOFF.md](https://drive.google.com/file/d/1FiqMWbinhtejgwVr1qqWbGwbmb7PDKp_/view?usp=drivesdk) — 2026-08-10.
- [TWO_STAGE_AUDIO_FIRST_PIPELINE.md](https://docs.google.com/document/d/1NQrCZr0Bs6eBDl71tmNigQDGtJ12NG8L2oplN29dhQ4/edit?usp=drivesdk) — 2026-08-13.
- [CHATGPT_HANDOFF.md](https://docs.google.com/document/d/1VAGL3Bu7hjC7ajD9D_r7fS9Utw5u8mAUmQ0OKXOGvvU/edit?usp=drivesdk) — 2026-08-13.
- [START_LOCAL_AGENT.md](https://docs.google.com/document/d/1LtF9BY1euECF668ZCWbV6XMNuYPa4dSxDzWF5WbEjSI/edit?usp=drivesdk) and [FINISH_LOCAL_AGENT.md](https://docs.google.com/document/d/12eAsJHqHeSbRxBQCtvokaRW5iOwxnGFunp6x1A0mwmE/edit?usp=drivesdk) — 2026-08-16 and 2026-08-18.
- [MINIMAX_PROMPT_GUIDE_ref.md](https://docs.google.com/document/d/1-luspy--e54itRN-54FcS3cQjIsoe3DXOyDlVHTeW7o/edit?usp=drivesdk) — 2026-08-16.
- [START_VOICE_AUDITIONS.md](https://docs.google.com/document/d/1RMkgwl1jhVBFf-C7Q8mcN9Ncn5KsiIVLxPfc4BTczNI/edit?usp=drivesdk) — 2026-08-18.

The checked-in primary H3 sources remain `CLAUDE.md`,
`docs/OMNI_REFERENCE_VOICE_LOCK_PIPELINE.md`, `docs/H3_PROMPT_RULES.md`, and
the newest entry in `docs/WORKFLOW_NOTES.md`.

## Known historical duplicates

- `06b_phone_app.md`: Drive copies from 2026-08-20 04:03, 04:25, and 04:26;
  the 04:26 copy is the current source above.
- `00_INDEX.md`: Drive copies from 2026-08-19 and 2026-08-20; the 04:26
  2026-08-20 copy is current.
- `02_retrieval_over_tree.md`: two copies within seconds; the 18:46:34 copy is
  current.
- `CLAUDE_CODE_OPENING_ASSEMBLY_PROMPT.md`: two 2026-08-12 copies; historical
  launch prompts only, not a substitute for the current handoff instructions.

## Deliberate exclusions

Drive searches can return unrelated personal files.  They were not copied into
this project source index merely because they share a keyword.  This index is
limited to Equal Shares, ComfyUI/H3, local-agent, GPU/media, and phone/Sideband
material.
