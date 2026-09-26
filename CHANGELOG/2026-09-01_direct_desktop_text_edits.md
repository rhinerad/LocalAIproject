# 2026-09-01 — direct desktop text edits

## Changed

A specific desktop-chat request is now the authorization for a normal text-file
write. `write_file` no longer requires a redundant sidebar approval for `.ini`,
`.cfg`, `.json`, `.bat`, or `.vbs` files.

## Safeguards retained

- Protected project records remain refused.
- Remote phone identities still require their explicit `write_file` capability.
- Binary edits still use the exact-byte inspection and approval gate.
- Failed writes remain truthfully reported as no file/directory change.

## Verification

- Added a regression test proving a requested `.json` text file writes without
  calling the sidebar file-edit gateway.
