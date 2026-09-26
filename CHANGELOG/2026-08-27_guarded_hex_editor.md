# 2026-08-27 — guarded binary hex editing

## Added

- `inspect_binary`: read-only bounded hexadecimal/ASCII inspection of a binary
  file, including its path, size, byte offset, and SHA-256 checksum.
- `apply_hex_patch`: one fixed-length, in-place byte replacement. It requires
  the supplied old bytes to match the file, limits a patch to 4096 bytes, and
  requires a one-shot File edit approval tied to the exact old/new byte values,
  offset, path, and whole-file checksum.
- The File edit card now displays an exact byte-patch summary when applicable.

## Safeguards

- The tool cannot create a file or insert/delete bytes.
- It rechecks both checksum and target bytes immediately after approval, before
  writing.
- It refuses all protected records and the complete `outputs/equal_shares/`
  evidence tree.
- Phone identities are default-denied for the binary-write tool; a separate
  exact per-identity capability grant is required.

The operator granted `apply_hex_patch` to the active paired Sideband identity.
That grant does not bypass the byte-match, checksum, protected-evidence, or
desktop File edit approval checks.

## Verification

`python -m unittest local_agent/test_native_tool_calling.py -v`: **26/26
passing**, including inspect, approval, exact replacement, mismatch, evidence
protection, and remote-default-deny coverage.
