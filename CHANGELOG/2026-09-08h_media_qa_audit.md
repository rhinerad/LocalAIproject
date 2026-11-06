# 2026-09-08h — Media QA audit and adaptive-failure TODO

Audited the exact still/video QA path. The current checker is deterministic and
fail-closed for approval: it verifies file integrity, dimensions, aspect ratio,
blank output, and prompt invariants, while semantic VLM review remains
`not_run` until the exact Qwen2.5-VL Caption V4 runtime is invoked. The local
VLM wrapper returns model/runtime metadata and separates observations from
inference, but no live semantic verdict was claimed in this audit.

Added a TODO item for future bounded adaptive diagnosis after 3–4 consecutive
failures. That work is intentionally not implemented yet: it must preserve
original evidence, require deterministic revalidation, and avoid changing
neighboring clips or creating unbounded retry loops.
