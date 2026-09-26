# 2026-09-05ba — Sealed chat export scoped; existing farm AES doesn't meet the new bar

## Scope

🟢 lane, Task #57. Reviews Grok's own report (`2026-09-05az`). Design
only — no real export authorized, no code shipped.

## Key finding: the existing encryption doesn't clear the new bar

`distill_export`'s `EncryptedArtifactStore` (AES-256-GCM) keeps its key in
`worker_farm/.env` on the same machine that can decrypt it — a local
admin can read `FARM_ENCRYPTION_KEY_B64` directly and decrypt every
distill artifact. BitLocker or a key sitting next to the file fail for
the identical reason: the decryption capability lives on the same box as
the ciphertext. Also flagged, correctly: `local_agent/chats/*.json` is
already plaintext today — sealing a future *export* does nothing for
live chat storage, which is a separate problem not addressed by this
scope.

Also caught: the existing `--sample` synthetic path
(`submit_distillation.py`) writes a plaintext tempfile and unlinks it —
acceptable for the public synthetic fixture, explicitly **not**
acceptable for a real snapshot under the new requirement.

## What the bar actually requires

Public-key sealing (age recommended over GPG) to a recipient whose
private key never lives on this machine — decryption only possible on a
separate device or an unsynced password-manager item. No plaintext ever
touches disk, not even a tempfile: read to RAM, encrypt, write ciphertext
only. Residual leaks correctly identified as unavoidable and named
explicitly rather than glossed over: outer filename (mitigated with an
opaque name), approximate file size (padding optional), timestamps, and
the age recipient identity in the file header. Explicitly flagged: do
not copy the farm's `plaintext_sha256` onto a sealed-export sidecar —
that would function as a content oracle for guessing plaintext.

Correctly noted: `distill_export` and a sealed chat export are
necessarily different outputs, because a worker that decrypts for
distillation processing must hold the secret — this new sealing scheme
is fundamentally incompatible with the farm's existing keying if the
farm still needs to read the content.

## v1, gated behind sign-off

A synthetic-only seal helper (same pattern as `three_d_contract.py`) can
exist once E1 is signed off, and must hard-refuse any path under
`chats/`. A real command touching actual chat history is explicitly not
v1 — it still requires the pre-existing source-selection operator
decision plus a new sign-off item (E8). Full sign-off list (E1-E8) is in
`docs/design_notes/SEALED_CHAT_EXPORT_2026-09-05.md`: helper-vs-real-export
boundary, age-vs-GPG choice, key custody, recipient file location, new
binary dependency, RAM/pagefile residual risk, padding decision, and the
chats/ hard-refusal.

## What was not done

No real export, no key generated, no code shipped. The pre-existing
"obtain explicit operator decision before staging any real historical
export" TODO item stays closed/unaddressed by this scope, as intended.
