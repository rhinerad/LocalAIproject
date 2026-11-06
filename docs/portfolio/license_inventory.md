# Candidate-module license inventory (draft)

**Status:** local planning inventory. **Not** an SBOM for a public push and
**not** permission to publish.

This answers upgrade-20 “audit candidate modules and transitive licenses
before open sourcing.” Sideband-derived trees stay private.

## Must stay private (already decided)

| Component | License recorded in-tree | Portfolio action |
|---|---|---|
| Vendored / forked Sideband | CC BY-NC-SA 4.0 | Do not copy into a public repo |
| LXST component inside Sideband | CC BY-NC-ND 4.0 | Do not copy |
| Equal Shares media, prompts, voices, workflows | project-private | Do not copy |
| MiniMax H3 weights / ComfyUI graphs | third-party / private install | Do not copy |

## Candidate public modules (from `public_release_boundary.md`)

These are **ideas for extraction**, not a repo that exists yet.

| Candidate | In-tree origin (private) | Apparent original-work status | Third-party runtime it talks to |
|---|---|---|---|
| Structured tool-call loop | `local_agent` native function-calling tests/helpers | Written for this project; no SPDX header on the harness files reviewed | Ollama (separate product/license) |
| Tool whitelist / validation | `local_agent` safety tests | Project-original patterns | none required for a synthetic demo |
| H3 evaluation harness | `local_agent/h3_evaluation.py`, `validate_h3_prompt.py` | Project-original; reports are aggregate hashes only | none |
| ComfyUI preflight patterns | guarded render helpers | Project-original **patterns**; strip workflow JSON and model names | ComfyUI (GPL-family desktop app — do not vendor) |
| Transport permission model | LXMF bridge tests | Reimplement from first principles; do **not** copy Sideband | Reticulum/LXMF are separate MIT-licensed projects if used as dependencies |

## Transitive runtimes (do not vendor unless license-reviewed)

Record as **dependencies of a future public repo**, not files to copy:

- Python 3
- Ollama (if the demo talks to a local daemon)
- Reticulum (`RNS`) / LXMF if a transport demo is included — currently used
  locally as `RNS 1.5.0` and `LXMF 1.1.1`; confirm upstream license files at
  extraction time rather than assuming
- llama.cpp (if a VLM demo is included)
- ComfyUI (call as an external service; do not ship its source unless the
  public repo is itself GPL-compatible and that is an explicit choice)

## Required before any public push

1. Create a **new** repository. Never push this working tree.
2. Copy only reviewed files; replace project tools with synthetic fixtures.
3. Run `python local_agent/public_release_audit.py --dir <candidate>`.
4. Attach an SPDX identifier to every published file.
5. Generate a real SBOM from that candidate tree (pip freeze is not enough).
6. Human review of README claims vs tests.

Until those gates pass, the honest portfolio sentence is: “license inventory
drafted; no public source published.”
