# 2026-09-05bh — Status sync: APK review PR1 shipped, farm judge design closed

## Scope

Operator-facing tracking entry for two reports (`2026-09-05bf`/`bg`). No
new production work from this entry.

## 2026-09-05bf — Android companion PR 1 shipped

`local_agent/apk_review.py`: stdlib-only ZIP/manifest/signing review, no
Android SDK dependency. Fails closed (exit 1) on exactly the dangerous
permissions this design exists to prevent — `MANAGE_EXTERNAL_STORAGE`,
privileged `INSTALL_PACKAGES`, device-admin binding, `QUERY_ALL_PACKAGES`,
unsigned or wrong-package APKs. `REQUEST_INSTALL_PACKAGES` is flagged
(exit 2) rather than silently accepted, correctly deferred to PR 6. One
audit row per review (hashes and permission names only, never APK bytes,
never sent to the phone). 9/9 tests against synthetic APKs. PR 0 (A1-A14
acceptance) is now recorded in the design note itself.

## 2026-09-05bg — Farm semantic judge: sub-decision closed, design only

Closed the open sub-decision cleanly: secondary machines use their own
local Ollama, which was already true in practice on the Mac (confirmed
against the same LaunchDaemon/keep_alive work from earlier today).
Design reuses `judge_eval.py`'s existing four-layer isolation pattern
rather than inventing a new one — advisory-only, `auto_accepted: false`,
off by default. Correctly scoped the model choice to avoid a real
problem: running the semantic judge on the Mac's CPU-tier Qwythos-9B
(`num_gpu: 0`) rather than anything that would evict the farm's
GPU-resident tool-calling model. No build, no live judge run.

## Status

Task tracker: Android companion PR 1 done, PR 2 (ADB wrapper,
refuse-by-default) next. Farm semantic judge design closed, gated on
future build authorization like the other scoped-only items today.
