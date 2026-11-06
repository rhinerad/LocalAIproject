# 2026-08-30 — Bamboo-DPO isolated mechanical gate authorized

The operator approved the next isolated candidate gate after the byte-verified
Q4 runtime intake. The allowed operation is one bounded native `main.exe`
raw-completion smoke run against the exact locked Bamboo-DPO Q4 PowerInfer
GGUF and its 32 adjacent activation files.

This authorization does not permit a server, registry entry, proxy, router or
picker change, a render, ComfyUI, training, conversion, or a substitute model.
The runner records the exact model SHA-256, output logs, GPU before/after state,
and exit status under the candidate's `validation/` directory.

The first preflight invocation exposed a runner-only stale-exit-code defect in
the GPU status check and exited before model launch. The check was corrected to
validate the actual status line rather than an inherited native-command code;
the candidate, GPU, and runtime receipt were untouched.

The second preflight invocation also exited before model load: Windows split a
space-containing prompt while forwarding it through `Start-Process`. The runner
now invokes `main.exe` with PowerShell's native argument array, so the bounded
raw-completion prompt is forwarded as one argument. This is a runner repair,
not a model or candidate change.

The first actual bounded run exited cleanly and produced text, but its native
log showed that the solver called the unrelated system Python and therefore
failed to generate the sparse GPU split. That is a mechanical **failure**, not
a pass. The gate now requires confirmed sparse load, CUDA use, a successful
split, and non-zero FFN GPU offload. It scopes the matching PowerInfer venv on
`PATH` and `PYTHONPATH` only for the child process; no persistent environment,
model artifact, or route is changed.
