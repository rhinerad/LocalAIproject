"""Shims so ImageReward 1.5 can import on transformers 5.x."""
from __future__ import annotations


def patch_transformers_for_imagereward() -> None:
    import torch
    import transformers.modeling_utils as mu
    try:
        import transformers.pytorch_utils as pu
    except Exception:
        pu = None
    if pu is not None and not hasattr(mu, "apply_chunking_to_forward"):
        mu.apply_chunking_to_forward = pu.apply_chunking_to_forward
    if pu is not None and not hasattr(mu, "prune_linear_layer"):
        mu.prune_linear_layer = pu.prune_linear_layer
    if not hasattr(mu, "find_pruneable_heads_and_indices"):
        def find_pruneable_heads_and_indices(heads, n_heads, head_size, already_pruned_heads):
            mask = torch.ones(n_heads, head_size)
            heads = set(heads) - already_pruned_heads
            for head in heads:
                head = head - sum(1 if h < head else 0 for h in already_pruned_heads)
                mask[head] = 0
            mask = mask.view(-1).contiguous().eq(1)
            index = torch.arange(len(mask))[mask].long()
            return heads, index
        mu.find_pruneable_heads_and_indices = find_pruneable_heads_and_indices
    try:
        from transformers import PreTrainedTokenizerBase
        if not hasattr(PreTrainedTokenizerBase, "additional_special_tokens_ids"):
            def _additional_special_tokens_ids(self):
                toks = list(getattr(self, "additional_special_tokens", None) or [])
                if not toks:
                    return []
                return self.convert_tokens_to_ids(toks)
            PreTrainedTokenizerBase.additional_special_tokens_ids = property(_additional_special_tokens_ids)
    except Exception:
        pass
    try:
        from transformers import BertTokenizer
        from ImageReward.models.BLIP import blip as _blip
        def init_tokenizer():
            tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
            tokenizer.add_special_tokens({"bos_token": "[DEC]"})
            tokenizer.add_special_tokens({"additional_special_tokens": ["[ENC]"]})
            tokenizer.enc_token_id = tokenizer.convert_tokens_to_ids("[ENC]")
            return tokenizer
        _blip.init_tokenizer = init_tokenizer
    except Exception:
        pass
