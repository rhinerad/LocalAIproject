# 2026-08-30 — TurboSparse loader memory blocker

**Later the same day:** the streaming loader was implemented. Root cause
confirmed as host-RAM pressure from Transformers 4.41 full-shard `load_file`,
not a need to leave Windows. Canonical checkpoint:
`...\turbosparse-mistral-abliterated-projected-20260830b`. See
`2026-08-30_turbosparse_projected_abliteration_loader_fix.md` and
`2026-08-30_turbosparse_abliteration_docs_accepted.md`.

After pinning the exact checkpoint stack to Transformers 4.41.2 and bypassing
the optional FlashAttention import scanner, the 4-bit measurement process
entered checkpoint-shard loading but advanced only to shard 1 after several
minutes. GPU allocation stayed near 1.3 GiB, indicating host-memory/pagefile
thrashing rather than useful GPU loading. The isolated process was interrupted
before inference; source weights and all prior evidence remain unchanged.

Next implementation options are a lower-memory streaming loader or a Linux/WSL
environment. Do not retry repeatedly on the Windows desktop until one of those
changes is made; the 47B target remains out of scope.
