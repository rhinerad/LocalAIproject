import sys
sys.path.insert(0, "local_agent")
import agent
text = (
    'I have prepared an inspectable RealVisXL still-image graph for the general '
    'story or storyboard "vhs_liminal_space_story" using Flux. Now, I will proceed '
    'to generate the images.'
)
print("req", agent._requests_specialist_project_context(text))
print("offer", bool(agent._SPECIALIST_CONTINUATION_OFFER_RE.search(text)))
h = [{"role": "assistant", "content": text}, {"role": "user", "content": "proceed"}]
print("pending_no_evidence", agent._pending_specialist_continuation(h))
decline = "No render was started. This chat has no complete fenced H3 prompt set to render."
h2 = [{"role": "assistant", "content": decline}, {"role": "user", "content": "continue with powerinfer training"}]
print("pending_decline", agent._pending_specialist_continuation(h2))
