# Upgrade 5 — the models. RUN THIS ONLY WITH REAL INTERNET.

Paste everything below the line into Claude Code **once you are off the hotspot**.

---

Download the models and switch on everything upgrades 1–4 built. **This prompt
downloads roughly 21 GB — do not run it on a metered connection.**

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## Confirm before downloading

Ask the operator to confirm they are on unmetered internet. **That is the one
legitimate stop in this prompt.** After confirmation, work straight through.

```
gpt-oss-20b             ~13 GB    main chat model
nomic-embed-text        ~275 MB   retrieval embeddings
qwen2.5vl:7b            ~6 GB     vision
faster-whisper large-v3 ~1.5 GB   audio (pip install faster-whisper)
```

The card is a **16 GB RTX 5080**. Everything below must leave room for a ComfyUI
render to start.

## Job 1 — the main model

```powershell
ollama pull gpt-oss-20b
```

MoE: ~20B total, ~3.6B active per token, trained with RL for function calling and
chain-of-thought — which is exactly what upgrade 1 rebuilt the agent around.

Put it at the front of `GPU_MODELS` in `router.py`. **Then measure, do not
assume:**

- VRAM with the model loaded at the chosen `num_ctx` — read `nvidia-smi`
- tokens/second on a real question
- whether a ComfyUI backend can still start while it is resident

If it crowds the card, either lower `num_ctx` or shorten `OLLAMA_KEEP_ALIVE` on
the GPU instance so it evicts sooner. Record what you measured and chose.

Keep a smaller model in `CPU_MODELS` — the CPU tier still needs something that
runs at four threads.

## Job 2 — real embeddings for retrieval

```powershell
ollama pull nomic-embed-text
```

Upgrade 2 left a swappable scorer interface with `LexicalScorer` as default.
Implement `EmbeddingScorer` against it: embed each chunk once, cache vectors
beside the index, embed the query per search, rank by cosine similarity.

**Do not delete the lexical scorer.** It is the offline fallback and the
comparison baseline.

Then compare them on the same queries and report which wins:

- "why was the pace corrected to 2.5"
- "what happens if a take has a doubled voice"
- "which clips render without audio references"
- "what does verified mean in this project"

If embeddings do not clearly beat BM25 on these, **say so and keep lexical as the
default.** Do not adopt a heavier component for its own sake.

## Job 3 — vision

```powershell
ollama pull qwen2.5vl:7b
```

`see_image` from upgrade 4 should now work with no code change. Verify that, then
test it honestly against this project's known blind spot:

- a full frame at native resolution → what does it report?
- **a native-resolution crop of a face** → does it catch a fault the full frame
  missed?

This project measured that reduced-scale review caught every large-area fault and
**missed every face-level one**. Confirm the crop path is what actually works,
and record the finding.

Also test it on burned-in text, extra people, and a frame you know is good — a
false positive on a good frame is as damaging as a miss.

## Job 4 — audio

```powershell
pip install faster-whisper
```

`transcribe` should now work. The critical test:

**Run it on the 14 known-good Narrator takes in
`ComfyUI-Shared\output\video\good audio\`, with `expected_text` from
`story_config.json`.** These are confirmed correct by ear, so the tool must agree.
If it reports errors on takes the operator has approved, **the tool is wrong, not
the takes** — recalibrate before trusting it on anything.

This matters: a previous recogniser on this project returned empty transcripts on
H3's synthetic voice and was useless. Whisper large-v3 should do far better, but
prove it on known-good material first.

Report the per-take word error rate. If it is low across all 14, that is a real
result — it means the audio gate can be mostly automated.

## Job 5 — retune and re-verify

With a smarter model, some scaffolding built for a weaker one is now overhead:

- try trimming the remaining defensive prompt rules and see if behaviour holds
- `MAX_TOOL_HOPS` may be loweredable if it plans better
- re-run the full acceptance list from `FINISH_LOCAL_AGENT.md`

## Verify

- [ ] `gpt-oss-20b` loads on GPU; VRAM, tok/s and render-coexistence all measured
- [ ] it calls tools reliably on questions the old model answered from memory
- [ ] embeddings vs BM25 compared on the four queries, with a recorded verdict
- [ ] `see_image` works; the crop-vs-full-frame difference is measured
- [ ] `transcribe` agrees with the operator's ear on all 14 known-good takes,
      with per-take WER reported
- [ ] `capabilities` now reports everything available
- [ ] guard rails still refuse; `validate_h3_prompt.py` still **124/124**
- [ ] `README.md` updated so no stale "not yet verified" line remains

## Do not stop

After the operator confirms unmetered internet, work straight through. A failing
test is a task, not a stopping point. Finish with a `CHANGELOG/` entry carrying
every measurement above — this project's standard is that a claim without a
number is not evidence.
