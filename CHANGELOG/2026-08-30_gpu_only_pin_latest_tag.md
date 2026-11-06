# 2026-08-30 — GPU-only pin match accepts Ollama `:latest`

## What changed

`CHANGELOG/2026-08-30_decide_early_return_audit.md` left this as "ambiguous /
no evidence the picker emits those strings." That was an assumption. Traced
the names.

**Heretic — real gap.** The picker *does* emit `gpt-oss-20b-heretic:latest`
once Ollama lists that tag. Exact-string `is_gpu_only_opt_in_model()` then
missed, and `decide()` fell through to a CPU "cannot run now" refusal.

**PowerInfer — picker never suffixes.** `chat_models()` always sets
`"name": POWERINFER_MODEL_ALIAS`. `_valid_chat_model` only accepts names
from that list, so the GUI/server pin path cannot store
`powerinfer-local:latest`. Comparison is still family+tag so a suffix cannot
miss if it reaches `decide()` another way.

Fix: normalize the **comparison** in `is_gpu_only_opt_in_model` and
`is_powerinfer_model` via existing `_is_configured_variant`. Did not change
`GPT_OSS_20B_HERETIC_MODEL`, `POWERINFER_MODEL_ALIAS`, or stored chat pins.

| File | Change |
|---|---|
| `local_agent/router.py` | pin match uses `_is_configured_variant` |
| `local_agent/test_router_switching.py` | picker emits `:latest` when catalogue has it; suffixed Heretic and PowerInfer busy pins get the GPU-only refusal |

## Why — file:line, not the assumption

1. Install name is untagged. `setup_gpt_oss_20b_heretic.py:26` /
   `:119`: `OLLAMA_MODEL_NAME = "gpt-oss-20b-heretic"` and
   `ollama create gpt-oss-20b-heretic`. Ollama's default tag is `latest`.
2. Catalogue is used raw. `router.py:655-658` `_tags()` returns
   `m["name"]` from `/api/tags` with no strip.
3. Untagged configured names are treated as `:latest`.
   `router.py:114-117` `_family_tag`: no colon → tag `"latest"`.
   `router.py:120-128` `_installed_variant` then returns the **catalogue**
   string `gpt-oss-20b-heretic:latest`.
4. Picker publishes that catalogue string.
   `router.py:272-277`: `"name": installed or name`.
5. GUI pins whatever `name` is. `static/index.html:238`
   `o.value=m.name`; `:438` `model:activeModel||$('#chatmodel').value`.
6. Server accepts it because it is in `chat_models` names.
   `server.py:379-389` `_valid_chat_model`; `:248` / `:402` `store.create(..., model=model)`.
7. Turns pass the stored pin into `decide()`.
   `server.py:505` `model=conv.get("model")`; `agent.py:991`
   `router.decide(..., model=model)`.
8. Before this change, `is_gpu_only_opt_in_model` was
   `str(model) in GPU_ONLY_OPT_IN_MODELS` (`router.py` former L104-106),
   which is only the bare `gpt-oss-20b-heretic`.

PowerInfer contrast: `router.py:287-290` `"name": POWERINFER_MODEL_ALIAS`
only. Never `_installed_variant`, never `/api/tags`.

## The evidence

```
python test_router_switching.py -v
...
test_heretic_latest_suffix_gets_same_gpu_only_busy_refusal ... ok
test_heretic_picker_emits_ollama_latest_tag_when_catalogue_has_it ... ok
test_powerinfer_latest_suffix_gets_same_gpu_only_busy_refusal ... ok
...
Ran 41 tests in 7.301s
OK
```

41 = previous 38 plus those three. Bare-name Heretic/PowerInfer tests still
pass.

## What was verified after

The suite above. No live `ollama create`, no GPU load, no GUI click.

## What is still unverified

- A live `/api/tags` dump from this machine's GPU Ollama after
  `setup_gpt_oss_20b_heretic.py --create`. The unit test feeds the catalogue
  form Ollama uses for an untagged create (`name:latest`).
- Existing chats already pinned to the bare Heretic name remain valid; the
  comparison matches both forms.
