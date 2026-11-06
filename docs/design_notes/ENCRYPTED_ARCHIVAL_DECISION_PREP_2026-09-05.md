# Encrypted archival — decision prep (not a decision)

| Field | Value |
|---|---|
| **Document** | Operator choices required before the first Restic archive |
| **Date** | 2026-09-05 |
| **Status** | Prep only — no archive, no key, no Restic install, no upload |
| **TODO** | Backup hygiene: “Choose the first archive destination, recovery-secret custody approach, source roots, and approved execution window” |
| **Runbook** | `docs/ENCRYPTED_ARCHIVAL_RUNBOOK.md` (2026-08-29) |
| **Primer pattern** | Same job as `docs/SDXL_LORA_TRAINING_PRIMER.md`: enough fact to pick, not a build |

This is background reading for the gate the runbook already named. The
source-and-documentation ZIP (`work/New-LocalAgentSourceBackup.ps1`) is
**not** this archive. Nothing below authorizes `restic init`, a password,
a download, or a scheduled task.

The runbook requires a local-only `ARCHIVE_DECISION.md` (**never commit
it**) that records: primary destination, a separate second destination,
exact source roots, recovery-secret custody, restore contact/device, and
a restore-test date. This note is the menu. You fill that file.

---

## What is already decided (not reopened here)

- Format is a versioned, client-side encrypted **Restic** repository
  (AES-256 + Poly1305-AES per Restic’s published design).
- First execution is **operator-run only**.
- Do not prune, `forget`, delete, rotate keys, or repair automatically.
- Do not treat lack of space as permission to delete evidence.
- Google Drive plaintext upload is an explicit non-goal of the runbook.
- This does not replace the worker-farm AES-256-GCM artifact store, and
  it is not the sealed-chat-export track
  (`docs/design_notes/SEALED_CHAT_EXPORT_2026-09-05.md`).

Restic is **not installed** on this workstation (not on PATH, not under
`Program Files` / `AppData\Local\Programs` at a shallow search). The
runbook already says: install a current official Restic release **only
after** you approve the download.

---

## Live facts on DuranGamingPC (2026-09-05, this session)

Measured; not inferred from older docs.

| Item | Fact |
|---|---|
| Disk C: | Lexar NVMe 2 TB, NTFS, **~788 GB free**. OS + some user data. |
| Disk A: | Toshiba MG08ACA16TE 16 TB SATA HDD, label **RAD Disk**, NTFS, **~3.9 TB used / ~11.0 TB free**. Project tree, Equal Shares outputs, ComfyUI-Shared all live here. |
| USB / external | **None attached.** `Get-Disk` shows only the NVMe and the Toshiba. |
| Mapped NAS | **`net use` empty.** No SMB share mounted. |
| Google Drive desktop | DriveFS path **absent**. Drive is used as a *document index* (`docs/GOOGLE_DRIVE_PROJECT_SOURCE_INDEX.md`), not a file-sync folder. |
| OneDrive | Process running. Folder exists (`Apps`, `Desktop`, `Pictures`, `Videos`, **Personal Vault.lnk**). Tree ~**0.75 GB**. Not a Restic repo today. |
| Password managers | No local 1Password / Bitwarden / KeePass install path found. Custody would be something you already use off-box, Windows/Microsoft account, or a new tool — not something this machine currently runs. |
| BitLocker | `manage-bde -status` denied without admin. **Unknown** whether C: or A: is encrypted. Do not assume disk encryption. |
| GPU now | RTX 5080 **52 °C, 0 % util, 59 MiB / 16303 MiB, ~69 W**. Port **8188 not listening**. |
| Render owners | Equal Shares owner file names PID **16900** dated 2026-08-10 — **process not running** (stale). Batch and image-render owners `pid: 0` / released. Equal Shares remains **paused** per AGENTS.md. |
| Farm | `farm_status.json` **ok**, worker **`celery@Louises-MBP` only**, broker reachable. Hub peer is still just the Mac (`10.90.90.2`). |

Order of magnitude for a first media/evidence pass (see §3): **about 6–7 GB**
if you take the handoff `outputs/` tree plus selected Shared output
evidence, **not** model weights. Plenty of free space on both local disks;
space is not the hard part. **Independence of copies** is.

---

## 1. Destination options

The runbook wants **two** places: a primary, plus a separate second
destination or offline copy. Client-side encryption happens *before*
bytes land, so a cloud bucket is only a blob store — but only if you
never put the Restic password next to it.

None of these is “the” choice. Pair one primary with one second copy
that does not die in the same incident.

### A. Dedicated USB / external drive (not plugged in today)

You would attach (or buy) a drive used **only** for this Restic repo.
The runbook’s first listed option is “a dedicated external encrypted
drive.”

| | |
|---|---|
| **Survives** | Workstation disk death, OS reinstall, many ransomware paths (if the drive is **unplugged** except during backup/restore). |
| **Dies with** | The drive itself; theft of the drive *and* the password; fire if stored in the same room as the PC. |
| **Fits this machine** | Plausible. No external is connected now, so this is a hardware step you take, not a path I can point at. Capacity: first pass is single-digit GB; a 1–4 TB drive is ample with room for 14 daily / 8 weekly / 12 monthly snapshots. |
| **Cost** | Disk I/O on USB during backup; you must plug it in for the window and unplug after. BitLocker or hardware encryption on the *volume* is extra (Restic already encrypts the repo; volume encryption protects against casual mount if the password file were ever copied onto it — it should not be). |
| **Do not** | Reuse a drive that already holds unsorted backups, Equal Shares working copies, or the source ZIP. Empty dedicated destination. |

### B. Folder on C: (NVMe, different local disk)

A Restic repo under e.g. a new directory on C:, never inside the
handoff tree.

| | |
|---|---|
| **Survives** | Death of the 16 TB A: HDD (where the sources live). Fast. |
| **Dies with** | Same chassis: fire, theft, motherboard, many malware/ransomware incidents. |
| **Fits** | ~788 GB free. Trivial for ~7 GB + snapshots. |
| **Trap** | This is a **second disk**, not a **second site**. Valid as *one* of two copies, weak as the only copy. |

### C. Folder on A: (same HDD as the sources)

Technically easy: 11 TB free on RAD Disk.

| | |
|---|---|
| **Survives** | Almost nothing that kills the project tree. Same spindle, same SATA cable, same enclosure. |
| **Use** | Only as a *scratch* or *staging* copy if you insist, never as the primary and never as the second destination. The runbook’s “lack of space is a stop condition” is about not deleting evidence; it is not permission to keep the only ciphertext next to the plaintext. |

### D. NAS / another LAN computer (none mounted)

No share is mapped today. The only other live machine on the farm overlay
is **Louise’s MacBook Pro** (`10.90.90.2`), 2019, 16 GB RAM, already the
Celery worker.

| | |
|---|---|
| **NAS (if you have one offline)** | Good second site *on the LAN* if it is a different box and you never store the Restic password on it. Would need a mount or `sftp`/`restic rest-server` you set up. **Not observed**, so this is “tell me the hostname/share if you want this.” |
| **Mac over WireGuard** | Different machine, already reachable. Unknown free disk. Mixes **backup target** with **farm worker**. A full-disk Mac failure or a farm compromise then also holds the ciphertext (still needs the password). Bandwidth is the tunnel, not 1 GbE LAN. Only consider if you explicitly want the Mac as the off-box copy *and* have verified free space there yourself. |
| **Pixel** | Out of scope (small, different trust track). |

### E. Cloud-backed Restic repo (B2 / S3 / Wasabi / similar)

The runbook’s other listed primary: “a private cloud/object-store
repository.” Restic encrypts locally; the bucket sees ciphertext.

| | |
|---|---|
| **Survives** | House fire, theft of the PC, HDD death. This is the only option in the list that is a real off-site copy without you carrying a drive. |
| **Dies with** | Provider account lockout **plus** no second copy; you deleting the bucket; password loss. |
| **Fits this machine** | `rclone` is **not** installed either. First use needs an operator-approved install of Restic and a backend (Restic native S3/B2, or rclone). Home LAN / hotspot: first ~7 GB upload is one evening, not a render-length job. |
| **Not this** | **Google Drive as a folder of files**, OneDrive camera-roll sync, or dumping ZIPs into Drive. The runbook forbids Drive upload as a procedure, and Drive/OneDrive are poor Restic backends compared with B2/S3. OneDrive Personal Vault is a Microsoft custody toy for a few files, not a versioned evidence repo. |
| **Account** | Needs a bucket you control, separate from chat/Google-docs login if you can. Access keys are **not** the Restic password; keep them in the same custody plan as other credentials, never in the repo. |

### Pairings that actually satisfy “two destinations”

Pick **two failure domains**:

| Pair | What it covers | What it does not |
|---|---|---|
| USB (unplugged) + C: | Disk death + many malware paths if USB stays offline | House fire if USB lives next to the PC |
| USB (unplugged, stored elsewhere) + B2/S3 | Disk, fire, theft of one site | Password loss (see §2) |
| C: + B2/S3 | HDD death + off-site | Chassis theft still has C: copy; cloud account |
| NAS (other building/floor) + USB | Local network + offline | Not available until a NAS exists |
| A: + anything | A: copy is nearly worthless | Do not pair A: as a “destination” |

I am not picking a pair.

---

## 2. Recovery-secret custody

Restic’s repository password is the whole archive. The runbook: long
unique password; **password manager plus an offline recovery copy**;
never in a command line, source file, chat transcript, or the
repository. Prompt for manual runs, or an operator-created password
file **outside** the repo with restrictive ACLs if you later approve a
scheduled task.

This machine does **not** currently run 1Password / Bitwarden / KeePass.
Whatever you already use on phone/browser still counts if you can open
it when this PC is gone.

Sealed-chat-export is a **different** secret (age/GPG private key, never
on this workstation). Do not reuse that key as the Restic password, and
do not put the Restic password on DuranGamingPC “because BitLocker.”
BitLocker status is unverified here; even if on, local admin can read
the disk.

| Approach | What it protects against | What it does not |
|---|---|---|
| **Password manager only** (1Password, Bitwarden, etc., syncing to your phone) | Forgetting; this PC dying; shoulder-surfing a sticky note. Phone can unlock the archive after a house incident *if* the vault is reachable. | Manager account lockout, phishing the vault, or a single-device vault that lived only on this PC (you do not appear to have a local-only KeePass file). |
| **Printed / offline paper** (or a steel card) in a place that is not this desk | Manager outage; you locked out of the vault; this PC gone. The runbook’s “operator can locate the recovery secret without relying on this workstation alone.” | Fire/theft of that hiding place; someone who finds the paper. Treat like a will: envelope, not a screenshot in chat. |
| **Split custody** (e.g. Shamir / two envelopes / manager half + paper half) | One stolen location or one compromised vault is not enough. | Operational pain. Restore drill must prove **you** can reassemble without me. Overkill for a 7 GB first repo; reasonable if the archive later holds irreplaceable private media. |
| **Password file on this PC** (`restic` `--password-file`) | Convenience for an approved scheduled task. | Theft of the PC, malware, backup of the home directory. The runbook allows this **only** outside the repo, restrictive permissions, and **not** as the only copy. Do not create one until you approve scheduling. |
| **DPAPI / BitLocker / farm AES key** | Nothing relevant. Same-box wrapping. The sealed-export note already rejected these for a stronger bar; they are also wrong here as *sole* custody. | — |

Minimum that matches the runbook’s own words: **manager + offline
copy**, two different places, restore contact is a device that is not
DuranGamingPC (phone or another PC). Schedule a restore-test date in
`ARCHIVE_DECISION.md`.

I am not generating a password.

---

## 3. Source roots (realistic, with sizes)

Runbook include-after-review:

- original and approved raw media
- final renders and embedded-prompt evidence
- immutable manifests, checksums, and review artifacts
- large local-agent encrypted artifacts where retention is required
- model conversion profiles, activation logs, and accepted validation manifests

Never by default: `.env` / API keys / phone identity keys / Redis
credentials; transient caches, venvs, Docker layers, replaceable build
outputs; the source ZIP itself.

Sizes measured 2026-09-05. **Include means “candidate for your list,”
not “already approved.”**

### Strong candidates (this is the evidence the ZIP refuses)

| Root | Size | Why |
|---|---|---|
| `outputs/equal_shares/` | **3.36 GB**, 5794 files | Audio masters, frames, review, voices, quarantine of the 2026-08-17 corrupt-prompt pass, runtime logs/config. This is the Equal Shares evidence tree. Largest buckets: `_QUARANTINE_corrupt_prompt_pass_2026-08-17` 0.80 GB, `runtime` 0.76 GB, `audio` 0.71 GB, `frames` 0.47 GB, `review` 0.28 GB. You may still exclude `__pycache__` and throwaway validation subfolders. |
| `outputs/stories/` | **0.01 GB**, 12 files | General-story stills + manifests (media v1/v2). Small; fits “final renders.” |
| `docs/GOLDEN_REFERENCE/` | ~0 GB, 4 files | Proven graphs. Also in the source ZIP; including it in Restic still makes the evidence archive self-contained. |
| Desktop `EQUAL_SHARES_FIRST_APPEARANCE` / `_GENERATION_LIST` / `_VOICE_AUDITIONS` | **0.16 GB** together | Operator-facing packs, not inside the handoff `outputs/` tree. |

### Shared Comfy output — slice, do not swallow

`A:\Users\rhine\ComfyUI-Shared\output` is **2.93 GB**, 791 files, mixed:

| Slice | Size | Note |
|---|---|---|
| `output/video/` | 1.17 GB | Includes `good audio\` (**0.01 GB, 16 files**) — the golden takes. Rest of `video/` is not automatically golden. |
| `output/Finished_realesrgan_x4plus_work` | 1.45 GB | Upscale work product; replaceable if you still have sources, evidence if you do not. |
| Other named folders (`story`, `h3-ryan`, `DBS scene proj`, …) | ~0.3 GB | Project-ish; review before include. |
| Hundreds of `ComfyUI_*.png` in the output root | small each, noisy | Unreviewed stills. Default **out** until you name a keep-set. |

Do **not** archive `ComfyUI-Shared\models\` (weights are replaceable and
huge). Do **not** archive `runtimes\`.

### Local-agent trees — mostly no

| Root | Size | Default |
|---|---|---|
| `local_agent/uploads/` | 0.10 GB | **Maybe.** Original attachments; some may be private. Explicit review, not a wildcard. |
| `local_agent/chats/` | ~0 GB, 105 JSON | **No** for this Restic. Plaintext chat is the sealed-export TODO, different key, different bar. |
| `local_agent/worker_farm/runtime/artifacts/` | empty | Include later if farm AES envelopes that must be retained appear. Still never `.env`. |
| `artifacts/powerinfer_vault/` | empty | Same. |
| `artifacts/backups/` source ZIPs | (under `artifacts/` 0.35 GB total) | Source ZIP is a **different backup class**. Do not put it in this repo. |
| `archive/` | ~0 GB, 25 files | Old logs/state; review, don’t wildcard. |
| `local_agent/.env`, `wireguard/hub.conf`, `hub-private.key`, phone pairings | — | **Never.** |

### Suggested first-pass menu (still your pick)

**Narrow (restore-drill sized, still real evidence):**
`docs/GOLDEN_REFERENCE/` + `ComfyUI-Shared\output\video\good audio\` +
one small Equal Shares manifest directory. Proves Restic + SHA-256
restore without hashing 3 GB of audio.

**Working evidence set:** narrow + `outputs/equal_shares/` (with an
exclusion list for `__pycache__`) + `outputs/stories/` + the three
Desktop Equal Shares folders.

**Only if you explicitly want Shared dump:** add named folders under
`ComfyUI-Shared\output` after a keep/drop pass. Not the whole `output\`
root.

A dry-run manifest (labels, relative paths, bytes, mtimes, SHA-256) is
step 3 of the runbook and happens **after** you pick roots, still
operator-run.

---

## 4. Approved execution window

Restic backup is **CPU + disk**, not a GPU workload. It still must not
collide with a render or with farm work that is using this box’s disks
or GPU. Standing numbers from `work/thermal_guard.py`:

- start only at **≤ 70 °C** (`START_MAX_C`); prefer cooled to
  **≤ 60 °C** (`START_RESUME_C`)
- **82 °C** is emergency stop for GPU jobs; if the card is anywhere near
  that, something else owns the GPU — **do not start an archive**

### Preflight (all must be true)

1. `nvidia-smi`: utilization **0 %** (or clearly idle), temperature
   **≤ 60 °C**, VRAM not holding a 14B / Comfy / vision model you care
   about. **Right now: 52 °C, 0 %, 59 MiB — GPU-idle, but that is not
   a standing reservation.**
2. Port **8188** not listening, unless you have confirmed Comfy
   timeshare-idle *and* are not hashing `ComfyUI-Shared\output` while it
   writes. Prefer 8188 down.
3. Live PIDs in `outputs/equal_shares/runtime/render_queue_owner.json`,
   `batch_render_queue_owner.json`, and
   `work/runtime/image_render_owner.json` are **absent or dead**. Stale
   JSON does not count as a lock; a live PID does. Today the August
   Equal Shares owner PID is dead.
4. Equal Shares audio/picture pass is **not** in progress (it is paused
   as a project; do not unpause it for this).
5. No local-agent turn in flight that is itself calling media tools or
   writing `outputs/` (`chat_busy.json` PID, if present, must be dead).
6. **Farm:** Mac Qwythos / judge / summarize may keep running **as long
   as this archive is not saturating A: while a workstation-side farm
   helper writes artifacts**, and you are not submitting new heavy farm
   jobs from this box during the hash. The Mac does not need to be
   powered off. Do **not** use the Mac as the backup target in the same
   window you are also pounding it with Qwythos.
7. USB destination, if chosen, **plugged in before start**, unplugged
   after verify.

### During the job

- Explicit source roots only; no `A:\` wildcard.
- Password via prompt, not CLI.
- After backup: `restic check`, then restore **one small non-sensitive
  file** to a fresh temp dir and compare SHA-256 to the dry-run
  manifest.
- Record snapshot id, roots, bytes, verification time, restore result
  in a **local encrypted archive log** (not in git, not in chat).

### How long

A first pass of ~7 GB on the 16 TB HDD is minutes to a small number of
tens of minutes (hash + copy), not a 124-clip render. Cloud upload of
the same, if you chose B2/S3, is bandwidth-bound (hotspot vs LAN). Still
treat it as a reserved window, not a background “while I render.”

### Do not

- Overlap Kohya / SDXL LoRA / Comfy enqueue / `comfy_generate`.
- Run prune/`forget` in the first window.
- Call the window “approved” in chat and then start it without
  `ARCHIVE_DECISION.md` filled.

---

## What you type when you have decided

Create **untracked** `ARCHIVE_DECISION.md` (desktop or encrypted vault —
not this git tree) with:

1. Primary destination (A/B/D/E above, with a concrete path or bucket).
2. Second destination (different failure domain).
3. Exact include roots and exclusions.
4. Custody: where the password manager entry lives, where the offline
   copy lives, restore device that is not this PC, restore-test date.
5. “Execution window: only when preflight 1–7 pass.”

Then, and only then, a later session can do runbook steps 1–6
(install Restic with your approval, dry-run manifest, `init`, backup,
check, tiny restore). That session still does not invent a password for
you.

---

## Explicit non-goals of this note

No Restic binary, no `restic init`, no password, no `ARCHIVE_DECISION.md`
in-repo, no copy of media, no change to Equal Shares evidence, no GPU
job, no farm task, no Google Drive upload.
