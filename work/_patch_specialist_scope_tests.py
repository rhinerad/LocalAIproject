from pathlib import Path

p = Path("local_agent/test_native_tool_calling.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
needle = "    def test_stale_h3_render_tool_is_blocked_on_unrelated_turn(self):\n"
idx = None
for i, line in enumerate(lines):
    if line == needle:
        idx = i
        break
if idx is None:
    raise SystemExit("needle not found")

new_test = r'''    def test_confirmation_proceed_after_image_plan_allows_render_story_image(self):
        # Sibling of 2026-09-06f reply-text fix: after plan_story_image the
        # operator often just says "proceed". That must allowlist
        # render_story_image via _pending_specialist_continuation, not trip
        # "stale specialist-project tool selection blocked".
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {
                "name": "render_story_image",
                "arguments": {
                    "story": "vhs_liminal_space_story",
                    "prompt": "VHS skatepark still",
                    "model_profile": "realpro_flux",
                }}}])],
            ["Started the Flux still render; polling story_image_job_status next."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        history = [
            {"role": "user", "content": "Generate these photos using flux --- CLIP 1 --- "
                                         "START FRAME: a skater at a park."},
            {"role": "assistant",
             "content": "I have prepared an inspectable RealVisXL still-image graph "
                        "for the general story or storyboard \"vhs_liminal_space_story\" "
                        "using Flux. Now, I will proceed to generate the images.",
             "tool_evidence": [{
                 "tool": "plan_story_image",
                 "outcome": "result",
                 "summary": '{"planned": true, "model_profile": "realpro_flux", '
                            '"story": "vhs_liminal_space_story"}',
             }]},
            {"role": "user", "content": "proceed"},
        ]
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call",
                          return_value=json.dumps({
                              "started": True,
                              "story": "vhs_liminal_space_story",
                              "pid": 4242,
                              "ownership": "owned",
                          })) as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_called()
        self.assertEqual("render_story_image", call.call_args.args[0])
        self.assertFalse(any(
            k == "tool_result" and "stale specialist-project tool selection blocked" in p
            for k, p in events))
        self.assertFalse(any(k == "note" and "blocked unrelated specialist-project tool" in p
                             for k, p in events))
        self.assertIn("4242", reply)

'''
lines.insert(idx, new_test)
p.write_text("".join(lines), encoding="utf-8")
print("inserted at", idx)
