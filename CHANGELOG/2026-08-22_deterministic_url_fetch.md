# Deterministic URL fetching — 2026-08-22

## Problem

The chat incorrectly told the operator it could not fetch
`https://docs.comfy.org/tutorials/video/minimax/minimax-h3`, even though
`fetch_url` and `web_search` were already registered tools. The model ignored
the optional tool instruction and answered from an outdated assumption.

## Change

- Public `http://` and `https://` links in the newest user message are fetched
  before the first model turn, rather than relying on the model to decide to call
  the URL tool.
- Each fetched page emits its normal `fetch_url` action/result card in the GUI.
- The returned page text is supplied as evidence to the model for its answer.
- A request about persistent memory now deterministically checks saved memory as
  well; the trigger accepts the common spelling `memery`.
- The general prompt now explains that supplied links must be read before an
  answer, and that a page is never remembered unless the operator explicitly
  asks to store a specific fact.
- Removed the contradictory README claim that the app has “No internet”; it has
  no cloud-AI dependency, but can use the workstation connection for requested
  web retrieval without downloading anything.

## Live verification

The exact operator question containing the ComfyUI MiniMax H3 URL emitted:

1. `fetch_url` with the supplied link, returning the official page headed
   “MiniMax H3 in ComfyUI: T2V, I2V, and R2V Video Workflows”.
2. `list_memory`, returning the actual five saved operator facts.
3. A final answer correctly stating that the page is accessible but is not in
   persistent memory.

`test_general_assistant.py`, native tool calling, router switching, media
analysis, and `validate_h3_prompt.py` all passed; prompt validation remains
124/124. No model or dependency was downloaded, and no render was started.
