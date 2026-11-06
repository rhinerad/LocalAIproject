# 2026-08-31 — agent.py: _ACCESS_BYPASS_RE over-matched legitimate everyday requests

## What changed

Split `_ACCESS_BYPASS_RE` in `agent.py` into two tiers to eliminate six confirmed
false positives that were silently refusing ordinary desktop-assistant requests
before any model was ever called.

**Before** — a single flat verb set matched any of
`bypass|circumvent|crack|jailbreak|evade|remove|skip|disable|unlock` within
80 characters of any of
`paywall|login|authentication|auth|license|activation|premium|subscription|purchase`
(in either order). Words like `disable`, `remove`, `skip`, and `unlock` are
common management verbs that appear constantly in legitimate sentences, so the
flat set produced a constant stream of false positives.

**After** — two tiers:

- **Tier 1** (`bypass|circumvent|crack|jailbreak|evade`): always hostile; still
  matches any access-control noun from the original full set.
- **Tier 2** (`remove|skip|disable|unlock`): only matches high-specificity nouns
  (`paywall|activation|premium`) where a malicious reading clearly dominates.
  `login`, `authentication`, `subscription`, `license`, and `purchase` are
  excluded from tier-2 matching because they appear too often in legitimate
  sentences.

## Why

Found during the access-bypass-guard audit triggered by the 2026-08-30i handoff.
All six hypothesis cases from the handoff were confirmed false positives by
running `agent.answer()` directly (mocked chat_stream). Every one of these was
silently returning the bypass-refusal message with no model call:

| Request | False-positive trigger |
|---|---|
| "How do I disable auto-login on Windows 11?" | `disable` near `login` |
| "How do I disable subscription auto-renewal?" | `disable` near `subscription` |
| "Remove my old license key to activate on another computer" | `remove` near `license` |
| "Authentication to unlock my phone after forgotten passcode" | `authentication` near `unlock` (reverse) |
| "Cancel my Netflix subscription and remove my card on file" | `subscription` near `remove` (reverse) |
| "Skip the login screen on my Raspberry Pi at boot" | `skip` near `login` |

None of these involve paywalls, software activation bypass, or premium content
circumvention. All six are routine account-management or system-configuration
questions that a general desktop assistant must answer helpfully.

## What was verified

**Live audit (mocked chat_stream/router, real guard code):**
- today's `will`-fix confirmed: "get the model ready" → "I will download the
  model once you approve the GPU gate." passes through unchanged ✓
- all 6 false-positive cases confirmed: guard was firing, model never called;
  all 6 return helpful model response after the fix ✓
- scope routing: `needs_project_context()` returns False for general knowledge,
  creative writing, and generic "render/clip" queries; True only for explicit
  Equal Shares identifiers ✓

**Regex verification — before vs after:**

| Input | Before | After | Correct |
|---|---|---|---|
| "disable auto-login on Windows 11" | MATCH (wrong) | no match | after |
| "disable subscription auto-renewal" | MATCH (wrong) | no match | after |
| "remove my old license key" | MATCH (wrong) | no match | after |
| "authentication to unlock it" | MATCH (wrong) | no match | after |
| "subscription and remove my card" | MATCH (wrong) | no match | after |
| "skip the login screen on my Pi" | MATCH (wrong) | no match | after |
| "bypass its paywall and login" | MATCH | MATCH | both (tier 1) |
| "crack the license protection" | MATCH | MATCH | both (tier 1) |
| "jailbreak to evade the authentication check" | MATCH | MATCH | both (tier 1) |
| "you can disable the paywall with this trick" | MATCH | MATCH | both (tier 2) |
| "skip the paywall" | MATCH | MATCH | both (tier 2) |
| "unlock premium features without a subscription" | MATCH | MATCH | both (tier 2) |

**Test suite:** 31/31 pass (was 29/29 before; +2 new test methods).

Added to `test_native_tool_calling.py`:
- `test_access_bypass_false_positives_get_helpful_responses` — all 6 false-
  positive cases now get a model response, stream is called, bypass refusal
  is not returned
- `test_access_bypass_tier2_verbs_still_refuse_high_specificity_nouns` — 5
  cases with tier-2 verbs near paywall/activation/premium still trigger the
  guard without calling the model

## Residual notes

- Passive-voice forms like "can be disabled" (past participle) are not caught
  by `\bdisable\b` — consistent with the original regex, which also used the
  base verb only. This was already the case before this change and is out of
  scope for this fix.
- The remaining guards (`_START_CURRENT_RENDER_RE`, `_STOP_COMFYUI_RE`,
  `_SONIC_PI_*`) were not audited in this session; only `_ACCESS_BYPASS_RE`
  and the previously fixed `_UNVERIFIED_EXECUTION_RE` were in scope.
