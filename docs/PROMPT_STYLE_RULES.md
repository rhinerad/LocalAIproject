# Prompt style rules

Derived from live testing on 2026-08-10, including two failures found by hand. Apply to
every clip. These sit on top of `PROMPT_REPETITION_RULE.md`, which still holds.

## 1. Quotation marks mean speech. Nothing else may be quoted.

**This is the most important rule on the page, and breaking it makes characters speak at
random.**

The model treats a quoted string as a line to be spoken and assigns it to the nearest
named person. A shot list beat like:

```
[1-2.5 s] "If there's one chair in a room" - Male Visitor One steps through the doorway
```

reads to the model as *Visitor One says "If there's one chair in a room."* He then speaks
narration that was only ever meant to time the picture.

It is made worse by the speech-lock sentence, which tells the model that quoted text is
what gets spoken. Once that is established, any quotation mark anywhere is an instruction.

**Narration is never quoted.** Write it plain, with a label:

```
[1-2.5 s] Narration over, off screen: If there's one chair in a room. Male Visitor One
steps through the doorway at screen-right...
```

And open the shot list with:

> Narration timing below is for pacing only. The Narrator is off screen. Nobody visible in
> frame speaks the narration, and nobody's lips move to it.

**The narration does not need to be spoken at all.** Every H3 audio track is discarded and
the real narration is added in post. Narration text exists in the prompt only to time the
visuals, so there is no reason to let the model try to perform it.

## 2. Never put two quoted strings in one beat.

A beat containing both a quoted narration line and a quoted character line is the worst
case observed. The model has to choose an owner for each and frequently gets both wrong.
One beat, at most one line, with the speaker named immediately before it.

## 3. On-camera dialogue lives in its own block, not scattered through the shot list.

The shot list says *that* someone speaks. A single `DIALOGUE` block says *what*, *when* and
*who*:

```
DIALOGUE
Exactly two lines are spoken on camera in this shot, one each, and nothing else:
[3s-5s] Male Visitor Two, politely insistent: "No, please, I insist."
[5s-7s] Male Visitor One, quietly pressing: "Really, please."
Those are the only words spoken by anyone in frame. The receptionist never speaks. Neither
man speaks outside his own window. Nobody else's lips move at any point.
```

State the count. Name who stays silent. In the shot list, refer to it as "speaks his
assigned line" rather than repeating the words — repeating them is a rule-1 violation and a
repetition violation at once.

## 4. No section may reference a section that does not exist.

The stock trailing line, *"Nobody in frame speaks except where DIALOGUE TIMING assigns a
line,"* becomes nonsense if the dialogue block was renamed or removed. Both hand-edited
clips carried this fault. If you move dialogue, fix every sentence that points at it.

## 5. No blanket denial that contradicts a line you just wrote.

Both hand-edited clips ended with a flourish that cancelled their own dialogue:

- *"The entire check-in is transacted through the form, the stamp and the nod. Nobody speaks
  to anybody."* — while Visitor One says "After you, please."
- *"The whole negotiation is carried by hands, heads and shoulders."* — while both men speak.

Narrow the denial to what is actually true: *"The check-in at the window is transacted
entirely through the form, the stamp and the nod"* is fine, because the window exchange
really is silent.

## 6. `LOOK` describes only what is in this shot.

Several opening clips described *"even television lighting on the Narrator, the room behind
him"* in shots the Narrator is not in. Anything the model is told to light, it may decide
to draw.

## 7. Every beat with a visible face carries a mouth state.

"Mouth closed" or "mouths closed" belongs in the beat, not only in a rule at the bottom.
The model decides what a face is doing at the same moment it decides what the body is
doing. The beat that names the speaker also names who stays silent.

## 8. Counted actions get a number.

"They repeatedly offer the chair" produces either one limp gesture or a blur. "There are
exactly three offer-and-refusal exchanges, no more and no fewer" produces three. Same for
people, props and repetitions of any kind.

## 9. Staging must support its own claims.

An edit that removed the first offer's staging left a later beat asserting *"two offers have
now been made, one each"* when only one had been shown. If a beat counts something, the
beats before it must have shown that many.

## Checklist before sending a prompt

- Every quoted string has a named speaker immediately before it.
- No narration is inside quotation marks.
- No beat contains two quoted strings.
- The dialogue block states how many lines are spoken and who stays silent.
- No sentence refers to a section that is not present.
- No blanket "nobody speaks" while somebody speaks.
- `LOOK`, `SET` and `CAST` describe only people and objects present in this shot.
- Every counted action states its number.
- Any beat that counts prior actions is preceded by that many actions.
