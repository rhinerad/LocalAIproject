#!/usr/bin/env python3
"""Reapply ImageReward 1.5 shims for transformers 5.x. Idempotent."""
from __future__ import annotations

from pathlib import Path

ENC_OLD = "    tokenizer.enc_token_id = tokenizer.additional_special_tokens_ids[0]"
ENC_NEW = """    enc_ids = list(getattr(tokenizer, "additional_special_tokens_ids", None) or [])
    tokenizer.enc_token_id = enc_ids[0] if enc_ids else tokenizer.convert_tokens_to_ids("[ENC]")"""

TIED_MARKER = "    all_tied_weights_keys"
TIED_INSERT = '''    _tied_weights_keys = {}

    @property
    def all_tied_weights_keys(self):
        return {}

    def invert_attention_mask(self, encoder_attention_mask):
        if encoder_attention_mask.dim() == 3:
            extended = encoder_attention_mask[:, None, :, :]
        else:
            extended = encoder_attention_mask[:, None, None, :]
        dtype = self.dtype
        extended = extended.to(dtype=dtype)
        return (1.0 - extended) * torch.finfo(dtype).min

    def get_head_mask(self, head_mask, num_hidden_layers, is_attention_chunked=False):
        if head_mask is not None:
            head_mask = self._convert_head_mask_to_5d(head_mask, num_hidden_layers)
            if is_attention_chunked:
                head_mask = head_mask.unsqueeze(-1)
        else:
            head_mask = [None] * num_hidden_layers
        return head_mask
'''


def patch_tree(root: Path) -> list[str]:
    done = []
    blip = root / "models" / "BLIP" / "blip.py"
    med = root / "models" / "BLIP" / "med.py"
    if blip.is_file():
        text = blip.read_text(encoding="utf-8")
        if "convert_tokens_to_ids(\"[ENC]\")" not in text and ENC_OLD in text:
            blip.write_text(text.replace(ENC_OLD, ENC_NEW, 1), encoding="utf-8")
            done.append(str(blip))
    if med.is_file():
        text = med.read_text(encoding="utf-8")
        if "def invert_attention_mask" not in text:
            needle = "    _keys_to_ignore_on_load_missing = [r\"position_ids\"]\n"
            if needle in text:
                med.write_text(text.replace(needle, needle + "\n" + TIED_INSERT, 1), encoding="utf-8")
                done.append(str(med))
    return done


def main() -> int:
    import ImageReward
    roots = [Path(ImageReward.__file__).resolve().parent]
    try:
        import sys
        for p in sys.path:
            cand = Path(p) / "ImageReward"
            if cand.is_dir() and cand not in roots:
                roots.append(cand)
    except Exception:
        pass
    changed = []
    for root in roots:
        changed.extend(patch_tree(root))
    print("patched", changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
