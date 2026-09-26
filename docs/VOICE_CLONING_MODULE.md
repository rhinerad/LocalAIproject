# Voice cloning and approval gate

> **Legacy design; prohibited for the current workflow as of 2026-08-14.** The
> VOX/filler and external clone-API approach below is preserved only as design
> history. Do not run `work/voice_manager.py`. Current character references come
> only from first qualifying actual story soundtracks generated locally by
> non-Turbo MiniMax H3 at 0.2 MP and 20 steps. Use
> `work/render_audio_pass.py --bootstrap-missing-voices` and
> `outputs/equal_shares/story_voice_bootstrap_plan.json`.

`work/voice_manager.py` — plan, extract, gate, clone. `work/voice_review.ps1` — listen and approve.

Everything below the API section was executed against the real project. The MiniMax API
calls were **not** executed — no key in this environment — so treat those two functions as
reviewed-but-untested and check the response shapes on your first live call.

---

## The constraint that shapes the design

The MiniMax clone endpoint needs a reference sample of **10 seconds minimum**, 5 minutes
maximum, 20 MB maximum, in mp3/m4a/wav.

Measured against this script, by longest single take:

| | characters |
|---|---|
| One take already clears 10 s | **6** — Narrator, Kent, Doris, Avery, Terminal voice, Doris recording |
| No take clears 10 s | **12** |

Of those twelve, eight have less than 10 seconds of dialogue *in the entire film*. Male
Visitor Two has 2.0 s. Crew lead 2.0 s. Aid worker and Council member 3.0 s.

**A sample must come from a single take.** H3 re-derives a voice on every clip — that is
the drift you have been hearing. Concatenating two takes to reach 10 seconds would splice
two different-sounding performances together and teach the clone an average of both, which
is the opposite of what cloning is for.

So the twelve get a **VOX clip**: a throwaway 15-second render of that character speaking
filler, using their own approved anchor frame, existing only to harvest a voice. It is
never part of the edit.

## Render order

`plan` writes `outputs/equal_shares/runtime/render_priority.json` in two phases:

**Phase 1 — 12 voice sample clips**
`VOX_MALE_VISITOR_ONE  VOX_MALE_VISITOR_TWO  VOX_WEALTHY_COMMUTER  VOX_UNHOUSED_MAN
VOX_FAITH_WHITE  VOX_RYANN_SALLY  VOX_VOLUNTEER  VOX_HOUSING_REPRESENTATIVE
VOX_CONGREGATION_MEMBER  VOX_COUNCIL_MEMBER  VOX_CREW_LEAD  VOX_AID_WORKER`

**Phase 2 — 6 story clips whose audio doubles as a sample**
`00A  11B  13B  14D  22B  25A`

Eighteen renders and every character has a voice. Note phase 2 picks the *longest* take
per character, not the first — Kent's sample comes from `14D` (the driving shot, 15 s of
continuous speech), not from `02B` where he has 3.5 s.

**`render_queue_owner.json` is deliberately untouched.** That file is the GPU mutex —
the one lock preventing two backends. Queue ordering is a different concern and lives in
its own file. `render_until_complete.py` should read `render_priority.json` and take those
clips first; that wiring is the one integration step left to you.

`voice_sample_clips.json` holds the full spec for the twelve VOX clips — id, anchor,
duration, frame count already rounded to 5 mod 17, seed, dialogue and a complete prompt
following the house style. They are single-anchor by design; a closing frame would force
the take to arrive at a pose, which fights thirteen seconds of talking.

## `voice_approval_gate.json`

```json
{
  "schema_version": 1,
  "generated_at": "2026-08-11T21:24:54",
  "api_minimum_seconds": 10.0,
  "gate_open": false,
  "policy": "Downstream dialogue generation is blocked until every character here is approved...",
  "characters": {
    "Narrator": {
      "character": "Narrator",
      "first_speaking_clip": "00A",
      "first_appearance_seconds": 13.0,
      "strategy": "single_clip",
      "source_clips": ["00A"],
      "planned_sample_seconds": 13.0,
      "total_dialogue_seconds": 168.6,
      "sample_path": "outputs/equal_shares/voices/narrator/reference_sample.wav",
      "sample_seconds": null,
      "extracted_at": null,
      "approved": false,
      "needs_reroll": false,
      "status": "pending",
      "fallback_voice": "am_onyx.pt",
      "reviewer_note": "",
      "reviewed_at": null,
      "cloned_voice_id": null
    }
  }
}
```

`strategy` is `single_clip` or `sample_clip_required`. `status` moves
`pending → approved`, or `pending → needs_reroll` and back. `fallback_voice` is the Kokoro
voice already assigned to that character, which stays available if cloning is abandoned.

The gate opens only when every character is `approved` with no `needs_reroll`. Rewriting
the file by hand works — set `approved: true` — but the CLI keeps `gate_open` and
`reviewed_at` consistent.

## Workflow

```powershell
$Py = "A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe"

# 1. plan: writes the VOX specs, the priority queue and the gate
& $Py work\voice_manager.py plan

# 2. render phase 1 and phase 2 (supervisor or by hand), then review them visually

# 3. extract reference samples from the rendered clips
.\work\voice_review.ps1 -Extract

# 4. LISTEN and decide - this is the human gate
.\work\voice_review.ps1 -Listen

# 5. anything unusable
.\work\voice_review.ps1 -Reroll "Kent" -Reason "too nasal, re-render 14D"

# 6. confirm before letting anything downstream run
& $Py work\voice_manager.py gate      # exit 0 open, 1 closed
```

`-Listen` plays each sample through `System.Media.SoundPlayer` and prompts
approve / re-roll / skip / quit per character. Extraction runs two-pass EBU R128
loudness normalisation, a 70 Hz high-pass and light denoise, then writes mono 44.1 kHz
PCM — H3's output level varies between clips and the clone endpoint is level-sensitive.

## Blocking downstream work

```python
from voice_manager import check_approval_gate

is_open, reasons = check_approval_gate()
if not is_open:
    raise SystemExit("voice gate closed:\n  " + "\n  ".join(reasons))
```

`check_approval_gate()` is read-only and never mutates state.

## MiniMax API integration

Three calls: upload the sample for a `file_id`, clone it into a `voice_id`, then
synthesise each line with that `voice_id`.

```python
file_id  = upload_reference("outputs/equal_shares/voices/narrator/reference_sample.wav")
voice_id = clone_voice("Narrator")          # POST /v1/voice_clone, records voice_id on the gate
synthesize_line("In a world of total equality...", voice_id,
                "outputs/equal_shares/voices/narrator/lines/00A_01.wav")
```

`clone_voice()` refuses to run on an unapproved character — the gate is enforced in code,
not just documented. The key comes from `MINIMAX_API_KEY` in the environment and is never
written to disk; `MINIMAX_GROUP_ID` is passed to upload if set.

`upload_reference()` validates the 10 s floor, the 5 minute ceiling and the 20 MB limit
before spending a call.

**Unverified:** the exact JSON envelope of the upload and clone responses, and whether
`t2a_v2` returns hex-encoded audio in `data.audio` for your account tier. Those are the
first things to check on a live call. Endpoints and the model name `speech-2.6-hd` come
from MiniMax's published docs.

## Replacing audio in the finished clips

Once voices are cloned and lines synthesised, `work/audio_decisions.py` already builds the
final timeline — mark clips `replace` and point its Kokoro source at the cloned line files
instead. The two modules are designed to meet there rather than duplicating the mixing
logic.

## What is left to wire

1. **`render_until_complete.py` should read `render_priority.json`** and take those clips
   before its normal sequence order. Nothing else consumes that file yet.
2. **The VOX clips need a render path.** They are not in `story_config.json` on purpose —
   adding them would put them in the edit and the completion audit. Either run them by hand
   through ComfyUI using the prompts in `voice_sample_clips.json`, or give the runner a
   `--spec` flag that accepts an alternate clip list writing to `story/VOX_*/`.
3. **Decide what happens to the Kokoro timeline** once voices are cloned. Both paths can
   coexist per clip through `audio_decisions.py`.
