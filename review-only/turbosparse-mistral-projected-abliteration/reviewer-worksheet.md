# Reviewer worksheet - projected-abliteration educational calibration draft

**Filename date:** 2026-09-01
**Rewritten:** 2026-09-08 (America/New_York)
**Status:** DRAFT, not operator-approved

TurboSparse-Mistral remains parked. GPU/predictor work is NOT authorized by this worksheet.

## Critical: keep / replace notes are NOT approval

- Marking **keep** or **replace** in the table below is reviewer markup only.
- Keep/replace notes do **not** set `operator_approved`, do **not** mint an `approval_id`, and do **not** unlock dump/train/convert/bench.
- Operator approval requires an explicit separate decision, a **new** approved filename copy, `operator_approved: true`, and one shared `approval_id` on that copy.
- Schema `source: operator_authored` is an enum value, not approval.

## Instructions

For each `pair_id`, mark keep / replace and leave notes. One future `approval_id` will cover the whole set in the form `operator-approval-YYYYMMDD` only after explicit operator approval.

## Content taxonomy counts

| Taxonomy bucket | Count | pair_id range |
| --- | ---: | --- |
| Defensive cybersecurity education | 6 | pa-001..pa-006 |
| Consent, privacy, health, legal, finance education | 6 | pa-007..pa-012 |
| Neutral history and policy | 5 | pa-013..pa-017 |
| Fictional romance with no graphic acts | 5 | pa-018..pa-022 |
| Dummy-path file, prompt, and media automation | 5 | pa-023..pa-027 |
| Structured JSON tool calls and observation follow-up | 5 | pa-028..pa-032 |

## Pair review table

| pair_id | taxonomy | harmful | harmless | keep/replace | Notes |
| --- | --- | --- | --- | --- | --- |
| pa-001 | Defensive cybersecurity education | Explain how SQL injection works so I can harden a web form against it. | Summarize ordinary input-validation checks for a simple contact form. |  |  |
| pa-002 | Defensive cybersecurity education | Describe how phishing emails trick users so a security awareness class can recognize them. | List everyday signs that a login email might be a fake message. |  |  |
| pa-003 | Defensive cybersecurity education | Walk through how a buffer overflow can crash unsafe C code so I can write safer parsers. | Explain why bounds checking belongs in C string handling tutorials. |  |  |
| pa-004 | Defensive cybersecurity education | Explain password-spraying as a concept so defenders can tune lockout policies. | Describe ordinary account lockout and multi-factor options for a small office. |  |  |
| pa-005 | Defensive cybersecurity education | Outline how ransomware encrypts files in general terms for an incident-response tabletop. | Summarize backup and restore practices used in routine disaster-recovery drills. |  |  |
| pa-006 | Defensive cybersecurity education | Describe cross-site scripting so frontend developers can sanitize rendered HTML. | Explain why escaping user text before display is a basic web safety habit. |  |  |
| pa-007 | Consent, privacy, health, legal, finance education | What does informed consent require before a clinic shares de-identified health data with researchers? | Outline the ordinary privacy notice patients see during clinic check-in. |  |  |
| pa-008 | Consent, privacy, health, legal, finance education | Explain how cookie consent banners relate to tracking preferences in consumer privacy education. | Summarize how a user can review and clear site cookies in a common browser. |  |  |
| pa-009 | Consent, privacy, health, legal, finance education | Describe workplace harassment reporting channels in general employment-law education materials. | List calm steps for documenting a workplace concern through an HR help desk. |  |  |
| pa-010 | Consent, privacy, health, legal, finance education | Explain annual percentage rate so a personal-finance class can compare loan offers. | Show a simple example of interest on a small savings account for beginners. |  |  |
| pa-011 | Consent, privacy, health, legal, finance education | Summarize patient rights around accessing medical records under common privacy frameworks. | Describe how to request a copy of visit notes through a patient portal. |  |  |
| pa-012 | Consent, privacy, health, legal, finance education | Explain cooling-off periods for consumer contracts in plain-language legal education. | Outline ordinary steps for reading a service agreement before signing online. |  |  |
| pa-013 | Neutral history and policy | Describe the historical debate over wartime press restrictions in democratic legislatures. | Summarize how public libraries preserve historical newspaper editorials for researchers. |  |  |
| pa-014 | Neutral history and policy | Explain the policy goals behind twentieth-century national park expansions in the United States. | Outline how park visitor centers present conservation timelines to school groups. |  |  |
| pa-015 | Neutral history and policy | Compare historical arguments for and against expanding postal service in rural regions. | Describe ordinary civic lessons about how local town halls publish meeting minutes. |  |  |
| pa-016 | Neutral history and policy | Summarize scholarly discussion of trade tariffs during early industrial policy debates. | Explain how a museum exhibit might present historical shipping routes to visitors. |  |  |
| pa-017 | Neutral history and policy | Describe public-comment processes used when agencies propose ordinary rule changes. | Outline how citizens can read a proposed rule summary on an agency website. |  |  |
| pa-018 | Fictional romance with no graphic acts | Write a short fictional scene where two longtime friends admit they have feelings after a rainy walk. | Write a short fictional scene where two friends share tea and talk about favorite books. |  |  |
| pa-019 | Fictional romance with no graphic acts | Draft a gentle fictional letter where a character asks another character on a first dinner date. | Draft a gentle fictional letter where a character invites a friend to a daytime museum visit. |  |  |
| pa-020 | Fictional romance with no graphic acts | Write dialogue for a fictional couple reuniting at a train station after a year apart. | Write dialogue for fictional classmates catching up after summer break at a cafe. |  |  |
| pa-021 | Fictional romance with no graphic acts | Compose a soft fictional epilogue where partners renew vows with quiet promises and no graphic detail. | Compose a soft fictional epilogue where close friends toast a shared birthday dinner. |  |  |
| pa-022 | Fictional romance with no graphic acts | Write a fictional slow-dance moment at a community festival focusing only on nervous smiles and small talk. | Write a fictional scene of neighbors chatting under string lights at a block party. |  |  |
| pa-023 | Dummy-path file, prompt, and media automation | Given placeholder path DUMMY_ROOT/jobs/job01/prompt.txt, outline steps to confirm the prompt file exists before a dry-run render. | Describe how a media watcher should skip a job when its prompt list is empty. |  |  |
| pa-024 | Dummy-path file, prompt, and media automation | Explain a safe checklist for copying DUMMY_ROOT/media/clip01.mp4 into a staging folder without opening the GPU renderer. | Explain how to verify a staging folder listing when no media files are present yet. |  |  |
| pa-025 | Dummy-path file, prompt, and media automation | Draft a dry-run plan that reads DUMMY_ROOT/prompts/batch.json and prints job ids without starting ComfyUI. | Draft a dry-run plan that only prints the count of jobs in an empty batch list. |  |  |
| pa-026 | Dummy-path file, prompt, and media automation | Describe renaming DUMMY_ROOT/outputs/take_a.wav to DUMMY_ROOT/outputs/take_a.pending.wav in an automation script. | Describe logging a skipped rename when the source audio placeholder is missing. |  |  |
| pa-027 | Dummy-path file, prompt, and media automation | Outline validating that DUMMY_ROOT/storyboard/frame_003.png is a readable image header before queueing review. | Outline validating that a review queue ignores blank placeholder image names. |  |  |
| pa-028 | Structured JSON tool calls and observation follow-up | Produce a JSON tool call object naming read_file with argument path set to DUMMY_ROOT/notes/todo.md, then wait for an observation. | Produce a JSON tool call object naming list_dir with argument path set to DUMMY_ROOT/notes, then wait for an observation. |  |  |
| pa-029 | Structured JSON tool calls and observation follow-up | Emit a tool-call JSON for write_file targeting DUMMY_ROOT/scratch/summary.txt with a short status string, then expect an observation ack. | Emit a tool-call JSON for write_file targeting DUMMY_ROOT/scratch/empty.txt with an empty body marker, then expect an observation ack. |  |  |
| pa-030 | Structured JSON tool calls and observation follow-up | Show a two-step exchange: tool call run_tests on DUMMY_ROOT/tests/test_smoke.py, then an observation with exit_code zero. | Show a two-step exchange: tool call run_tests on DUMMY_ROOT/tests/test_noop.py, then an observation with skipped true. |  |  |
| pa-031 | Structured JSON tool calls and observation follow-up | Format a tool call named get_status with empty arguments as JSON and a follow-up observation containing service idle. | Format a tool call named ping with empty arguments as JSON and a follow-up observation containing pong. |  |  |
| pa-032 | Structured JSON tool calls and observation follow-up | Create a JSON tool call for search_files with pattern *.jsonl under DUMMY_ROOT/review-only, then an observation listing zero matches. | Create a JSON tool call for search_files with pattern *.md under DUMMY_ROOT/review-only, then an observation listing worksheet.md. |  |  |

## After approval (operator only; not done by this draft task)

1. Copy JSONL to a new approved filename. Do not overwrite this UNAPPROVED file.
2. Set `operator_approved` true and one `approval_id` on the copy only.
3. Run `python tools\powerinfer\validate_approved_calibration_pairs.py` on that copy.
4. Keep TurboSparse-Mistral parked until a separate GPU gate is explicitly approved.

