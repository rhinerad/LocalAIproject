# 2026-09-08k — Live semantic QA wiring

The prompt-pack worker now invokes the exact local Qwen2.5-VL Caption V4 GGUF
through the paired llama.cpp runtime after each still render. Its JSON-only
prompt checks subjects, setting, composition, camera visibility, pose, and
continuity. The worker records the model/runtime, verdict, rationale, and image
hash, releases the VLM immediately, and blocks video binding on any failure.

Existing generated stills with `semantic_check: not_run` are deliberately not
reused. No automatic prompt rewriting was added; that remains deferred until
semantic QA has been exercised on real outputs.

Verification: `py_compile` passed; media QA 3 passed; production-integrity 21
passed.
