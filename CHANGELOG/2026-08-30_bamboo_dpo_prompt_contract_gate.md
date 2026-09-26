# 2026-08-30 — Bamboo-DPO prompt-contract gate

Added a local-only classifier for the frozen Bamboo-DPO candidate's prompt
contract. It does not load a model, call a network service, or alter the
candidate, PowerInfer registry, agent router, proxy, or picker.

The byte-verified frozen source establishes Bamboo dReLU, but its tokenizer
contains no `chat_template` and its README contains no explicit instruction
format marker. The resulting evidence is
`A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake\validation\bamboo_dpo_prompt_contract_20260830_233100.json`.

It records `prompt_contract_unresolved`, `chat_routing_allowed: false`, and
`instruction_quality_gate_allowed: false`. This prevents the earlier ReluLLaMA
category error—testing a model with an invented `[INST]` wrapper—while allowing
the separately recorded raw-completion mechanical result to remain valid.

`test_classify_bamboo_dpo_prompt_contract.py` covers missing-template blocking
and the declared-template future-review path (2 tests passed).
