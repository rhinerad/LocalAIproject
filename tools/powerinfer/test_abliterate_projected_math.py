"""CPU-only check that the Projected Abliteration formula is unchanged."""

from __future__ import annotations

import torch

from abliterate_loader import edit_tensor_norm_preserving
from abliterate_turbosparse import TARGET_RE, projected_refusal_direction


class _FakeModel:
    def __init__(self, hidden: torch.Tensor) -> None:
        self.hidden = hidden

    def __call__(self, **kwargs):
        class Out:
            pass

        out = Out()
        out.hidden_states = [None, self.hidden]
        return out


class _Tok:
    def __call__(self, text, **kwargs):
        del text, kwargs
        return {
            "input_ids": torch.zeros(1, 1, dtype=torch.long),
            "attention_mask": torch.ones(1, 1, dtype=torch.long),
        }


def test_refined_direction_matches_hand_formula() -> None:
    harmful = torch.tensor([3.0, 1.0, 0.0])
    harmless = torch.tensor([0.0, 4.0, 0.0])
    hnorm = harmless.norm()
    unit = harmless / hnorm
    refusal = harmful - harmless
    scalar = torch.dot(refusal, unit)
    refined = refusal - scalar * unit
    expected = refined / refined.norm()

    pairs = [{"harmful": "a", "harmless": "b"}]
    model = _FakeModel(harmful.view(1, 1, 3))

    class Swap:
        def __init__(self) -> None:
            self.n = 0

        def __call__(self, **kwargs):
            self.n += 1
            vec = harmful if self.n == 1 else harmless
            return _FakeModel(vec.view(1, 1, 3))(**kwargs)

    direction, projection_scalar = projected_refusal_direction(Swap(), _Tok(), pairs, "cpu")
    assert abs(projection_scalar - float(scalar)) < 1e-5
    assert torch.allclose(direction, expected, atol=1e-5)
    assert abs(float(direction.norm()) - 1.0) < 1e-5
    assert abs(float(torch.dot(direction, unit))) < 1e-5


def test_o_proj_only_and_norm_preserved() -> None:
    d = torch.tensor([1.0, 0.0, 0.0])
    weight = torch.arange(12, dtype=torch.float32).reshape(3, 4)
    skipped = edit_tensor_norm_preserving("model.layers.0.mlp.down_proj.weight", weight.clone(), d, 1.0, TARGET_RE)
    assert torch.equal(skipped, weight)
    edited = edit_tensor_norm_preserving("model.layers.0.self_attn.o_proj.weight", weight.clone(), d, 1.0, TARGET_RE)
    assert edited.shape == weight.shape
    assert abs(float(edited.float().norm() - weight.float().norm())) < 1e-5
    bf16 = torch.arange(12, dtype=torch.bfloat16).reshape(3, 4)
    edited_bf16 = edit_tensor_norm_preserving("model.layers.0.self_attn.o_proj.weight", bf16.clone(), d, 1.0, TARGET_RE)
    rel = abs(float(edited_bf16.float().norm() - bf16.float().norm()) / float(bf16.float().norm()))
    assert rel < 1e-3, rel
    assert TARGET_RE.search("model.layers.7.self_attn.o_proj.weight")
    assert not TARGET_RE.search("model.layers.7.mlp.down_proj.weight")


if __name__ == "__main__":
    test_refined_direction_matches_hand_formula()
    test_o_proj_only_and_norm_preserved()
    print("math-ok")
