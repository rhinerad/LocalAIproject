# 2026-08-18 — one-off speakers need no voice, and the routing that follows

## What changed

Operator rule, verbatim:

> "if there are characters that only have a spoken part in one generation of
> video then we dont need to remember their voice and that video can be generated
> with regular image to video minimax. If there is a scene where there is only one
> generation of spoken part for a character but there is also a character that has
> more then one spoken part within all the generations; this will be generated in
> the minimax audio/video/image to video generator. The character that has only
> one spoke part in one generation does not need an audio reference."

Implemented as:

```
speaks in 2+ clips  ->  RECURRING  ->  needs a master, gets <Audio N>
speaks in 1 clip    ->  ONE-OFF    ->  needs nothing, gets no <Audio N>

no recurring speaker in the clip  ->  fl2va  (MiniMaxH3ImageToVideo), no refs
any recurring speaker             ->  ref2va (MiniMaxH3ReferenceToVideo),
                                      refs for the RECURRING speakers only
```

### Files

| File | Change |
|---|---|
| `work/classify_voice_requirements.py` | **New.** Single source of the classification. Writes `outputs/equal_shares/voice_requirements.json`. |
| `work/build_native_r2v_prompts.py` | Reads it; omits `<Audio N>` for one-off speakers even when a master file exists. Also fixes a live tag-numbering bug — see below. |
| `work/build_voice_auditions.py` | Skips one-offs. 17 packs → **9**, 51 renders → **27**. |
| `work/harvest_good_audio_masters.py` | Prompt extraction bug fixed — see below. |
| `CLAUDE.md` | Sixth binding audio rule. |
| `docs/AUDIO_PASS_RUNBOOK.md` | New step 0. |
| `START_LOCAL_AGENT.md` | Job 2 rewritten: 8 characters → 2. |
| `docs/GOLDEN_REFERENCE/PROVEN_FACTS.md` | New §10; §1 and §2 corrected. |
| `Desktop\EQUAL_SHARES_VOICE_AUDITIONS\_NOT_NEEDED_one_off_speakers\` | 8 packs quarantined, not deleted, with a README explaining why. |

## Why it is right

A voice master exists for exactly one purpose: to make a character sound the same
in clip 7 as they did in clip 3. A character who speaks in one clip has nothing to
be consistent with — their voice is whatever that single render produces, and it
cannot contradict itself. Referencing them costs a slot out of H3's three and
conditions a voice nothing needs to match.

## Measured on this film

| | count | |
|---|---|---|
| speakers | 18 | |
| recurring | **10** | Kent 32 clips, Narrator 16, Ryann Sally 14, Avery 10, Doris 5, Faith White 3, Volunteer 3, Housing representative 3, Terminal voice 2, Male Visitor One 2 |
| one-off | **8** | Aid worker, Congregation member, Council member, Crew lead, Doris recording, Male Visitor Two, Unhoused man, Wealthy commuter |
| fl2va clips | **4** | `01B`, `20B`, `22B`, `30B` |
| ref2va clips | 74 | |
| mixed | **3** | `00D2`, `27E`, `28C` |
| audio reference slots used | 90 | no clip exceeds H3's limit of 3 |

**Six of the eight one-offs were on the runbook's Job 2 list of provisional
masters**, so Job 2 collapses from 8 characters to 2: `Male Visitor One` and
`Terminal voice`. The audition pass drops from 51 renders to 27.

## Evidence that the fl2va path works

`17.mp4` in the good-audio folder **is clip `01B`** — one of the four fl2va
clips. `MiniMaxH3ImageToVideo`, `minimax_h3_fl2va_pruned_int8_convrot`, 0.2 MP,
20 steps, `res_multistep`/`simple`, denoise 1.0, 24 fps, two boundary images,
a real AAC track. The operator filed it under good audio.

Two caveats, stated rather than glossed:

1. Its prompt declares `<Audio 1>` and `<Audio 2>` although the fl2va node **has
   no audio reference sockets** — it promised references the graph could not
   supply and worked anyway. The generator now omits them for fl2va clips rather
   than relying on the model to ignore them.
2. "Filed under good audio" is the operator's judgement of the take overall, not
   a verified statement that both one-off voices are right.

## Two bugs this exposed

### 1. My own `17.mp4` identification was wrong

`harvest_good_audio_masters.py` read the prompt only from
`PrimitiveStringMultiline` nodes. `17.mp4` carries its prompt inline on the
sampler node's `prompt` input, so the harvest returned an empty prompt and
reported **"17.mp4 — no dialogue"**. It is `01B` with two spoken lines.

Corrected in the tool and in `PROVEN_FACTS.md` §1 and §2. The folder holds **15**
speaking takes, not 14, and also contains Wealthy commuter and Unhoused man —
both one-offs, so neither needs anything.

### 2. A live off-by-one in the tag numbering

`build_native_r2v_prompts.py` numbered `<Audio N>` by the speaker's position in
the clip while `continue`-ing past speakers with no master. **Reference tags
follow connection order**, so a clip whose first speaker lacked a master declared
the second speaker as `<Audio 2>` and wired it into `ref_audio_0` — describing a
reference that was not there and mis-attributing the one that was.

Measured before the fix: **4 mis-numbered tags across `27E`, `28C`, `00D2`.**
`27E` declared `<Audio 1/2/3>` for Council member, Kent and Ryann Sally. Under the
one-off rule only Kent and Ryann get references, so the correct tags are
`<Audio 1>` and `<Audio 2>` — which is what it now emits. Tags are assigned
sequentially as sockets fill.

This bug predates today's rule and would have mis-conditioned those clips
regardless.

## Unresolved and logged, not silently decided

`Doris recording` speaks only in `22B`, so the rule makes it a one-off — but it is
a **recording of Doris**, who is recurring with a master of her own. Under the
literal rule the device plays back a voice generated from nothing, which will not
be Doris. The rule counts names and cannot see that two names are one person.

Not overridden, because it is a story decision. Logged in
`outputs/equal_shares/runtime/agent_questions.md`. A documented, empty
`VOICE_ALIASES` hook in the classifier applies it in one line if wanted:
`{"Doris recording": "Doris"}` routes `22B` to ref2va carrying Doris's master.

## Verified after this change

Backup of the previous prompt set kept at
`outputs/equal_shares/prompts_native_r2v.BACKUP_before_oneoff_rule/`.

- 124/124 regenerated prompts still start `subject_definitions:`
- `<Audio N>` numbering is contiguous from 1 in **every** prompt
- tag count equals the recurring-speaker count on **all 78** dialogue clips
- **no** one-off speaker appears in any `<Audio N>` declaration anywhere
- the 4 fl2va clips contain **no** `<Audio N>` at all
- exactly **7** prompts changed — `00D2`, `01B`, `20B`, `22B`, `27E`, `28C`, `30B`
- **no dialogue text altered** in any of the 124, diffed against the backup

## Still unverified

- **No render.** The fl2va routing has not been executed by the pipeline; the
  evidence for it is one hand-made take.
- Whether dropping the `<Audio N>` declarations from `01B` changes its result —
  `17.mp4` was rendered *with* those declarations present and unwired.
*(That gap is now closed — see the addendum.)*

---

# Addendum — the renderer now routes it, and two more faults surfaced

## The routing is wired, not just planned

`work/render_audio_pass.py` previously built a **ref2va graph for every clip**.
Left alone, `01B`, `20B`, `22B` and `30B` would have gone through
`MiniMaxH3ReferenceToVideo` carrying **zero references** — a graph shape nothing
in this project has ever validated.

| File | Change |
|---|---|
| `render_audio_pass.py` `clip_list()` | Loads `voice_requirements.json`, refuses to run without it, tags each row `path`/`node`, and **filters staged references down to recurring speakers**. |
| `render_audio_pass.py` `build_workflow()` | Branches: an fl2va-routed clip builds `MiniMaxH3ImageToVideo` with no reference sockets and returns early. Raises if a clip is routed fl2va but references were staged anyway. |
| `render_single_pass.py` `build_fl2va_workflow()` | Gained `last_frame`. |

## Fault: one-off references were still being staged

The renderer read its references from `audio_pass_config_omni_v1.json`, which
still lists provisional masters for one-off characters. Measured: **references
for 8 one-off characters across 7 clips** would have been wired.

```
00D2  Male Visitor Two          20B   Congregation member
01B   Wealthy commuter,         22B   Doris recording
      Unhoused man              27E   Council member
28C   Crew lead                 30B   Aid worker
```

Each was burning one of H3's three audio slots to condition a voice with nothing
to match. Now filtered at source.

## Fault: `build_fl2va_workflow` silently dropped the closing anchor

It wired `first_frame` only. The proven fl2va graph — `17.mp4`, which is `01B` —
wires **both** `first_frame` and `last_frame`. Any fl2va clip with a closing
boundary image would have lost it without warning. Added.

## Verified after this change

Against the renderer's real `clip_list()` and `build_workflow()`, and diffed
against the proven `17.mp4` graph:

- the renderer routes exactly `01B`, `20B`, `22B`, `30B` to fl2va
- those rows carry zero voice references
- staged references equal the classifier's recurring speakers on **all 78**
  dialogue clips
- `01B` builds a `MiniMaxH3ImageToVideo` node with **no** `ref_audios` or
  `ref_images` sockets
- its UNet (`minimax_h3_fl2va_pruned_int8_convrot`) and megapixels (0.2) **match
  the proven 17.mp4 render**
- `27E` still builds ref2va with exactly two audio sockets

## Still unverified

- **No render.** The routing is proven correct in graph shape against `17.mp4`;
  it has not been executed by the pipeline.
- Whether dropping the unwired `<Audio N>` declarations from `01B`'s prompt
  changes its output — `17.mp4` was rendered with them present.
- The fl2va path has no `--check` equivalent of the audio gate; validation of
  those four clips is the same mechanical + ear process as everything else.
