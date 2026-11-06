# 2026-09-08l — C001 live semantic QA evidence

Ran one controlled review on the existing C001 start still using the exact
Qwen2.5-VL Caption V4 Q4_K_M GGUF and llama.cpp runtime. The VLM returned a
structured verdict with `pass: false`: camera body and tripod were visible in
the foreground, directly violating the no-visible-camera requirement. It also
observed a man standing with arms crossed in an indoor room. The image hash was
recorded in the worker output; the temporary VLM was released after the check.

This confirms the semantic gate catches the failure that mechanical checks missed.
No image was overwritten or regenerated.
