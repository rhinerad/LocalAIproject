# 2026-09-08 — Camera visibility invariant

Updated the reviewed Backrooms prompt adapter so the camcorder is always the
viewpoint and its body, lens, tripod, and operator are explicitly outside the
frame for both stills and videos. Added a positive-camera request rejection to
the deterministic media accuracy gate. Existing negative prompts already reject
visible recording equipment; this makes the rule explicit in effective prompts
and validation as well.
