# Local agent product goal clarified — 2026-08-22

## Decision

The Equal Shares Local Agent's primary product goal is a functional, local copy
of ChatGPT Desktop. It is not limited to answering questions about Equal Shares.

## Consequences

- The app shell is a general desktop assistant: persistent chat, multimodal
  attachments, native tools, files, web access, memory and polished controls.
- Equal Shares knowledge and guarded project actions are a specialization layer.
- Missing local capabilities are reported honestly rather than simulated.
- Downloads still require explicit approval.
- Evidence protection, GPU/render coordination, CPU limits and thermal safety
  remain non-negotiable.

## Documentation updated

- `local_agent/README.md`
- `local_agent/UPGRADE/00_INDEX.md`

## Verification

The two documents were reread after editing and both state the same product
hierarchy. This is a documentation-only change; runtime behavior was not altered.

## Still unverified

Full ChatGPT Desktop capability parity is a roadmap, not a completed claim.
