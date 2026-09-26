# Public-safe repository layout (plan)

**Status:** extracted. Local git tree is `local-agent-core` in the operator
home directory (outside this handoff folder). Secret scan: 0 findings.
GitHub remote not created because `gh` is not installed.

```
local-agent-core/                 # new repo, not this handoff folder
  README.md                       # 5-minute architecture + claim language
  LICENSE
  NOTICE                          # third-party attributions
  SECURITY.md                     # localhost-only, no public HTTP
  docs/
    architecture.md               # sanitized mermaid from architecture_overview.md
    adr/                          # copies of ADRs 0001–0005 after path scrub
    threat-model.md
    validation-matrix.md          # commands against synthetic fixtures
    licenses.md                   # SPDX + SBOM pointer
  src/
    tool_loop/                    # schema calls, multi-call, fallback
    tool_guard/                   # whitelist + path/permission checks
    preflight/                    # “do not render if GPU owned” patterns
    eval_harness/                 # aggregate-only evaluation runner
  tests/
    fixtures/synthetic/           # fake prompts, fake tool names
  examples/
    synthetic_job/                # numbered prompts, no private media
```

## Extraction rules

- Copy **patterns**, not Equal Shares content.
- Replace every project tool name with a synthetic example.
- H3 harness may ship only **synthetic** prompts and expected error codes.
- Do not include `outputs/`, `workflows/`, `vendor_sideband*`, runtime DBs,
  memory.json, or model files.
- ComfyUI remains an optional external backend.

## Claim language in the public README

Use the same vocabulary as `public_release_boundary.md`:

- **implemented and locally tested** — has a current test in this private tree
  and a synthetic equivalent in the public tree;
- **experimental** — RNode mesh, unmeasured radio reliability;
- **in progress** — custom Android packaging, live phone camera/mic.

## Not done

- Creating the GitHub (or other) repository.
- Copying modules.
- Final secret/path/license scan of a candidate tree.
- Recording the sanitized screen-capture demo.
