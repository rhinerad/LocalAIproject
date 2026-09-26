# 2026-09-06j — Flux/photos CAP_IMAGE + timeshare HTTP /free fallback

Date: 2026-09-06. Host: DuranGamingPC.
Id from python scripts/next_changelog_id.py --date 2026-09-06: **2026-09-06j**
(note: operator expected i; i was already claimed under CHANGELOG/.id_claims/).

## Symptom

1. Operator prompt Generate these photos using flux classified
   image_generation_intent=False then capability tool/logic. Chat
   5c5b5b96f0e44966 got full CPU catalog and invented a nonexistent lux tool.
2. _clear_vram_for_timeshare() called MCP clear_vram with spawn=False.
   When MCP was never started, timeshare failed with MCP client is not started
   and stayed on CPU 8B.

## Root cause (verified)

1. _IMAGE_GEN_SIGNAL matched images? but not photos?, and had no
   START/END FRAME or flux-model intent alternations — so photo+flux briefs
   missed CAP_IMAGE and length-escalated to CAP_LOGIC.
2. Timeshare VRAM clear had no HTTP /free fallback when the MCP client was
   not started.
3. Tool text did not tell the model that "using flux" means
   model_profile=realpro_flux on plan/render_story_image (not a tool named flux).

## Fix

- Expand _IMAGE_GEN_SIGNAL: photos?/stills? in generate clause;
  (?:start|end)\s+frame; (?:using|with|via)\s+flux\b and
  \bflux\b.{0,40}\b(?:model|checkpoint|unet|photos?|images?|stills?).
- _clear_vram_for_timeshare: keep MCP clear_vram primary; on
  MCP client is not started, POST http://127.0.0.1:8188/free with
  {"unload_models": true, "free_memory": true} then same used-MiB cap.
- TOOL descriptions + schema for plan_story_image / 
ender_story_image:
  Flux ask → model_profile="realpro_flux"; never call a tool named lux.

## Files

- local_agent/router.py
- local_agent/tools.py
- local_agent/test_capability_routing.py
- local_agent/test_router_comfy_timeshare.py
- local_agent/server.py — APP_REVISION=2026-09-06-flux-photo-intent-r89
- local_agent/START_LOCAL_AGENT_GUI.ps1 — matching ExpectedAgentRevision

## Tests

python -m unittest test_capability_routing.ClassifyCapabilityTests test_router_comfy_timeshare.ComfyTimeshareTests -v
→ **67/67 OK** (new photos/flux/START-END FRAME cases + MCP-not-started → HTTP /free).

## Constraints

No Equal Shares work; Rockernow not killed; no Admin GUI; no reboot.


## Live evidence (DuranGamingPC)

- classify: Generate these photos using flux -> intent True, capability image
- /api/status app_revision=2026-09-06-flux-photo-intent-r89 after START_LOCAL_AGENT_GUI.ps1
- chat 5c5b5b96f0e44966 regenerate after truncate to original brief: capability=image; gpu image schema note (plan/render/status); 14x plan_story_image model_profile=realpro_flux; no tool flux; no comfy_generate; CPU 8B because 8188 listening (Rockernow kept)
- SSE: local_agent/runtime/regen_5c5b_image_sse.txt
