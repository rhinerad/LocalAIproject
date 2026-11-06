# 2026-08-31 — Prior-chat retrieval relevance and contamination fix

## Incident

A new general chat asked, “im trying to test how fast you can do things,” but
received an unrelated response about Unity asset files. The chat-retrieval
feature had matched generic words such as `how`, `can`, and `you`, then injected
old assistant output from an unrelated game/paywall conversation into the new
prompt.

## Fix

`local_agent/chat_retrieval.py` now removes generic conversational words before
scoring, requires two meaningful terms in both the new request and the prior
operator topic, and injects prior **operator** messages only—never old assistant
responses or tool output. It continues to omit Equal Shares material from an
unscoped general chat.

`local_agent/agent.py` labels the injected text as bounded prior operator topics,
not instructions, claims, tool actions, or safety decisions.

The exact failing request now retrieves no prior chat. The regression suite covers
generic-query refusal, topic-specific retrieval, project scoping, and non-injection
of old unsafe assistant output. No model was loaded, no render/ComfyUI action
occurred, and no chat record was deleted or changed.

## Fast casual-turn path

The same incident exposed excessive first-token latency on the four-thread CPU
fallback: an ordinary speed check still carried the full 43-tool schema set and
the long specialist/sensory rules. A very narrow lightweight path now applies
only to a new or near-empty **general** chat that is a greeting or an explicit
speed test and contains no path, URL, file, action, media, research, or
permission request. It sends a 234-character no-tool prompt and skips optional
prefetch/state bookkeeping. Every substantive request retains the complete
rules, retrieval, state tracking, and native-tool schemas.

The server/launcher revision is now `2026-08-31-relevance-r65`, so the normal
desktop launcher replaces an earlier local-agent instance rather than treating
it as current code.

## Live verification

With ComfyUI still owning port 8188, the restarted local agent reported
`cpu_server_up: true` and selected `huihui_ai/qwen3-abliterated:8b` on the
CPU-only listener. A new general-chat speed-check returned the relevant reply
“Got it! How can I assist you quickly?” with no unrelated-chat content. The
fast-path request reached Ollama with 75 prompt tokens, versus 8,848 tokens for
the equivalent pre-fix live check. This verification used CPU only; no GPU model
was loaded and the existing ComfyUI process was not stopped or altered.
