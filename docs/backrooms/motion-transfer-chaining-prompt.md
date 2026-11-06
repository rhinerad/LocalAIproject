Project: A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
(start in that folder; local_agent/ is the offline Ollama chat app). Read
CLAUDE.md for the binding safety/evidence rules first, then run
`python scripts/write_handoff_status.py` and read HANDOFF_STATUS.md. Multiple
agents touch this repo daily: re-read any file before editing it, use
exact-anchor edit scripts, preserve each file's line endings (agent.py /
server.py / remote_security.py are CRLF; tools.py / media_*.py /
gvd_tool_router/*.py / motion_transfer.py / motion_transfer_render.py /
motion_transfer_masks.py / motion_transfer_faces.py are LF), and take a
changelog id only with `python scripts/next_changelog_id.py` (it claims the
id; call it once per changelog entry — this will likely take more than one).

Read CHANGELOG/2026-09-26{i,j,k}.md in full before starting, and
docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md. Re-verify current state
first — this is an active area, other sessions may have touched it since.

## The problem

`render_video_from_reference` (local_agent/motion_transfer_render.py,
26j/26k) generates the *entire* output as one continuous AnimateDiff job:
a sliding context window (16 frames, 4-frame overlap, pyramid fuse) runs
inside a single ComfyUI graph/sampling pass for the whole requested length.
26k measured this approach's ceiling directly: 180 frames (~15-22s at
8-12fps) needs 29.84 of 30.9 GB system RAM on this machine, and a 70-second
clip (≈565 frames) projects to ~3x that — it does not fit as one job here,
full stop. The fix applied in 26k was to raise the measured frame cap and
add a RAM-refusal guard. That's honest engineering, but it doesn't address
the actual limitation: this tool cannot produce a long clip *at all* on this
hardware, because it insists on doing the whole thing in one job.

This is inconsistent with how the rest of this pipeline works.
dspy_orchestrator.py / batch_run_backrooms_gvd.py generate MiniMax clips in
~8-second segments and chain them: each clip's last frame becomes the next
clip's first-frame condition (MiniMaxH3ImageToVideo.first_frame /
.last_frame, per the existing FL2VA wiring). That pattern needs no more
memory per segment no matter how long the final output is, because each
segment is an independent job. The operator's own words: "we're supposed to
be doing chunk clips where it's like 10 second generations then taking the
last frame of that generation and putting it as the first frame of the next
generation" — that's exactly the MiniMax pattern, and it's the right fix
for the RAM ceiling 26k just hit.

There's a second, independent benefit if this works: 26k's own "not done"
list flags that lighting/background drift *within* a single multi-window
job is already unsolved ("the hallway's lighting and colour drift across
windows, warm orange <-> cool green-grey"). A clean last-frame reseed
between segments carries the exact prior frame's lighting/background/pose
forward as a real image, which plausibly holds a scene together better than
AnimateDiff's internal window-blending does. Verify this against real
output, don't assume it.

## What is NOT yet known — investigate before committing to an approach

AnimateDiff is fundamentally a text-to-video model with a motion module
added on top of an SDXL base; unlike MiniMax, it was not trained with an
explicit first/last-frame video-continuation mode. "Start exactly from this
image" on AnimateDiff is typically done via an img2img-style partial-noise
init on the first latent, or an IP-Adapter/reference trick, not a native
conditioning input. Before building segment chaining, determine:

1. Can the current graph (motion_transfer_render.py's build_graph, or the
   pinned templates in local_agent/graphs/motion_transfer_animatediff_*)
   actually be seeded from a real prior frame with high fidelity — i.e. does
   segment N+1 visibly and reliably continue from segment N's last frame
   (same room, same lighting, same character pose continuity), or does the
   reseed introduce its own visible seam/drift? Test this directly: render
   two consecutive real segments off the same source clip section, feed
   segment 1's actual last output frame in as segment 2's init, and look at
   the boundary frame-by-frame.
2. What denoise strength / init-latent scheme gives continuity without just
   regenerating the same frame over and over (too low denoise) or losing the
   reseed entirely (too high)? This needs real measurement, not a guess.
3. Whether the identity machinery already built (face crop, IP-Adapter mask,
   FaceID Plus V2, the face-detail pass) still applies per-segment cleanly,
   or needs adjustment when segments are independent jobs instead of one
   continuous context.

If reseeding AnimateDiff from a real frame turns out to be unreliable (visible
seams, identity resets, motion discontinuity), say so plainly with the
evidence and stop — don't ship a chaining scheme that looks like it works in
the changelog but produces worse output than the current single-job
approach. In that case, the honest fallback is documenting that this tool is
bounded to ~180 frames per call until a model with native first/last-frame
conditioning (Wan 2.2 Animate, already downloaded per 26h but unused) is
wired in instead — a separate, larger task, not yours to start here unless
you finish this and have capacity.

## What to build, if the investigation above says it's viable

- A segment-chaining mode in motion_transfer_render.py: split the requested
  output duration into N segments (pick a segment length from what's
  actually measured to work well in your investigation above — the
  operator's example was ~10s, but let real continuity-quality evidence
  decide, not the round number), each one an independent AnimateDiff job
  seeded from the previous segment's actual last rendered frame, walking
  forward through the corresponding span of the *source reference video*
  (each segment tracks a different, sequential slice of the reference clip's
  motion — not the same slice repeated).
- Keep the existing single-job path working and tested for short requests
  (the current 180-frame ceiling is fine for anything that already fits);
  only route to segment-chaining when the requested length exceeds what one
  job can hold, or when the operator asks for a specific chaining behavior.
  Don't rip out what's already shipped and validated (34 + tests in
  test_motion_transfer_render.py, full suite 1754 OK as of 26k).
- The job/manifest shape should stay consistent with render_story_image's
  established pattern (already followed by this tool): background job,
  preflight, owned backend, job-status polling, sha256-verified manifest per
  segment plus a final concatenated/stitched output, no success claim
  without frame-level evidence.
- Update the RAM-guard math: chained segments should each cost roughly the
  same fixed RAM regardless of total requested length (that's the entire
  point) — prove this with a real measured run of at least 3 chained
  segments (~24-30s combined) and confirm peak RAM doesn't scale with
  segment count the way the single-job path did in 26k.
- Tests: a request short enough for one job still uses the single-job path
  unchanged; a request long enough to require chaining produces N segments
  with each one's first frame matching the previous one's last frame
  (compare actual pixel data, not just metadata); RAM stays flat across
  segment count in a chained run; existing single-job tests all still pass.
- Changelog entry(ies) with real measured evidence: the seam-quality
  investigation's findings (with frame comparisons, not just a verdict), the
  chaining implementation, and the RAM-flatness measurement across a real
  multi-segment run.

## Do not

- Do not touch the legacy MiniMax/dspy_orchestrator.py chaining path — it
  already works correctly and isn't part of this task.
- Do not silently drop the single-job path or its existing tests.
- Do not claim chaining "solves" background drift without a real
  frame-by-frame comparison against a chained run; it's a plausible
  improvement, not a given.
