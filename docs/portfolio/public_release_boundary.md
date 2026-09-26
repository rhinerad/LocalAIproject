# Public-release boundary

This is a release-planning boundary, not permission to publish. A final source,
secret, path, media, and license audit is still required before any push.

## Candidate public modules

| Candidate | Why it may be useful | Required preparation |
|---|---|---|
| Structured tool-call loop | Shows schemas, multi-call control flow, and compatibility fallback | Replace project tool names with synthetic examples and add fixtures |
| Tool validation patterns | Shows whitelist and input-validation boundary | Remove project-specific paths/actions and prove protected-file behavior |
| H3 evaluation harness | Shows reproducible, privacy-safe evaluation design | Publish only synthetic prompts and synthetic expected outcomes |
| ComfyUI preflight patterns | Shows guard-before-render architecture | Remove workflows, model names, and private render assumptions |
| Transport permission model | Shows paired identity/default-deny design | Reimplement a dependency-free demonstration from first principles; do not copy Sideband-derived source |

## Must remain private

- raw media, voice/reference materials, creative prompts/scripts, real chat
  history, uploads, and evaluation corpus;
- workflow JSON, render queue/runtime records, model files/checksums tied to
  local installation, device identities, radio profiles, and paired identities;
- local paths, usernames, network addresses, API credentials, authentication
  data, and generated logs containing any of the above;
- Sideband derivative package/source: its bundled license is CC BY-NC-SA 4.0,
  and its LXST component is CC BY-NC-ND 4.0. Keep all Sideband-derived source
  private; it is not a candidate for an open-source portfolio repository.

## Required release gates

- [x] Create a separate public repository; do not publish from the canonical
  working tree. Local git tree `local-agent-core` (home directory). No GitHub
  remote yet (`gh` not installed).
- [x] Copy only selected, reviewed modules and replace integrations with
  synthetic adapters/fixtures.
- [x] Build the non-destructive audit tool
  (`python local_agent/public_release_audit.py --dir <candidate>`). Run it on
  the eventual public candidate tree before a push.
- [x] Review and resolve every audit finding on that future public candidate
  tree. **0 findings** on 2026-08-25.
- [ ] Build an SBOM/dependency and license inventory, including any code
  adapted from third-party projects.
- [ ] Confirm each README claim has a matching test, changelog entry, or clearly
  labeled measurement.
- [ ] Record a sanitized demo with public-domain assets and inspect every frame
  before publication.
- [ ] Perform a human final review before the first public push.

## Claim language

Use **implemented and locally tested** for source behavior covered by a current
test. Use **experimental** for the RNode mesh and unmeasured remote reliability.
Use **in progress** for custom Android packaging and live device media features.
Never substitute a design document or static test for a performance or
end-to-end acceptance claim.
