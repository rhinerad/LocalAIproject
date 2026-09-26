> **SUPERSEDED 2026-08-16 — historical evidence only. Do not execute.**
>
> This document authorised purpose-built VOX identity masters and limited the job
> to three masters plus controlled 00A/00I tests. Both are withdrawn:
>
> - **VOX and filler dialogue are prohibited again.** A missing voice comes only
>   from that character's first qualifying actual story soundtrack.
> - **The tests are finished.** The job is now all 124 Stage-1 soundtracks.
>
> The current instructions are `docs/AUDIO_PASS_RUNBOOK.md` (procedure) and
> `docs/H3_PROMPT_RULES.md` (prompt grammar), with `CLAUDE.md` binding. Where
> this file disagrees with those, they win.

# Equal Shares — MiniMax H3 Omni-Reference Voice-Lock Pipeline

Status: authoritative experiment and current execution path as of 2026-08-14.
This document supersedes every older instruction that prohibits VOX identity
references or tells an agent to resume the old nonblocking Stage-1 queue.

## Official prompt source

Use the official ComfyUI MiniMax H3 tutorial as the primary prompt-writing
reference for this project and future story-generator prompts:

`https://docs.comfy.org/tutorials/video/minimax/minimax-h3`

For Reference-to-Video prompts, follow its R2V guidance: refer to inputs by
their exact one-based connection tags (for example `<Picture 1>` and
`<Audio 1>`), explicitly assign each reference one job, and describe the scene,
camera, dialogue, sound effects, and music together in one timed prompt block.
Project safety, voice-lock, audio-acceptance, and no-Turbo rules in this handoff
remain binding where they are more specific.

## Decision and gate

The project is testing MiniMax H3 Omni-Reference voice locking before deciding
whether XTTS is needed. This is a small audio test, not permission to start the
0.9 MP film render. Picture generation remains blocked until all 124 complete
clip soundtracks have been generated, reviewed, and accepted.

## Voice identity rule

1. Every speaking character owns one immutable 5-10 second master WAV.
2. The exact same file, with the exact same SHA-256 digest, is supplied every
   time that character speaks. A rebuilt map may not silently change it.
3. Use one master audio reference for a one-speaker clip. Multi-speaker clips
   use one master per actual speaker, in speaking order, up to H3's limit of
   three standalone audio references.
4. Never use music, ambience, effects, a prior full soundtrack, or a second
   take of the same speaker as an extra audio reference in this voice-lock pass.
5. Pair the voice conditioning with the exact approved opening boundary image
   and the declared closing boundary image when one exists. The same character
   identity images remain the visual source of truth.
6. Purpose-built VOX recordings are authorized only as voice-identity masters.
   They never enter the edit and never become film dialogue.

The installed Rockernow node exposes at most three standalone audio references
and nine reference images. Its prompt language is one-based: `<Audio 1>`,
`<Audio 2>`, `<Audio 3>`, and `<Picture 1>`. Names such as `ref_audio_0` are
internal workflow sockets and must never appear in a MiniMax prompt.

## Prompt rule

For each numbered audio reference, explicitly bind the actual character to it:

`<Audio 1> is the fixed master voice for Narrator. Whenever Narrator speaks,
use the same voice identity, timbre, pitch, accent, and natural cadence as
<Audio 1>.`

The master is identity conditioning only and must be inaudible. Require exactly
one new dry foreground performance. Prohibit replay, leakage, quiet duplicates,
backing speech, whispers, alternate takes, chorus, delay, echo, and
speech-shaped reverb.

Put the exact quoted words once, inside their exact start/end window. Do not put
control prose such as "the audio is the deliverable" in the prompt; MiniMax has
spoken that phrase in previous attempts. No broad narration placeholders, no
second dialogue block, and no invented filler outside the quoted windows.

## Current deterministic sequence

1. Render 0.2 MP, 20-step, full-quality non-Turbo VOX masters for Crew Lead,
   Male Visitor One, and Male Visitor Two. Preserve every attempt.
2. Run `work/prepare_omni_voice_masters.py`. It creates versioned 5-10 second
   masters and pins their hashes in `omni_voice_master_map.json`.
3. Run `work/build_audio_pass_prompts.py`. It writes only to the versioned
   `prompts_audio_pass_omni_v1/` and `audio_pass_config_omni_v1.json` paths.
4. Preflight 00A and 00I, then render one preserved 0.2 MP attempt for each with
   the exact same Narrator master WAV.
5. Audit each test separately for: correct Narrator identity; one voice layer;
   exact scripted words; speech only in the assigned window; no leaked master
   words; and no invented spoken control prose.
6. If both pass, apply this same immutable-master method to the full Stage-1
   audio queue. Ear review does not stop unrelated audio generation, but it
   never becomes an acceptance automatically.
7. If the controlled test still doubles, leaks, or speaks gibberish, record the
   result and switch the full dialogue pass to VOX-conditioned XTTS when XTTS is
   installed. Do not keep burning full-story H3 attempts with a failed method.
8. Only after all 124 complete soundtracks are accepted may the 0.9 MP picture
   ladder begin. The picture ladder remains 0.9, 0.8, 0.7, 0.6, 0.5, 0.4 MP,
   with human review required after a failed 0.4 attempt.

## Safety and persistence

Never use Turbo. Never run two ComfyUI backends or two render coordinators.
Honor queue owner files and `thermal_guard.py`, including the 82 C emergency
ceiling. Never delete, overwrite, move, or rename raw generations, manifests,
audits, approved references, source audio, assembly inputs, or deliverables.
Normal safe project reads, versioned edits, rendering, validation, recovery,
and assembly should proceed automatically. A deletion/overwrite requirement is
handled by keeping the original and writing a versioned sibling.
