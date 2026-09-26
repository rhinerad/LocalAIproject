# 2026-09-05ay — Inline generated-media v2 shipped

## Scope

🔵 lane, Task #51. Reviews Grok's own report (`2026-09-05aw`, already in
TODO.md). No new work.

## What shipped

`comfy_job_status(prompt_id)` polls ComfyUI's `/history` directly over
HTTP (not MCP — an in-flight generate holds the MCP lock, correctly
avoided), bounded backoff (0.5s doubling to a 5s cap, 90s default
deadline, 300s hard cap), and correctly gives one immediate snapshot with
no sleep at all when `timeout_s=0`. Completed jobs resolve to a real
`shared_output` locator via the same hash-verified pattern as v1; a
still-running job returns an honest pending card (no filename, no image
fetch attempted) rather than a broken preview. Video gets a real
`<video controls>` card with duration and an open-folder action, reusing
the same reveal/root-allowlist machinery as images — story roots stay
image-only, and `uploads/`/`chats/`/`equal_shares/`/Shared input all stay
forbidden. `APP_REVISION` correctly bumped to `r78` (real behavior
change), launcher's `$ExpectedAgentRevision` matched.

## Self-caught bug, worth noting

The report is explicit that an initial run hit a real bug — `timeout_s=0`
was being treated as `90s` because of a falsy-zero check (`0 or 90`
evaluates to `90`) — and it was caught and fixed before being reported as
done, not glossed over. Final run: 66/66 tests in 0.25s. This is the
right instinct: report the bug that was actually found and fixed, not
just the clean final state.

## Live verification

Port 8188 was closed during this pass, so no live `/history` poll ran.
Instead, the real 2026-09-04j history JSON was parsed directly and
confirmed to resolve to the actual on-disk file
(`ComfyUI_00214_.png`, 317295 bytes, byte-identical to the original) with
a 200 image/png response — real data, just not a freshly-triggered live
generate.

## Status

Task #51 fully closed. Inline media display (story stills + Comfy-generated
images/video) is now complete end to end: v1 (stills) + v2
(comfy_generate polling + video) both shipped, tested, and hash-verified.
