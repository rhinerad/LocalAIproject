# 2026-09-05bl — Sealed export v1 verified: refusal and no-plaintext claims both proven live

## Scope

🟢 lane, Task #57's build. Reviews Grok's own report (`2026-09-05bj`).
No new work.

## What shipped and why it's trustworthy

`local_agent/sealed_export.py` — age X25519 sealing, RAM straight to
ciphertext, no decrypt capability shipped on this machine (correct —
the whole point is the private key never lives here). `atomic_io.py`'s
`atomic_write_bytes` only ever touches the ciphertext `.tmp` file, never
plaintext. 7/7 tests pass.

Both of the two hardest claims were verified adversarially, not just
asserted:

- **The chats/ refusal actually fires**: a real attempt to seal
  `local_agent/chats/must_not_be_read.json` raises and refuses before
  the target file is even created, and the CLI path returns exit 2 for
  the same case. A grep lock further confirms the helper contains no
  `NamedTemporaryFile`, `store.load`, or `plaintext_sha256` — and a
  deliberately reintroduced bad copy was confirmed to get caught by that
  lock.
- **No plaintext ever hits disk**: a real test polls both the
  destination directory and an isolated process temp directory *while
  the seal is running*, searching for the fixture's plaintext bytes.
  Zero hits. The resulting `.age` file was confirmed to start with the
  correct `age-encryption.org/v1` header and to not contain the canary
  string, with a round-trip decrypt (test-only, not a shipped CLI
  capability) confirming the ciphertext is actually recoverable.

Output filenames are opaque (`sealed_export_<12 hex>.age`), and the
recipient is a public key only, matching the design's requirement that
the private half never lives on this machine.

## What was not done

No real export — only the synthetic `distill --sample` fixture can be
sealed. Real chat history remains fully blocked behind the existing
"obtain explicit operator decision and source selection" TODO item,
unchanged by this work.

## Status

Task #57 fully closed: scoped, sign-off accepted, built, and both of its
hardest security claims were proven with real adversarial tests rather
than left as design assertions.
