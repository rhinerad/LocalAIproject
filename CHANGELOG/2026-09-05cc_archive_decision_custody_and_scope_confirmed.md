# 2026-09-05cc — Archive decision: custody + source scope confirmed (remaining fields)

## Scope

Operator tracking entry. Records the last two operator picks needed for
`ARCHIVE_DECISION.md` field 2/3, following the destination-pair decision
already recorded in `2026-09-05by`.

## Purple's decision-menu report

`docs/design_notes/ENCRYPTED_ARCHIVAL_DECISION_PREP_2026-09-05.md`
content relayed in full. Its destinations section (A:/C:/USB/NAS/cloud
scan) reflects an earlier disk scan taken before D: was verified
(`2026-09-05bu`) and does not list D: — no longer the live options list;
`by`'s A:+D: decision supersedes that section. The custody and
source-root sections are current and were used for the picks below.

## Operator decisions

1. **Recovery-secret custody:** password manager (phone-synced) + one
   offline copy stored away from this desk — the runbook's own stated
   minimum. No manager is installed on this PC yet; the Restic repo
   password will be generated at `init` time and the operator will
   record it (write-down and/or manager entry) at that moment, before
   any archive proceeds.
2. **Source-root scope:** strong-include list only —
   `outputs/equal_shares/`, `outputs/stories/`, `docs/GOLDEN_REFERENCE/`,
   the Desktop Equal Shares packs (~3.5GB). `ComfyUI-Shared\output`
   (good audio, upscales) is explicitly **excluded** from this first
   pass, along with everything already on the runbook's default-out list
   (`chats/`, `.env`/keys, venvs, models, the source ZIP, empty vaults).
3. **First restore-drill scope**, adjusted for the above: since
   `ComfyUI-Shared\output\video\good audio\` is out of scope this pass,
   the drill uses only in-scope material — `docs/GOLDEN_REFERENCE/` plus
   one small manifest from `outputs/equal_shares/`. Purple's originally
   proposed "golden graphs + good audio + one manifest" drops the
   good-audio leg accordingly.
4. **Execution window:** the preflight checklist as written (GPU ≤70°C
   idle, port 8188 down, no live render-owner PID, Equal Shares pass not
   running, no in-flight local-agent media turn, D: plugged in only for
   this window and unplugged/stored elsewhere after verify). No
   prune/forget in the first window.

## Status

All five `ARCHIVE_DECISION.md` fields are now decided:
destination pair (A:+D:), custody approach, source-root scope, first
restore-drill scope, execution-window rule. Dispatching Purple to write
the untracked file and proceed through Restic install/init/first
archive/restore drill under these exact constraints.
