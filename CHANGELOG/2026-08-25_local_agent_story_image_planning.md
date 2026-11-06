# 2026-08-25 — Local-agent storyboard image planning

## What changed

- Added `plan_story_image` to the local agent's native tool registry.
- It builds a core RealVisXL text-to-image or reference-image-to-image graph for a
  general story/storyboard request, returning the graph and intended isolated
  output tree to the conversation.
- The tool has no execution path: it does not start ComfyUI, load a model, claim
  the GPU, write a plan file, or create an output image.
- It accepts only the verified current workhorse checkpoint and uses the existing
  graph builder, including its size, denoise, and reference-image validation.
- The agent's general conversation rules now distinguish a prepared image plan
  from a completed image generation.

## Safety

- A future execution action remains separately operator-approved and must use the
  isolated renderer's ownership, port, thermal, and checkpoint checks.
- Equal Shares remains out of scope for all storyboard image work.
- For i2i planning, a reference is reduced to its uploaded filename; no arbitrary
  local path is admitted into the ComfyUI graph.

## Verification

- `python local_agent/test_story_image_plan.py` — 4/4 passed.
- `python local_agent/test_native_tool_calling.py -q` — 19/19 passed.
- `python -m unittest discover -s local_agent -p "test_*.py" -q` — 138/138 passed.
