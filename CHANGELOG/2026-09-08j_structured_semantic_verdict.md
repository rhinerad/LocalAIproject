# 2026-09-08j — Structured semantic verdict gate

Added `semantic_verdict_from_caption()` to the media accuracy gate. Semantic
approval now requires a boolean JSON verdict, rationale, observed-evidence
object, and an exact Qwen2.5-VL Caption V4 / llama.cpp identity; plain captions,
stub models, malformed JSON, and rejected verdicts fail closed. Automatic
prompt/process adaptation remains a future TODO after this gate is proven on
real media.

Verification: with `PYTHONPATH=local_agent`,
`python -m unittest test_media_accuracy_gate -q` — 3 passed; production
integrity suite — 21 passed.
