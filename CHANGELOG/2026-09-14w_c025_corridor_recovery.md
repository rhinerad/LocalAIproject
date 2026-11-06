# 2026-09-14w — C025 long-corridor recovery

C024 last remains accepted. C025 start paused after two unconditioned SDXL
failures. C025 start is a long yellow corridor; C025 last stretches to a
vanishing point. Reuse the reviewed C022 corridor plates.

- Start donor SHA-256: `3c90e7ba037b5063f226acfc2244a3d1a0d90c185c355e7bce7b85a2ed4cfd88`
- Last donor SHA-256: `c3e38d4a020e932ac526a2b4d697d86325e1113b06bf5bee0afc91d2ba6bb8a9`

Preserve rejected stills. Do not seed-spin. Do not start videos.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 177 tests passed.

C025 last then used the vanishing-corridor donor and passed exact VLM QA
(SHA-256 `c3e38d4a020e932ac526a2b4d697d86325e1113b06bf5bee0afc91d2ba6bb8a9`).
The runner continued to C026 start, which paused after two unconditioned
SDXL failures. That is the stop point. No video.
