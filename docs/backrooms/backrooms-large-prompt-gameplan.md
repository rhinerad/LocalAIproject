# Getting the local agent to handle large, complicated prompt packs end-to-end

**Trigger:** chat `a051127dca4b4a25`, 18:08 local time — an 837,724-character paste (EDITOR OVERRIDES preamble + 102 clip prompts + a trailing status dump) that `ingest_prompt_pack` rejected with `"No clip prompts were parsed; nothing has been completed"`.

## Where things actually stand

Today's first fix (mine, verified against the on-disk `Backrooms_Sitcom_Audition_Prompt_Pack_MERGED_FINAL.md`) closed a real bug, but it was solving a different, narrower case than the one that actually failed. That file uses `### C001 — START FRAME IMAGE` headers under a `FULLY MERGED, CAMERA-LOGIC CORRECTED` title, and the fix stopped `backrooms_prompt_adapter.py`'s old camcorder-anchor rewriter from crashing on it. Good fix, still worth keeping — but Grok's follow-up traced the *actual* failed paste and found it's a different shape entirely: the `###` marks were stripped somewhere in how it got copied, and the title phrase (`FULLY MERGED` / `CAMERA-LOGIC CORRECTED`) is missing too. Both are load-bearing gates in `managed_prompt_pack.py`, so the plain `C001 — START FRAME IMAGE` headers (which a dedicated regex, `_PLAIN_FRAME_HEADER_RE`, already knows how to read) never got a chance to run, because that parser only turns on when the title phrase is present. Net effect: real clip content, unrecognized by either parser, zero clips out. I independently re-derived this from the actual regex definitions and it holds together.

There's a second thing I found independently while checking whether today's fix was even sufficient, unrelated to the crash: for packs that *do* parse via the "FULLY MERGED" path, the override-rewriter now no-ops entirely (that's what stopped the crash), and the backup enforcement path (`backrooms_compile.compile_job_settings()`, which is supposed to catch `## EDITOR OVERRIDES` independently and force `still_backend="flux"`) depends on an import that throws a `SyntaxError` on Python 3.10 (a real, pre-existing bug in `backrooms_compile.py` — an f-string with a backslash in its expression, invalid before Python 3.12). Every offline test in this whole engagement has run on 3.10, so that failure has been silently masked by a bare `except Exception` fallback the entire time. If it also fails on your real machine's Python 3.12 for some other reason, or if it never gets fixed, a pack that explicitly says "Flux, not SDXL" would silently render on `realvisxl` (SDXL) instead — no crash, no warning, just the wrong model. That's worse than the crash, because it looks successful.

And separately from both bugs: even a perfectly-parsed pack does **not** start rendering on its own. `wants_explicit_render()` deliberately treats a large pack's own body text as content, not an instruction — it requires an explicit render ask near the start or end of the message, and even then, actually starting production requires an operator-approved GPU gate every time. That's by design, not a bug, and I don't think it should be removed — but it's worth being explicit that "complete end-to-end on its own" realistically means "reliably get to a correct, fully-exported, ready-to-render state and clearly tell you it's waiting," not "render 102 clips with zero human involvement ever."

## The plan, in priority order

**1. Fix the real parser gap (blocking).**
Decouple `_parse_fully_merged_plain()` from requiring the title phrase. Trigger it on `_PLAIN_FRAME_HEADER_RE` match count alone (≥12 matches is already a strong, specific signal — a random 837K-character document doesn't accidentally contain a dozen `C0xx — START/LAST FRAME IMAGE` lines). Keep the title-phrase check as an *additional* OR'd trigger for backward compatibility, not the only one. This directly fixes the paste that actually failed.

**2. Close the Flux/SDXL override-enforcement gap (correctness, not just crashes).**
- Fix the `backrooms_compile.py` f-string syntax so it's valid on whatever Python versions you actually run (3.10 and 3.12 both, ideally — don't assume the sandbox and the production machine always match).
- Add an explicit test asserting `model_profile == "flux"` on parsed clips for an EDITOR-OVERRIDES-driven pack — not just clip *count*, which is what today's regression tests check and which would pass even with the wrong model silently selected.
- Run the one-line sanity check below directly on the production machine (not a sandbox) to confirm this isn't still silently broken there:
  ```
  python -c "import managed_prompt_pack as m; c=m.parse_clips(open('../Backrooms_Sitcom_Audition_Prompt_Pack_MERGED_FINAL.md',encoding='utf-8').read()); print(c[0].get('model_profile'))"
  ```

**3. Cover the actual failure shape in the regression suite.**
Add a fixture using plain `Cxxx — START/LAST FRAME IMAGE` headers with *no* `FULLY MERGED`/`CAMERA-LOGIC CORRECTED` title anywhere — the exact shape of the paste that failed — alongside the existing `###`-header fixture. Don't let the next reformatting variant slip through the same way this one did.

**4. Make failures diagnosable without archaeology.**
This entire investigation took hours partly because the original failed paste was never persisted (now fixed) and partly because there was no visibility into *which* branch of `parse_clips()` ran or why it returned empty. Add a lightweight debug field to the ingest failure path — match counts per regex, which branch was attempted, first/last 200 chars of what was actually searched — so the next format variant that breaks parsing is diagnosable from the stored failure artifact alone, not by asking two different AI agents to reverse-engineer it from a truncated task ledger.

**5. Make the agent's own behavior after ingest legible.**
Right now, a successful ingest-without-render-request just... stops, silently, with clips exported and nothing else said. For a pack this size, the agent's reply after a successful `ingest_prompt_pack` call should explicitly state the clip count and say something like "N clips exported and ready — say 'render it' to start stills+video production," so a real operator (or you, reading the transcript later) can tell the difference between "quietly finished the safe part and is waiting on you" and "silently did nothing."

**6. Re-verify before trusting it on a real multi-hour GPU job.**
Once 1-3 are done: re-run the actual failed paste (or as close to it as you can reconstruct) through `ingest_prompt_pack` for real, confirm clip count and `model_profile` are both correct, *then* explicitly ask for render. Don't skip straight to a live render on the strength of green unit tests alone — that's exactly the gap that let the SDXL-default issue hide for this long.

## What I'd hand to Grok next

```
Two things, in order:

1. managed_prompt_pack.py: _parse_fully_merged_plain() currently only runs
   when "FULLY MERGED" or "CAMERA-LOGIC CORRECTED" appears in the raw text
   (see the guard at the top of that function). The real paste that failed
   in chat a051127dca4b4a25 (837,724 chars) uses plain "C001 — START FRAME
   IMAGE" headers with no "###" and no title phrase at all -- so this
   function's own header regex (_PLAIN_FRAME_HEADER_RE) would match it fine,
   but the function never gets a chance to run. Change the trigger to fire
   on len(_PLAIN_FRAME_HEADER_RE.finditer(raw)) >= 12 directly, keeping the
   title-phrase check as an additional (not exclusive) trigger. Add a
   regression test using headers in exactly this shape (plain, no hash
   marks, no FULLY MERGED/CAMERA-LOGIC CORRECTED title anywhere) to lock
   this in.

2. backrooms_compile.py has a real syntax bug independent of the above: an
   f-string on/around line 348 contains a backslash inside the expression
   part (an f-string wrapping a raw-string regex literal), which is invalid
   before Python 3.12 and throws SyntaxError. Every offline test in this
   repo runs on Python 3.10 and has been silently swallowing this via a
   bare `except Exception` fallback in managed_prompt_pack._enrich_compiled_
   fields(), which means the Flux-override enforcement path
   (compile_job_settings() forcing still_backend="flux" when "## EDITOR
   OVERRIDES" is present) may never have actually been exercised by any
   test in this repo's history. Fix the f-string (pull the regex into a
   named variable before the f-string, don't build it inline), confirm the
   import succeeds on both 3.10 and whatever version production runs, and
   add a test asserting parsed clips get model_profile == "flux" (not just
   a clip count) for a pack containing "## EDITOR OVERRIDES", so a future
   regression here fails loudly instead of silently defaulting every still
   to realvisxl/SDXL.
```
