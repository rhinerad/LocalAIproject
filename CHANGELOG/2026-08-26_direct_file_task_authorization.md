# 2026-08-26 — Direct file-task authorization

## Change

An explicit desktop request to complete a normal text-file task now authorizes
the local agent to read the relevant file, edit it with `write_file`, and verify
the result in the same task. It no longer has to stop at a proposed diff or ask
for a redundant second approval.

`propose_file_diff` remains available when the operator asks to review a diff
first. The protected-record check in `tools.write_file` and
`tools.propose_file_diff` is unchanged: manifests, audits, queue ownership, and
other evidence files cannot be silently overwritten. Render and remote-phone
guards are unchanged.

## Operation

Server revision: `2026-08-26-direct-file-task-r59`.

No render, model load, or download was needed for this policy update.
