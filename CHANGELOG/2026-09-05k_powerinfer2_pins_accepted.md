# 2026-09-05k — PowerInfer-2 Android cross-build pins accepted by operator

## Scope

🩷 lane, Pixel edge track. Documentation-only: locks the pins Grok chose
during the 2026-09-05i cross-build (`CHANGELOG/2026-09-05i_powerinfer2_android_crossbuild.md`)
as the project's canonical pins, since the plan doc had never named an
exact commit or NDK version — only placeholders.

## What changed

- `docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md`: added a "Locked build
  pins, 2026-09-05" section recording commit `8bd56d69906c9d2dba4d3bf6899763401e01a9a4`,
  NDK r27d (27.3.13750724, linux-x86_64) with zip hash, and the resulting
  `llama-cli` hash/size/format. Replaced the `<pinned-ndk-version>` build
  recipe placeholder with the locked NDK path. Also added a pointer note
  that the step-2 smoke-test model was superseded 2026-09-05 to
  `huihui-ai/SmallThinker-3B-Preview-abliterated` (see `2026-09-05c`),
  without changing the 21B deployment target.
- `TODO.md`: checked off the cross-build item under "PowerInfer-2 mobile
  edge evaluation," with the pin values and evidence trail inline.

## What was not done

No rebuild, no new hashes generated, no phone contact, no model fetch.
Commit `8bd56d6` is an existing `external/PowerInfer` HEAD snapshot from
2026-05-11, not an upstream tag — `main` was deliberately not pulled
during the original build to keep the pin reproducible; a future rebuild
against a different commit needs its own dated pin-update entry here, not
a silent drift.

## Next

Step 2 (Pixel test with the abliterated 3B-Preview model) is still
untouched and gated behind the remaining private-overlay edge gateway
work per the plan doc's Phase D acceptance criteria.
