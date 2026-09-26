# No repetition in prompts — rule and the bug that produced it

Recorded 2026-08-10 after a live observation during manual ComfyUI testing.

## The observation

Testing the first clip by hand, the speaker direction *"Narrator, measured Twilight-Zone-like cadence"* appeared **twice** in the prompt that reached the model. The suspicion was that the repetition itself confused MiniMax H3.

That suspicion checks out, and the underlying cause is structural rather than a one-off typo. It affects most of the film.

## The rule

**Never state the same instruction twice in a prompt. This applies most strictly to the dialogue timing section.**

A repeated instruction is not emphasis. The model has to reconcile two copies of the same directive, and when the copies differ even slightly — different wording, different scope, different tense — it has to guess which one governs. Repeating a spoken line is worse still: the model can read it as the line being said twice.

Say each thing once, in the section that owns it:

| Information | Belongs in | Never repeat in |
|---|---|---|
| Who speaks, and the exact words | `DIALOGUE TIMING` | anywhere else |
| Tone and delivery ("calm", "measured cadence") | `DIALOGUE TIMING`, attached to the line | the shot list |
| Physical staging ("looking at Kent", "turning to Avery") | `SHOT LIST` | the dialogue block |
| Identity features | `IDENTITY` | the action text |
| Cast count | `CAST` | the prohibitions |

Physical staging in the shot list and delivery in the dialogue block are **not** repetition — they are different facts about the same beat. Stating "Faith White speaks, looking at Kent" in the shot list and "Faith White, calm: '…'" in the dialogue block is correct. Stating "Faith White speaks, calm, looking at Kent" in both is not.

## The structural bug behind it

`outputs/minimax_story_runner.py` line 305:

```python
h3_inputs["prompt"] = prompt + "\n\n" + strict_audio_prompt(audio_scene)
```

The prompt that reaches the model is **not** the `prompt` field in `story_config.json`. The runner appends an AUDIO LOCK block built by `strict_audio_prompt()` in `dialogue_validator.py`, and that block restates every line of dialogue verbatim:

> AUDIO LOCK (overrides every earlier audio instruction): No music, song, melody, score… From 1s to 14s, the named speaker says exactly once in clear intelligible American English: "…"

Meanwhile 121 of the 124 stored prompts already contain their own `Dialogue timing:` block carrying the same lines.

**Measured across the config: 73 of the 78 clips that have dialogue send the spoken line to the model twice.** Once in the body, once in the appended AUDIO LOCK.

That is very likely a contributor to the invented and garbled speech that dominated the opening sequence's retries — the model was being handed each line twice and told the second copy overrides the first.

### Two clips actively contradict themselves

`00A` and one other say in the body:

> Dialogue is added in post-production; no one vocalizes in this render. Quiet room tone only.

and then receive an appended AUDIO LOCK instructing the narrator to speak the line. The body says silence, the suffix says speak, and the suffix claims to override. The model cannot satisfy both.

`00A` is the film's opening shot. It took seven attempts.

### One thing the pipeline gets right

`expected_dialogue()` correctly strips the stage direction and passes only the quoted words into the AUDIO LOCK, so the model is never asked to *say* "Narrator, measured Twilight-Zone-like cadence". The stage direction reaches it as context in the body, which is correct. The duplication is of the quoted line, not the direction.

## Fixes applied

The optimized prompts on the Desktop now come in two variants, because the correct text depends on how the prompt is delivered:

- **`optimized_prompt`** — for pasting into ComfyUI by hand. Dialogue appears once, in `DIALOGUE TIMING`. Nothing appends an AUDIO LOCK in this path, so the line has to be present.
- **`optimized_prompt_for_runner`** — for going back into `story_config.json`. The quoted line is **omitted**; the dialogue block names the speaker and the window and defers to the audio lock. The runner then supplies the line exactly once.

Within both variants, tone and delivery now appear only in the dialogue block, and the shot list carries physical staging only.

## Fixes still outstanding in the live config

These are in `story_config.json` and the runner, and have not been changed:

1. **73 clips still double their dialogue** when rendered through `minimax_story_runner.py`. Either strip the `Dialogue timing:` block from the stored prompts, or stop `strict_audio_prompt()` restating lines that the body already carries. Stripping the stored block is the smaller change and keeps the audio lock as the single source of truth.
2. **`00A` and its twin still contradict themselves.** Decide whether those clips speak or are silent, and make the body agree with the audio lock.
3. **`AUDIO LOCK (overrides every earlier audio instruction)`** is itself an admission that the prompt contains conflicting audio direction. Once the duplication is removed, that parenthetical should go — nothing should need overriding.

## Check before shipping any prompt

- Does any sentence appear twice?
- Does any spoken line appear outside `DIALOGUE TIMING`?
- Does any tonal direction appear outside `DIALOGUE TIMING`?
- After the runner appends its AUDIO LOCK, is anything stated twice?
- Does any instruction contradict another?

The last two require looking at the **final** prompt, not the stored one. To see exactly what the model receives:

```python
import json, sys
sys.path.insert(0, "outputs")
from dialogue_validator import strict_audio_prompt
clip = next(c for c in json.load(open("outputs/equal_shares/story_config.json"))["clips"] if c["id"] == "00A")
print(clip["prompt"] + "\n\n" + strict_audio_prompt(clip))
```
