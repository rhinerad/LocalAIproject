# 2026-08-30 — TurboSparse exploratory run paused safely

The first exploratory invocation stopped before model loading because
Transformers attempted to create its dynamic custom-code cache under the
protected user cache (`A:\\Users\\rhine\\.cache\\huggingface\\modules`). The
next invocation must set `HF_HOME` to a writable project staging cache.

At the same time, the RTX 5080 reported 13.2 GiB allocated by pre-existing
processes. No process was stopped or evicted. The 4-bit measurement and
full-precision CPU edit remain pending until the GPU is genuinely idle and a
writable custom-code cache is configured. The source checkpoint is unchanged.
