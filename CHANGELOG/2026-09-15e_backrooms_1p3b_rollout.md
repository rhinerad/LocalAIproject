# Backrooms 1.3B generative upscale repair and monitored rollout

Operator explicitly authorizes C016 Phase-4-only test followed automatically
by all 24 clips. Prior Phase 3 C016 and interpolation-only output are preserved.

- Added `backrooms_watch.py`: owned backend lifecycle, exclusive runner lock,
  existing queue-owner coordination, two-second thermal/VRAM/RAM/port telemetry,
  emergency interruption and termination, and measured RAM recovery on stop.
- Replaced Phase 4 14B GGUF with Wan 2.1 T2V 1.3B FP16. Installed checkpoint
  from Comfy-Org; SHA256 be531024cd9018cb5b48c40cfbb6a6191645b1c792eb8bf4f8c1c6e10f924dc5.
- Tile weights inspected: attention width 1536, patch input 32 channels.
  Added the author's InstructPixToPixConditioning path for the extra 16 channels.
  Reference: https://huggingface.co/spacepxl/Wan2.1-control-loras/blob/main/1.3b/tile/Wan2.1_1.3b_tile_control_lora.json
- Removed spatial-upscale output/fallback. Video loader resizes only sampler
  inputs; output flows KSampler -> tiled VAE decode -> encoded MP4 with metadata.
- Durable stage checkpoints and MP4 embedded-graph verification are being added.
  Live validation pending; no claim of successful generative output yet.

Added atomic per-clip/stage checkpoints, explicit full-decode and embedded graph
validation, preserved canonical-file replacements, and rollout launcher. Four
recovery tests pass, including a simulated Phase 4 failure that never runs
Phases 1-3 and rejects the historical Lanczos MP4. C016 source SHA256 before
live test: d3e06cd1c865929a0f41641f5e83127105ae31449a0bbcb9e70d12363635508f.

Full production backend launches now load only GGUF, VideoHelperSuite, Impact
Pack and Impact Subpack. Added explicit per-process runner logs for Windows
hidden-process logging. C016 live prompt: 5b493486-4ce5-4129-9c4c-14151026ff0d.

The first repaired attempt was proactively interrupted during CPU T5 encoding:
backend RAM approached 10 GiB, GPU remained idle, and system available RAM fell
to about 3 GiB. Stopped only recorded owned process IDs after verifying command
lines. Phase 4 CLIP now uses default GPU placement; Phase 3 CPU CLIP is unchanged.
Enabled cache-none and the four-extension allowlist for the next test. No source
or output was removed, and no hardware cap was relaxed.

GPU text encoding reached KSampler in 64 seconds with no model-shape failure.
Prompt e0c69a7a-1e72-4fdd-8ea4-73dfed2da2a0 failed because backend cp1252 stdout
could not encode a Unicode log message. Added explicit PYTHONUTF8=1 and
PYTHONIOENCODING=utf-8 to backend environment; retries preserve the source.

## Verified live result and production transition

C016 prompt bc94844e-030c-44b8-8414-ace70097dc44 completed all four KSampler
steps and wrote photoreal_video_C016_00002.mp4 (747041 bytes). Its embedded
graph exactly matches the submitted 1.3B/tile/IP2P/KSampler graph after removing
runtime-only metadata. FFmpeg decoded every frame: 1280x720, 17 frames, 8 fps,
2.125 seconds. Canonical photoreal_video_C016.mp4 was written and SHA256 is
c9a942ffa01b2817a0ab55790b56c4420b0c5d61f509a8d4aa64bce01db6a5e5.
The original Phase 3 source hash is unchanged. Historical Lanczos output remains
preserved and is rejected by the new gate.

Successful prompt sampled maxima: 65 C, 12742 MiB VRAM; available system RAM
stayed >=1.922 GiB. Backend stop reclaimed a further 2.483 GiB available RAM
after model cleanup; port 8188 closed and VRAM returned to 112 MiB.

At 2026-09-15 02:36:57 Eastern, the launcher automatically transitioned to all
24 clips without --limit. Production runner PID 55200 uses --execute only,
skipped the verified C016 checkpoint and started C017. Local watcher remains
active. A separate read-only ten-minute scheduled status check was approved;
recurring autonomous code-edit/restart automation was rejected by auto-review.

Safety caps: 82 C, conservative decimal 15.5 GB VRAM (14781 MiB), 70 C start /
60 C hot-start recovery / 58 C between jobs per existing thermal_guard.
