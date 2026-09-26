# Roadmap: what's left to get the ComfyUI story pipeline done

Written 2026-09-26, from direct repo verification (changelog entries, TODO.md, code reads) — not from any session's narration. "Done" here means two things the operator has asked for: (1) the Backrooms Sitcom Audition pipeline runs end to end reliably, and (2) the agent is genuinely versatile — can take any video request and either do it or ask a real clarifying question, instead of guessing or silently picking the wrong tool.

Organized so the blocking layer is first: nothing below Section A can be handed to Fable as a finished decision until the operator actually decides it.

## Section A — Operator decisions, not engineering tasks

These are the items where more investigation won't produce an answer; a person has to choose.

1. **Motion-transfer identity quality: is the current no-download result good enough?** As of `2026-09-26a`, the reference-video-motion-transfer proof of concept renders upright, follows the reference motion, and keeps the right character identity via a face-crop + IP-Adapter mask + a per-frame face-detail pass. Faces stay soft (~60px wide at the current 768×448 render size — a resolution limit, not an identity bug anymore). Three paths forward, all named in `TODO.md`'s last section: accept the current installed-only quality, approve FaceID weights, or approve the ~17GB Wan 2.2 Animate download (or the smaller ~1.2GB Wan 2.1 VACE module). No tool has downloaded or installed anything without your say-so so far — that gate has held.
2. **Backrooms motion-keyword table: relax it or not?** Flagged since `2026-09-25i`: a specific prompt row ("gradually moves … panning") was rejected by the current mechanical gate, but the clip it would have produced passes human review and scores 0.80 from the judge offline. Still undecided in `TODO.md` line 92.
3. **Still-QA: should it ever check prompt-content match, not just face/continuity?** This was raised in the original still-QA wiring handoff (the missing-skateboard case) and, as far as I can find, was never actually decided — it doesn't appear anywhere in TODO.md or any changelog since. Worth deciding before more work goes into the still-QA layer: keep it narrow (current behavior) or add the heavier CLIP/WD14/Caption-V4 check that already exists for video submission.
4. **D02 `614e`: accept the known judge miss, or invest more in the camera-rig check?** The judge's camera-rig/operator-visible check (`2026-09-25g`) still misses this one clip — the VLM reads the brief's own words ("FPV drone") and never treats the aircraft as a visible object no matter how the question is phrased. This was explicitly left open rather than force-fixed. Worth a real decision: accept it as a known limitation, or scope a follow-up investigation.

## Section B — Ready to hand to Fable now

These don't need a decision first; they're scoped and can go out as soon as you're ready (I'd send them one at a time, or wait for whatever's currently running on the machine to finish — there was an active git lock and GPU-gate churn as of last check).

5. **MiniMax-default / Wan-fallback router policy** — the prompt I just wrote you (effort: `high`). Fixes the GVD router picking Wan over MiniMax with no stated reason. Not yet sent to a Fable session as of this writing.
6. **Backrooms motion-keyword relaxation + stale TODO cleanup** — sent earlier, not yet picked up by a session (blocked on decision #2 above being settled first, if you want the relaxation half to actually do something; the cleanup half doesn't need to wait).
7. **GVD-router "ask, don't guess" verification** — sent earlier as Part 1 of the GVD-router prompt, still unconfirmed. I checked again just now: `NEEDS_MANIFEST_REVIEW` and its sibling statuses exist only inside `gvd_tool_router/{planner,router,schema}.py` — there is still no evidence they reach `agent.py` or the operator's chat as a real question. This is the literal mechanism behind your "ask instead of guessing" requirement, so it's worth prioritizing this one over new capability work.

## Section C — Turn the motion-transfer proof of concept into a real, reusable tool

This is real, working evidence (`2026-09-25s` through `2026-09-26a`) but it is exactly that — a proof of concept run by hand with one-off scripts against one specific benign clip and one specific character. Per `2026-09-26a`'s own "not done" list, none of this exists yet:

8. A pinned, reusable ComfyUI API template (today it's a hand-tuned runner script with CLI flags, not a graph the router can invoke).
9. A measured GVD VRAM profile and promotion through `apply_profile.py` (the implementation stays `disabled` in `catalog_seed.py` on purpose until this happens).
10. Generalizing the two clip-specific hacks: face selection is currently hardcoded to "leftmost face in frame" and the IP-Adapter mask is a static left-half rectangle — both fit only the one proof-of-concept clip. A real template needs selection driven by the character's pose/mask per frame.
11. The actual `render_video_from_reference` chat tool (background job, preflight, owned backend, job-status polling, sha256-verified manifest, no success claim without evidence — matching `render_story_image`'s pattern). Nothing chat-callable exists yet; this is still a developer script.

## Section D — Broader versatility backlog (the "any prompt" goal)

From the GVD tool router capability audit (`2026-09-22i`, re-confirmed unchanged as of this check):

12. **Promote already-installed-but-inactive node packs** with real measured VRAM profiles: IPAdapter, ControlNet Aux, VideoHelperSuite, ProPainter, Wan, LTX, MiniMax H3 variants, HF-Flux. (ComfyUI-Advanced-ControlNet was added to this list and *is* now installed, per `2026-09-25u` — one down.)
13. **Decide on and, if approved, install the missing-entirely packages**: StoryDiffusion, AnimateDiff/Fizz, F5-TTS Comfy pack, MuseTalk, SAM2, TiledDiffusion, LongCat — each is a capability gap (identity-consistent narrative scenes, montage/morph, dialogue TTS, lipsync, segmentation, tiled upscaling) with no implementation at all right now.
14. Re-run the M3 family scan once B.7 and D.12 have moved, to get a fresh, accurate capability inventory rather than relying on the Sept 22 snapshot.

## Section E — Judge/quality loose ends (lower priority, can run independently)

15. `24q`/`24r`'s original open items were resolved as of `25o`, except D02 `614e` (Section A.4) — no further action needed there beyond that decision.
16. Nothing else outstanding in the judge/MIPRO stack as of `2026-09-25o`'s cold-prefill rebaseline; this section is effectively caught up pending A.4.

## Suggested order

A.1–A.4 first — they're free (no engineering time) and several of the "ready" items in Section B are more useful once decided. Then B.7 (ask-don't-guess verification) ahead of B.5/B.6, since it's the mechanism the whole versatility goal depends on and it's already been sitting unconfirmed the longest. Section C is the highest-value chunk of remaining work but also the largest — expect it to be multiple Fable sessions, not one prompt. Section D is real but lower urgency than C: promoting an existing capability is cheaper than building the one you're actually using right now (motion transfer).
