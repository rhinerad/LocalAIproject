# 2026-09-05cf — Bamboo-DPO-7B prompt-format source research (no load)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05cf**.

Research only. No GPU, no model load, no inference. Did not read or write
`A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake` or any
validation/receipt files. Candidate stays unregistered.

## Question

TODO.md (~702–717) blocks a ten-case instruction/format comparison on
`prompt_contract_unresolved`. This pass asked whether public sources
name the model's intended prompt format.

## Sources

| Source | What it is |
|---|---|
| [Tiiny/Bamboo-DPO-v0_1](https://huggingface.co/Tiiny/Bamboo-DPO-v0_1) (alias [PowerInfer/Bamboo-DPO-v0_1](https://huggingface.co/PowerInfer/Bamboo-DPO-v0_1)), revision `200c173716a059eaa29d6820a09b3bde76a727ed` | Original weights + custom code. Matches the 2026-08-30 provenance lock. |
| [Tiiny/Bamboo-DPO-v0.1-gguf](https://huggingface.co/Tiiny/Bamboo-DPO-v0.1-gguf) | PowerInfer GGUF. Card is convert/cite only. |
| [SJTU-IPADS/Bamboo](https://github.com/SJTU-IPADS/Bamboo) | Author repo. |
| `tokenizer_config.json`, `special_tokens_map.json`, `modeling_bamboo.py` (public HF raw) | Shipped tokenizer + generation example. |
| HF model API `cardData.datasets` | Author YAML, not a guessed tag. |
| Lineage papers on the card | Architecture/sparsity, not prompting. |

## What the sources say

**Documented inference path is plain raw completion.**
`modeling_bamboo.py` `BambooForCausalLM` example (also names the *base*
checkpoint) is:

```python
prompt = "Hey, are you conscious? Can you talk to me?"
inputs = tokenizer(prompt, return_tensors="pt")
generate_ids = model.generate(inputs.input_ids, max_length=30)
```

No `[INST]`, ChatML, Alpaca, Vicuna, or role tokens.

**Shipped tokenizer has no chat contract.** Public
`tokenizer_config.json` (same on PowerInfer/ and Tiiny/ DPO):

- LlamaTokenizer; `bos_token` `<s>`, `eos_token` `</s>`, `unk`/`pad` `<unk>`
- `additional_special_tokens: []`
- `use_default_system_prompt: false`
- **no `chat_template` key**

`special_tokens_map.json` is those four tokens only. HF API
`pipeline_tag` is `feature-extraction`, not conversational.

The DPO **README is the base pretrain card** (dReLU FFN, 200B-token
continued pretrain from Mistral, lm-eval vs Mistral-v0.1). It never
describes DPO data, SFT, or a chat wrapper. GGUF card adds nothing.

**GitHub does not treat DPO-v0.1 as the chat model.**
[SJTU-IPADS/Bamboo](https://github.com/SJTU-IPADS/Bamboo) lists
Bamboo-7B-base-v0.1 and Bamboo-7B-DPO-v0.1, then Future Work:
"Better base and **chat-7B** model." No prompt section.

**Bagel is a lead, not a contract.** DPO `cardData.datasets` is
`["jondurbin/bagel-v0.3"]` (base card instead lists Falcon-RefinedWeb /
StarCoder / Open-Web-Math). Bagel's own models document **four**
formats (Vicuna, Llama-2 `[INST]`, Alpaca, ChatML-ish) and ship a
Llama-2 `chat_template`. Bamboo-DPO does **not**. Picking `[INST]`
from the DPO name or the Bagel tag would repeat the ReluLLaMA
invented-wrapper error.

**Lineage papers are sparsity, not prompting.**

- Zhang et al. 2021, [MoEfication](https://arxiv.org/abs/2110.01786)
  (`2110.01786`)
- Liu et al. 2023, ReluLLaMA / DejaVu-family (OpenReview `wIPIhHd00i`)
- Mirzadeh et al. 2023, [ReLU Strikes Back](https://arxiv.org/abs/2310.04564)
  (`2310.04564`)
- GitHub also cites Zhang/Song et al. 2024, [ReLU2 Wins](https://arxiv.org/abs/2402.03804)
  (`2402.03804`) for top-k activation

Author citation is unpublished `@misc{bamboo, title={Bamboo: Harmonizing
Sparsity and Performance in Large Language Models}, year={2024}}`. No
arXiv PDF with a prompt section was found.

PowerInfer README (2024-03-28) only links Base/DPO GGUFs ("Experience
it with…"). No format.

## Verdict

| Claim | Confidence |
|---|---|
| Only documented generate path is raw `tokenizer(prompt)` | **High** |
| No shipped `chat_template` / extra special tokens | **High** (public files) |
| DPO YAML lists bagel-v0.3; base does not | **High** (API `cardData`) |
| Bagel implies one wrapper (`[INST]` / ChatML / …) | **Low** — bagel is four formats; Bamboo did not ship one |
| Authors consider DPO-v0.1 the finished chat model | **Low** — GitHub still wants a "chat-7B" |

**Does not resolve `prompt_contract_unresolved`.** It confirms the
frozen classifier from public HF (not only the intake tree) and adds
bagel-v0.3 as an unresolved multi-format lead. A ten-case
instruction/format comparison is still not authorized. Raw-completion
diagnostic remains the only source-backed path. Candidate stays
unregistered; no router/picker/registry change.
