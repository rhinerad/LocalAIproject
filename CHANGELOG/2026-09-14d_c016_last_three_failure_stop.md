# 2026-09-14d — C016 last-frame bounded stop

## Outcome

C016 start passed after its hand-only POV recovery. C016 last is paused after
three bounded failures for this frame, with all evidence retained and no video
started.

1. The first owned ComfyUI backend launch remained alive but never bound its
   loopback port, then reached the 240-second startup deadline. Its process and
   log record remain in the attempt evidence.
2. The second rendered candidate failed the exact VLM review: it did not
   establish the requested Backrooms/analog frame and a generic full-person
   comparison was inapplicable to the floor POV.
3. The third rendered candidate also failed exact VLM review for missing the
   required Backrooms/analog composition.

## Stop condition

The operator-set three-failure limit is reached. The production runner is not
running. Do not start a third seed or a video. Resume only with a new,
reviewed C016-last recovery policy that defines the static floor-POV target and
uses the exact VLM gate; preserve the two generated candidates and all startup
receipts.

## Earlier C016 start repair

The C016 start hand-only candidate passed after its narrow QA fixes. The donor
is checksum-pinned at
`work/runtime/identity_donors/c016_start/c016_start_floor_hand_backrooms_imagegen_v1.png`
with SHA-256
`fc7893767a312afb317d6176833899fb990390e3ebf3c08a1ad0772674da6e5d`.

## Verification

The C016 start recovery changes passed 120 focused tests. No model weight,
predictor, router, or video workflow was changed.
