# Portfolio dependency and license inventory — preliminary

This is an evidence-based triage document, not legal advice or a substitute for
a final license review. It lists only the dependencies visible in the local
agent's tracked requirement files and bundled license texts as of 2026-08-25.
It intentionally contains no local paths, device identities, or private media.

## Candidate public core

| Component | Direct dependency posture | Release status |
|---|---|---|
| Native Ollama tool-call loop | Python standard library HTTP/JSON plus a locally hosted Ollama service | Candidate only after synthetic fixtures and independent license review |
| Tool-schema/validation patterns | Python standard library | Candidate only after project-specific tools/actions are replaced with synthetic examples |
| H3 aggregate evaluation harness | Python standard library | Candidate only with wholly synthetic prompts/fixtures |
| Render-preflight patterns | Python standard library plus a local ComfyUI API boundary | Candidate only after private workflow/model assumptions are removed |

## Dependencies that remain private

| Item | Evidence in this project | Constraint |
|---|---|---|
| Sideband source | Bundled `LICENSE` identifies CC BY-NC-SA 4.0 | Do not publish a derivative in the portfolio repository without qualified legal/licensing review. |
| LXST component | Bundled `libs/lxst/LICENSE` identifies CC BY-NC-ND 4.0 | Do not redistribute modified derivatives. Keep private. |
| Able component | Bundled `libs/able/LICENSE` identifies MIT | Record attribution if separately reused; do not assume it clears Sideband-derived code. |
| RNS, LXMF, pyserial | Listed in `requirements-lxmf.txt` | Identify authoritative licenses and notices before public release. |
| ChromaDB | Listed in `requirements-exemplar-retrieval.txt` | Identify authoritative license and transitive dependencies before public release. |
| Ollama models / model files | Locally supplied runtime assets | Never include weights in a public repository; review each model's license separately. |

## Required release work

- [ ] Create a separate public repository from selected, synthetic-only code.
- [ ] Generate an SBOM for that public candidate—not this private working tree.
- [ ] Verify every direct and transitive dependency against its authoritative
  repository/package metadata and retain attribution notices.
- [ ] Confirm no Sideband-, RNS-, LXMF-, or project-derived file enters the
  public candidate unless its exact license permits the proposed use.
- [ ] Run `local_agent/public_release_audit.py` on the candidate tree and
  resolve every finding before publication.
- [ ] Obtain a human/legal review before publishing any component with a
  non-commercial, no-derivatives, copyleft, or unclear license.
