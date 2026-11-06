# Sanitized portfolio demo runbook

This runbook prepares a future screen-recording demonstration without using any
private media, prompts, identities, project history, paths, network details, or
model files. It does not authorize a recording, download, model load, or render.

## Before recording

- [ ] Create a separate demo-only working directory with a generic name.
- [ ] Use only a benign asset with a documented reusable license, such as a
  public-domain train clip. Save source URL, license, and attribution in a
  separate release-evidence record.
- [ ] Start a new demo-only chat with synthetic requests and synthetic filenames.
- [ ] Disable or hide persistent-memory panels, existing chat history, media
  queues, downloaded-model lists, and project-specific tools.
- [ ] Confirm the browser UI shows no usernames, absolute paths, addresses,
  paired identities, credentials, private prompts, or uploads.
- [ ] Confirm ComfyUI is not rendering. Demonstrate guarded preflight only—do
  not create an image or video merely for the recording.

## Suggested three-minute flow

1. Show a new local chat and explain that the desktop HTTP service is local-only.
2. Ask one synthetic question that needs a read-only tool; show a structured
   action card and a sourced response.
3. Attach the benign media asset and show that media analysis is queued behind
   render ownership rather than competing for the GPU.
4. Demonstrate a synthetic preflight/refusal: an invalid or missing job folder
   must be refused with a clear reason, not fabricated or silently rendered.
5. Show the architecture diagram and the permission decision diagram.

## Frame-by-frame release check

- [ ] Inspect the recording at full resolution before export.
- [ ] Blur/redact any path, username, local host data, identity, key, source
  media title, project name, chat transcript, or model-file location.
- [ ] Verify every shown claim appears in `docs/portfolio/validation_matrix.md`
  or is explicitly labeled planned/experimental.
- [ ] Keep the original unredacted capture private; publish only the reviewed
  redacted export.
- [ ] Store public-asset attribution separately from the private project tree.

## Claims allowed in the narration

- “Implemented and locally tested” for structured tool calls, guarded tools,
  localhost-only HTTP, retrieval safeguards, and current source-test evidence.
- “Experimental” for mesh reliability and unmeasured radio delivery.
- “In progress” for custom Android packaging and direct mobile media features.

Never present an architecture diagram, static test, or UI mockup as a completed
performance or end-to-end device result.
