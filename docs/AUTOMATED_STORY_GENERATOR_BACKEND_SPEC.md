# Automated ComfyUI story-generator backend — product specification

## Product goal

The end deliverable is not merely one completed Equal Shares film. It is a
working, reusable, resumable backend that can accept a new story, turn it into a
narrative and shot plan, create/manage reference assets, generate and validate a
complete soundtrack, generate and validate picture through ComfyUI/MiniMax H3,
retry recoverable failures, organize every artifact, assemble the film, and
produce an auditable final master.

**Equal Shares is the reference project and end-to-end acceptance test for that
backend.** Any logic learned here should move into generic backend modules and
configuration rather than remaining hard-coded to 124 clips or these character
names.

The GUI is a later phase. Do not begin GUI implementation until the backend can
complete the workflow through its command/API surface, resume after interruption,
and pass its automated completion audit. The future GUI must call the backend;
it must not duplicate render, validation, retry, or state logic.

## Backend definition of done

The backend is ready for GUI work when all of these are true:

- A user can provide a story and optional creative constraints.
- The backend produces an editable narrative plan, cast/continuity bible, scene
  list, variable-duration clip plan, dialogue timing, sound plan, first-frame
  requests, and optional last-frame requests.
- The user can approve/edit that material before expensive generation.
- Approved reference images and audio carry versioned provenance.
- The entire soundtrack is generated and accepted before picture generation.
- Picture generation uses the approved soundtrack and the fixed resolution
  fallback policy.
- Audio and visual validators produce structured reasons, never vague pass/fail.
- Failed work can retry, pause, resume, or enter a human-review queue without
  losing or overwriting evidence.
- One render owner controls ComfyUI/GPU use; a crash cannot create a second
  backend or corrupt the queue.
- Assembly uses only accepted inputs and the exact approved soundtrack.
- A machine-readable completion audit proves every required artifact exists and
  every gate passed.
- Equal Shares completes through this backend with no project-specific manual
  manifest surgery.

## Core workflow

### 1. Story ingestion and narrative planning

Input: story text plus optional target tone, style, rating, desired length,
characters, locations, aspect ratio, and creative rules.

Output should be editable before rendering:

- premise, theme, act/sequence outline, and ending;
- character list, appearance/wardrobe locks, motivations, relationships, and
  voice descriptions;
- location and prop continuity rules;
- scene list and ordered clips of variable duration;
- per-clip action, camera, first frame, optional last frame, dialogue windows,
  ambience, music, effects, and negative constraints;
- validation plan stating what would make the clip pass or fail.

No expensive image/audio/video generation begins until this plan is approved.

### 2. Reference-asset planning

The backend decides which reference assets are actually needed:

- character identity sheets and approved wardrobe/location references;
- exact first-frame image for every clip;
- exact closing-frame image only where it materially improves continuity or a
  required camera destination;
- canonical character voice references;
- recurring music, ambience, device tones, room beds, and effects.

Reference generation is provider-adapted. A project may use ChatGPT image
generation, another configured image provider, or an approved local model. The
backend records provider, source prompt, input references, creation time,
approval, and version. It never silently replaces an approved asset. Existing
approved frames are reused before requesting new images.

### 3. Canonical voice and sound references

For each character, inspect story appearances in order and choose the first
**delivered** MiniMax H3 take with at least six seconds of clean, contiguous,
single-speaker audio and adequate speech density. A merely scripted first line
does not qualify if the delivered take is gibberish, noisy, mixed, silent, or too
short. If none qualifies, render the character's first qualifying actual story
soundtrack at 0.2 MP using only the original story dialogue. Purpose-built VOX
jobs and invented reference dialogue are prohibited. A real-story passage below
six seconds must receive human voice review before canonical promotion.

Recurring sound uses the same provenance rule: the first approved clean
occurrence becomes the reference for its continuity group. Non-diegetic score is
one continuous master across the edit, not a freshly generated song per clip.

### 4. Complete soundtrack pass

Render every planned clip—including clips without dialogue—using full-quality
MiniMax H3 ref2va at the lowest proven audio resolution, currently 0.2 MP:

- exact opening image as `ref_image_0`;
- closing image as `ref_image_1` whenever the plan supplies one;
- canonical character voices in spoken-order reference slots;
- recurring sound reference when relevant and a slot remains;
- exact dialogue once, inside timed beats;
- timed ambience, music, and physical effects.

The low-resolution picture is disposable. Preserve each native H3 MP4 and
extract its full soundtrack to a versioned candidate WAV.

### 5. Soundtrack validation and retry

After each candidate, the backend checks:

- audio stream, duration, sample rate, channels, clipping, and near-silence;
- expected words, word order, omissions, additions, repetition, likely
  gibberish, muttering, and speech in supposedly silent clips;
- dialogue timing windows and speaker separation;
- canonical voice similarity when a reliable installed comparator exists;
- recurring music/ambience/effect continuity;
- prompt-required sound events.

An empty transcription is unknown, never pass. Validators are pluggable and
versioned so a stronger local speech/voice model can replace Windows Speech
later without changing the manifest contract.

Retry order is structured: tighten timing, split long clauses, lock non-speakers
silent, strengthen sound-reference jobs, then change seed. Preserve each prompt,
seed, measurement, transcript, and verdict. A candidate becomes `accepted` only
after every applicable audio dimension passes.

The backend hard-blocks picture work until every planned clip has accepted audio.

### 6. Picture generation around approved audio

For each clip, run full-quality MiniMax H3 ref2va with:

- the approved opening image;
- the approved closing image when present;
- the exact accepted full-clip WAV as the principal audio reference;
- a MiniMax-friendly prompt telling the model to preserve every word, speaker,
  pause, music cue, ambience, effect, and timestamp and to generate performance
  around that audio.

Start at 0.9 MP. When a visual attempt fails, preserve it and follow the fixed
ladder:

`0.9 → 0.8 → 0.7 → 0.6 → 0.5 → 0.4 MP`

Keep 20 steps. Use the failure reason to revise prompt and seed when useful. If
0.4 MP still fails, create a `human_review_needed` work item and stop automatic
rendering for that clip. Never descend below 0.4 MP automatically.

### 7. Visual validation and retry

Objective screening checks streams, duration, dimensions, frame rate, black or
frozen spans, hard scene changes, and obvious instability. It prepares
native-resolution frames for semantic review.

Agent vision then checks the full motion and native frames against the plan:

- faces, identity, hair, wardrobe, and character count;
- anatomy, hands, fingers, limbs, gait, and object interactions;
- duplicate, merged, extra, missing, or disappearing people;
- camera, blocking, architecture, props, geography, and screen direction;
- temporal morphing, flicker, unintended cuts, and scene replacement;
- visible text, captions, logos, and watermarks;
- start/end frame intent and all clip-specific acceptance rules.

Contact sheets may prioritize review but cannot pass a clip. Upscaling cannot
repair anatomy or identity.

### 8. Exact-audio mux, assembly, and publication

The high-resolution render's decoded audio is diagnostic only. Mux the exact
accepted soundtrack WAV onto the selected picture. This prevents Stage 2 from
changing accepted words, voices, music, ambience, effects, or timing.

Assemble only visually accepted clips with matching accepted audio. Apply the
continuous score as one track across cuts. Publish versioned deliverables and
retain original chunks even when they live outside the shared ComfyUI output;
report every such location.

## State machine and manifest contract

Every project and clip uses explicit states. Suggested project states:

`draft_plan → awaiting_plan_approval → references → audio_pass → audio_gate_passed → picture_pass → assembly → final_audit_passed`

Suggested audio states:

`planned → blocked_missing_reference → rendering → retry_required → needs_ear_review → continuity_review → accepted`

Suggested picture states:

`blocked_audio_gate → rendering_0.9 → needs_agent_native_review → review_rejected → rendering_next_rung → visually_accepted`

Terminal exception:

`human_review_needed`

Every attempt record includes:

- stable project, scene, clip, job, and attempt IDs;
- parent inputs and content hashes;
- model/node/settings, resolution, steps, seed, prompt, and references;
- start/end timestamps and source paths;
- mechanical probe and validator version;
- transcript/metrics or visual failure taxonomy;
- review verdict, reviewer, note, and time;
- selected/promoted output paths without deleting older attempts.

Writes are atomic. Runner-owned manifests are never hand-edited during a render.
Commands are idempotent: rerunning a stage salvages valid existing work and does
not overwrite an accepted output.

## Backend modules

The reusable backend should converge on these separable modules:

1. `project_service` — create/load/version a story project.
2. `narrative_planner` — story-to-scenes/clips/dialogue/validation plan.
3. `reference_manager` — image, voice, and recurring-sound provenance.
4. `prompt_compiler` — provider/model-friendly prompts from structured plans.
5. `comfy_queue_manager` — one owner, backend lifecycle, submit/monitor/recover.
6. `audio_renderer` and `audio_validator` — full soundtrack gate.
7. `picture_renderer` and `visual_validator` — exact-audio render and MP ladder.
8. `review_queue` — agent/human decisions with structured reasons.
9. `assembler` — exact-audio mux, score, edit, encode, publish.
10. `completion_auditor` — end-to-end artifact and provenance proof.

Equal Shares scripts may remain as adapters while these generic services are
extracted. New generic code must take a project root/config rather than embedding
Equal Shares paths, clip counts, character names, or duration.

## Command/API surface before GUI

The first usable product is a CLI or local API with equivalent operations:

- create/import project;
- build and export narrative plan for editing;
- approve plan and references;
- report status and blockers;
- generate/review voice and sound references;
- run/resume/pause soundtrack pass;
- validate/retry/approve soundtrack candidates;
- run/resume/pause picture pass;
- review/reject/accept picture attempts;
- list `human_review_needed` items with evidence;
- assemble, publish, and run completion audit.

The future GUI will display and invoke these operations. It should be a thin
client over the same state and commands, so work can continue headlessly and the
GUI can close without interrupting a render.

## Safety and operational rules

- Full-quality MiniMax H3 only; never Turbo.
- One ComfyUI backend and one GPU owner at a time.
- No downloads without an explicit later decision.
- No deletion or destructive overwrite of evidence.
- Copy rather than move; write versioned siblings.
- Mechanical validity is not creative acceptance.
- Recover after crashes from manifests and actual output probes.
- Every retry must have a reason and preserve the prior attempt.
- The backend reports meaningful progress without dumping logs.

## Current implementation bridge

The Equal Shares reference implementation currently maps as follows:

- narrative/config: `outputs/equal_shares/story_config.json`;
- voice selection: `work/build_voice_reference_map.py`;
- audio prompts: `work/build_audio_pass_prompts.py`;
- soundtrack rendering: `work/render_audio_pass.py`;
- audio filtering/review: `work/validate_audio_pass.py`,
  `work/review_audio_pass.py`;
- recurring sound policy: `outputs/equal_shares/audio_continuity_map.json`;
- picture rendering: `work/render_picture_pass.py`;
- visual filtering/review: `work/validate_visual_pass.py`,
  `work/review_picture_pass.py`;
- final gate: `work/audit_equal_shares_completion.py`.

These are the starting implementation, not the final generic API. The next
backend-engineering milestone after Equal Shares completes is to extract their
shared behavior into project-agnostic services while keeping this film as a
regression fixture.
