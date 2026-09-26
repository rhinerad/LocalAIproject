# 2026-09-22f — Local-agent audit fixes

Offline repair of the five findings from the 22 September audit. No models, renders, or production supervisors were started.

## Code execution

`run_code` now starts Python and Node at low integrity inside a one-process job with a memory cap. A child interpreter cannot be created, Node cannot write outside the run directory, and parent secrets are not copied into the child environment. `allow_network` is refused. Python sockets stay disabled in-process. This Node build has no network permission flag, so a JavaScript process can still open a socket.

## Local HTTP

Mutation routes require a local Host, a local Origin, `application/json`, and the per-session `la_csrf` cookie plus `X-CSRF-Token`. Read routes reject a non-local Host. The desktop page attaches the token on state-changing fetches.

## Phone grants

Remote callers are allowlisted. Every registered tool is either a default read/sensory tool or an explicit grant. `generate_still`, the other live GVD execute tools, and `run_prompt_pack_production` require a grant. Dispatch drops caller-supplied `__*` fields and binds conversation id and remote render identity from the trusted context. A forged identity cannot skip the desktop GPU gate.

## GVD submit and chats

`submit_stage` treats a missing HTTP transport as the default client. An unexpected submit error marks the attempt `FAILED` instead of leaving it `SUBMITTING`. Conversation read/modify/write holds a per-conversation lock across threads and processes.
