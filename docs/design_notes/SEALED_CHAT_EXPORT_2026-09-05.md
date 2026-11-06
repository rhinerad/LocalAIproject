# Design: sealed historical-chat export (off-box key)

| Field | Value |
|---|---|
| **Document** | Application-level encryption of chat exports so local admin cannot decrypt |
| **Date** | 2026-09-05 |
| **Status** | v1 helper built 2026-09-05 (`CHANGELOG/2026-09-05bj`); real export still gated |
| **TODO** | `TODO.md` “Obtain an explicit operator decision and source selection before staging any real historical export” |
| **New operator bar** | Exported chat history must be unreadable even with full local disk/admin access |
| **Does not authorize** | Touching `local_agent/chats/*.json` or submitting a non-`--sample` distill job |

This specifies **how an export must be sealed** if one is ever allowed. It does
not replace the existing gate. The live worker stays review-only and
synthetic. Same evidence bar as the phone-call-assistant note.

**BitLocker, a key next to the file, DPAPI, and `FARM_ENCRYPTION_KEY_B64`
all fail this bar.** Local admin can read the disk, the `.env`, and
user-DPAPI secrets. The decrypt key must never be on the source machine.

---

## Overview

Two different files get called “encrypted” in this tree today. Neither
meets the new bar:

1. **Farm artifacts** — AES-256-GCM envelopes under `FARM_ROOT`, key in
   `worker_farm/.env` (`FARM_ENCRYPTION_KEY_B64`). The worker **must**
   decrypt to run `distill_review_candidates`.
2. **PowerInfer private vault** — AES-256-GCM, key DPAPI-wrapped on the
   same box (`tools/powerinfer/vault.py` `load_key` / `encrypt_private`).
   Admin can unwrap DPAPI.

A sealed export is a **third class**: a portable ciphertext whose private
key lives only in the operator’s password manager / a second device. The
workstation holds a **recipient public key** and never a decrypt secret.

```text
chats/*.json  (plaintext today — not this task)
        |
        |  explicit source-selection decision (existing TODO — not given here)
        v
in-memory snapshot  (no plaintext tempfile)
        |
        |  age/GPG to recipient public key(s)
        v
opaque .age file   (ciphertext only on disk)
        |
        |  copy off-box
        v
decrypt on a different device, passphrase entered there
```

The farm distill path **cannot** use this sealing and still process the
text on DuranGamingPC: a worker that decrypts must possess the key. If
real transcripts are ever distilled here, that is a **weaker** threat
model and a separate sign-off. This note does not authorize that.

---

## What exists today (cited)

### The TODO gate (still closed)

`TODO.md` ~500–503: obtain an explicit operator decision and source
selection before staging any real historical export. The live worker
stays on the approved review-only workflow; the synthetic job does not
authorize private transcripts.

`CHANGELOG/2026-08-29_worker_farm_live_sample.md`: job
`distill_5090ec5b50892412f0c1a04a`, `review_required`, three candidates.
“No actual historical transcript.” Follow-up: any real export needs an
operator-selected source.

`RUN_PHASE1_SAMPLE.ps1` (~1–4, ~23): “cannot stage a real operator export
because it passes only `--sample`.”

`submit_distillation.py`: `--sample` vs a source path; `--sample` writes
the benign fixture (`SAMPLE` ~14) to a **`NamedTemporaryFile(...,
delete=False)`** (~53–55), stages it, then `unlink` in `finally` (~78–79).
That tempfile is **plaintext on disk**. Fine for the public fixture;
**forbidden** for a real transcript snapshot.

### Farm encryption (does not meet the new bar)

| Piece | Code | Why admin can read it |
|---|---|---|
| Key | `.env.example` `FARM_ENCRYPTION_KEY_B64` (~8); `farm_core.encryption_key` (~77–85) | 32-byte key in a local env file. Admin reads `.env`. |
| Envelope | `EncryptedArtifactStore.write_json` (~144–161) | AES-256-GCM; nonce + ciphertext + **plaintext_sha256** in JSON. Decrypt with the same `.env` key. |
| Staging | `stage_distillation_source` (~193–210) | Reads the source file (`_read_allowed_source` ~68–75), puts `raw_text` + `source_name` in the envelope. |
| Worker | `_run_distill` (`tasks.py` ~40–50) | `distill_review_candidates` decrypts, extracts, sanitizes, writes `result_*` with the **same** key. |
| Registry | `job_registry.py` (~36–37, ~44–56) | IDs, hashes, states only — no body. Still leaks that a `historical_memory_distillation` job existed. |
| Secondary nodes | `WORKER_FARM_MULTI_NODE_LAN_PLAN` ~51–52, ~166–167; Phase 1.5 ~166–168 | `distill` queue **forbidden** to secondary ACL users. Historical export is workstation-queue. |
| Doctor / status | `worker_farm/README.md` ~113–115 | Status scripts must not print source text, payloads, Redis password, or the AES key. |

`distill_export` (`tasks.py` ~155–159) is the only allow-listed historical
workflow. `judge_transcript` (~161–176) is the **opposite** trust
boundary: real chats may go to the Mac in the Celery envelope, no second
artifact layer, per the 2026-09-02 operator decision. **This sealed-export
requirement does not rewrite judge_transcript.** Judge jobs are live
worker input, not an “export file.”

### Chat source (plaintext on the workstation)

`store.py` (~3–6, ~22, ~63–66): one JSON file per conversation under
`local_agent/chats/`, greppable, titles from the first message. That
directory is already readable to local admin. Sealing an export does
**not** encrypt chats in place. In-place encryption of `chats/` is a
different product (breaks grep, GUI, LXMF bridge) and is out of scope.

### Other AES that also fails the bar

`tools/powerinfer/vault.py` `encrypt_private` (~349–372): ciphertext plus
**plaintext_bytes** and `source_name` in the envelope; key via DPAPI
(`load_key`). Local admin can DPAPI-unprotect. Same class as farm AES:
at-rest vs other users, not vs admin.

`docs/ENCRYPTED_ARCHIVAL_RUNBOOK.md`: restic with an operator password.
If that password is typed on this machine or stored in a file here, it
fails the new bar the same way. Restic is for media/evidence archives,
not this export. Do not reuse the restic repo password as the chat-export
key.

---

## What the new bar actually requires

**Threat:** someone with SYSTEM/Administrator on DuranGamingPC, or a
cold disk image of it, should not decrypt the **export file**.

**Not claimed:** protection against an attacker who is admin **while the
export process is running** and dumps RAM. Python chat JSON in
`str`/`bytes` can hit the pagefile / `hiberfil.sys`. That residual is
sign-off E6, not something a library call erases.

**Mechanism:** public-key encryption. Workstation has only the recipient
**public** key. Private key + passphrase exist only:

- in a password manager that does not sync that item onto this PC, or
- on a second device (phone, air-gapped USB), entered only at decrypt
  time there.

Recommended primitive: **age** (X25519, small header, easy recipients
file). GPG works but OpenPGP packets leak more (algorithm IDs, often
key-id). Either is application-level; neither is BitLocker.

Decrypt command (other device, not this design’s runtime):

```text
age -d -i "$HOME/chat-export.key" sealed_export_<hex>.age > snapshot.json
```

The workstation never runs `-d`.

---

## Plaintext window (must not hit disk)

Today’s failure pattern: `submit_distillation.py` `--sample` writes a
temp `.txt` then unlinks it (~53–79). Windows `unlink` does not securely
wipe. A real snapshot must **never** take that path.

Required pipeline if a real export is later authorized:

1. Read each allowed `chats/<id>.json` with `store.load` / `json.loads`
   into process memory. Do not assemble a directory copy, zip, or
   `NamedTemporaryFile`.
2. Build one in-memory JSON object (schema + opaque chat ids + messages).
   No `atomic_write_text` of that object.
3. Encrypt the UTF-8 bytes in memory (`age` encrypt to recipients, or
   `pyrage` / subprocess with stdin — **stdin/stdout only**, never
   `age -o` from a plaintext path).
4. `atomic_write` **only the ciphertext** to an opaque filename.
5. Drop Python references; do not write a `.tmp` of plaintext. A `.tmp`
   of ciphertext (same as `EncryptedArtifactStore` ~158–160) is allowed.
6. Do not log message bodies, titles, or paths. Fingerprint = SHA-256 of
   ciphertext or of plaintext **held in RAM then discarded** — if a
   plaintext hash is kept, it is a content oracle (see metadata).

`_read_allowed_source` (~68–75) reads an **existing** file. For a sealed
export, the source of truth is `store.py` memory, not “write a combined
export.json then encrypt that path.”

Subprocess `age`: plaintext on stdin, ciphertext on stdout. Do not use a
shell redirect from a file. Watch that Windows Python `subprocess` does
not create an unexpected temp when the blob is large (`_MAX_SOURCE_BYTES`
is 25 MiB today — keep a hard cap; do not spill to a scratch file).

---

## What the ciphertext file still leaks

Age/GPG hide the body. They do not hide the filesystem.

| Leak | If we do nothing | v1 mitigation |
|---|---|---|
| Outer filename | `chatgpt_rhine_pharmacy.json.age` names the topic | Opaque `sealed_export_<12 hex>.age` only |
| Inner tar/zip names | Titles and chat ids in headers | **No tar.** One JSON blob; ids inside ciphertext |
| Size | Ciphertext ≈ plaintext length | Optional pad to 1 MiB buckets (E7). Default: **accept size leak**, document it |
| mtime / ctime | When the export ran | Set mtime to a fixed epoch after write if the OS allows; Windows creation time may still leak |
| `plaintext_sha256` on the envelope | Farm store already publishes this (`write_json` ~154) | **Do not** copy that field onto a sealed export. It is a confirmation oracle |
| `plaintext_bytes` | PowerInfer envelope (~367) | **Do not** put byte counts in an adjacent `.json` sidecar |
| Recipient | Age header lists recipient public keys | One dedicated export recipient, not the operator’s daily SSH key; public key is not secret but ties the file to that identity |
| Adjacent files | `chats/*.json` still plaintext | Out of scope; admin who wants live chats does not need the export |
| Job registry | `workflow=historical_memory_distillation` | Sealed export is **not** a distill job. Do not register it in `worker_farm_jobs.sqlite3` |
| SHOW_PHASE1_STATUS | Metadata only today | Do not add sealed-export paths to that viewer |

A sidecar `sealed_export_<id>.meta.json` with `{created_at, byte_length,
recipient_fingerprint}` re-creates the leaks. **No sidecar.** If a
receipt is needed, it is a line in an append-only audit with
`ciphertext_sha256`, `recipient_sha256`, `bytes` (ciphertext bytes, not
plaintext), `at`.

---

## Interaction with the review-only worker (unchanged gate)

| Rule | Still true |
|---|---|
| Synthetic `--sample` only until source selection | `TODO.md` ~500–503, `RUN_PHASE1_SAMPLE.ps1` |
| Worker cannot promote memory / Chroma / render | `farm_core.distill_review_candidates` `promotion_rule` (~248); `ALLOWED_WORKFLOWS` |
| Secondary machines cannot take `distill` | ACL + `FARM_QUEUES` |
| This encryption task does not authorize a real export | Title of this document |

Sealed export and farm distill are **different outputs**:

| | Sealed export (this bar) | Farm `distill_export` |
|---|---|---|
| Key | Recipient public key; private key off-box | `FARM_ENCRYPTION_KEY_B64` on this box |
| Who can read | Operator on another device | Anyone with `.env` (admin) + the worker |
| Purpose | Take a copy off the machine | Extract review candidates on the worker |
| Real chats | Still forbidden | Still forbidden |

Do not “fix” `EncryptedArtifactStore` by stuffing an age file into
`FARM_ROOT` and expecting Celery to distill it. The worker would need the
private key, which puts the key back on a farm machine.

If the operator later wants distillation of real transcripts **and** this
bar, candidates are: (a) distill only on the decrypting device, (b)
accept that farm AES is a weaker class and keep real chats off `distill`,
(c) a new air-gapped worker that is not DuranGamingPC and holds the
private key — that is a new machine identity, not a default.

---

## v1 cut (honest)

**v1 that can exist without authorizing a real export:** a seal helper
and tests that only ever encrypt the existing benign `SAMPLE` string (or
a second public fixture). Proves: no plaintext tempfile, opaque output
name, decrypt only with a test keypair generated in a temp dir that is
**not** the workstation identity, refuse if no recipient file, refuse a
path under `local_agent/chats/`.

That is analogous to `three_d_contract.py`: a validator that cannot
submit work.

**v1 that does not exist:** a command that reads `chats/` and writes
`sealed_export_*.age`. That **is** a real historical export and stays
blocked on the existing TODO decision **plus** E1–E8.

**Not v1:** changing `EncryptedArtifactStore`; encrypting `chats/` in
place; age-encrypting Celery payloads; installing `age` without E5;
restic-as-chat-export.

Suggested later PR split, only after sign-off:

1. `sealed_export.py` + synthetic tests (no `chats/` read).
2. (Blocked) operator-selected source list → in-memory snapshot → seal.
   Still not a distill job.

---

## Operator / crypto sign-off (required before build)

| ID | Decision | Recommended default | Why a human |
|---|---|---|---|
| **E1** | May the seal helper be built while real export stays forbidden? | **Yes, synthetic-only**, like `--sample` | Useful tests; must not grow a `chats/` flag “just to try.” |
| **E2** | Primitive: age vs GPG vs other | **age** | Smaller header, easier recipients file. GPG if the operator already has an off-box key they refuse to duplicate. |
| **E3** | Where the private key lives | **Not on DuranGamingPC.** Password manager item that does not sync here, or a second device | This is the whole bar. |
| **E4** | Recipient public key material on this PC | One `age1…` line in an operator-chosen path **outside** the git tree | A dedicated export recipient, not SSH/GitHub keys. |
| **E5** | New binary/library (`age` / `pyrage`) | Operator-approved official `age` CLI, subprocess stdin/stdout; no silent pip | Same “no new dependency without a decision” as tracing Phase A. |
| **E6** | Residual RAM / pagefile / hibernation | **Accept** that a live admin during the run can dump RAM; optional: operator disables hibernation for the session | Cannot be fixed in Python alone on Windows. |
| **E7** | Size padding | **Off** in v1; document the leak | Padding is visible as “always multiple of 1 MiB,” which is also a signal. |
| **E8** | Real `chats/` snapshot | **Forbidden** until the existing source-selection TODO is answered **and** E1–E7 | This task does not answer that TODO. |

Until E1 is accepted, do not add a module. Until E8 is accepted, any
helper must hard-refuse paths under `local_agent/chats/` and
`store.DIR`.

---

## Non-goals

- Encrypting live `chats/*.json` in place
- Replacing `FARM_ENCRYPTION_KEY_B64` for Celery artifacts
- Putting the age private key in `.env` “but it’s encrypted”
- Using BitLocker as the export control
- Shipping a decrypt CLI on this workstation
- Quietly enabling `submit_distillation.py` without `--sample`

---

## Acceptance mapped to live code

| Requirement | Hook or gap |
|---|---|
| Stronger than FDE / adjacent key | Not `EncryptedArtifactStore`, not vault DPAPI, not BitLocker |
| Public-key seal | New; age recipient on disk, private key off-box |
| No plaintext tempfile | Today `--sample` **does** write one (`submit_distillation.py` ~53–55); real path must not |
| Opaque names / size / time leaks | Documented; no `plaintext_sha256` sidecar |
| Existing export gate unchanged | `TODO.md` ~500–503; `RUN_PHASE1_SAMPLE.ps1` `--sample` only |
| Worker still cannot promote | `promotion_rule`; no Chroma/memory write |
| This task does not authorize real transcripts | Explicit. No `chats/` reader in v1 |

Unverified here: whether `age.exe` is already on PATH. Treat as absent
until E5.

---

## Key decisions

1. **Farm AES and restic/DPAPI do not satisfy the operator bar.** They
   are decryptable with secrets this machine already stores.
2. **Sealed export ≠ distill job.** A worker that needs plaintext cannot
   hold only a public key.
3. **No plaintext file, even `.tmp`, even unlinked.** Encrypt from RAM;
   write ciphertext only.
4. **Metadata is a leak surface.** Opaque filename, no inner tar, no
   plaintext length/hash sidecar.
5. **The historical-export TODO stays closed.** Encryption design is not
   source selection.
