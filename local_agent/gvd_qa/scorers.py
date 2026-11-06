"""CPU CLIP / DINO / ImageReward for LocalQaClient. Never uses Comfy CUDA."""
from __future__ import annotations

from io import BytesIO
from typing import Any

CLIP_MODEL = "openai/clip-vit-base-patch32"
DINO_MODEL = "facebook/dino-vits16"
IMAGE_REWARD_ID = "ImageReward-v1.0"
DEVICE = "cpu"

_CACHE: dict[str, Any] = {}


def _pil(image: bytes):
    from PIL import Image
    return Image.open(BytesIO(image)).convert("RGB")


def _center_crop_224(pil):
    from PIL import Image
    w, h = pil.size
    scale = 256 / min(w, h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    pil = pil.resize((nw, nh), Image.BICUBIC)
    left = max(0, (nw - 224) // 2)
    top = max(0, (nh - 224) // 2)
    return pil.crop((left, top, left + 224, top + 224))


def clip_text_score(image: bytes, caption: str, *, model: str = CLIP_MODEL) -> float:
    """CLIP text-image score in unit torchmetrics_clipscore_0_100: max(100 * cosine, 0).

    Implemented with transformers CLIPModel on CPU. The TorchMetrics CLIPScore
    wrapper is not used because it breaks on transformers 5.x outputs.
    """
    import torch
    import torch.nn.functional as F
    from transformers import CLIPModel, CLIPProcessor

    key = "clip:" + model
    packed = _CACHE.get(key)
    if packed is None:
        net = CLIPModel.from_pretrained(model).to(DEVICE)
        net.eval()
        processor = CLIPProcessor.from_pretrained(model)
        packed = (net, processor)
        _CACHE[key] = packed
    net, processor = packed
    inputs = processor(text=[caption], images=_pil(image), return_tensors="pt", padding=True)
    inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
    with torch.inference_mode():
        text_out = net.get_text_features(inputs["input_ids"], attention_mask=inputs.get("attention_mask"))
        image_out = net.get_image_features(pixel_values=inputs["pixel_values"])
        text_emb = text_out.pooler_output if hasattr(text_out, "pooler_output") else text_out
        image_emb = image_out.pooler_output if hasattr(image_out, "pooler_output") else image_out
        text_emb = F.normalize(text_emb, dim=-1)
        image_emb = F.normalize(image_emb, dim=-1)
        cosine = float(F.cosine_similarity(text_emb, image_emb).detach().cpu())
    return float(max(100.0 * cosine, 0.0))


def clip_image_score(source: bytes, target: bytes, *, model: str = CLIP_MODEL) -> float:
    """CLIP image-image raw cosine, nominally -1 to 1. CPU only."""
    import torch
    import torch.nn.functional as F
    from transformers import CLIPModel, CLIPProcessor

    key = "clip:" + model
    packed = _CACHE.get(key)
    if packed is None:
        net = CLIPModel.from_pretrained(model).to(DEVICE)
        net.eval()
        processor = CLIPProcessor.from_pretrained(model)
        packed = (net, processor)
        _CACHE[key] = packed
    net, processor = packed

    def embed(blob: bytes):
        inputs = processor(images=_pil(blob), return_tensors="pt")
        pixel = inputs["pixel_values"].to(DEVICE)
        with torch.inference_mode():
            out = net.get_image_features(pixel_values=pixel)
        emb = out.pooler_output if hasattr(out, "pooler_output") else out
        return F.normalize(emb, dim=-1)

    a, b = embed(source), embed(target)
    return float(F.cosine_similarity(a, b).detach().cpu())


def dino_image_score(source: bytes, target: bytes, *, model: str = DINO_MODEL) -> float:
    """facebook/dino-vits16 CLS cosine. CPU only. Same recipe as wu12023."""
    import numpy as np
    import torch
    import torch.nn.functional as F
    from transformers import ViTModel

    key = "dino:" + model
    net = _CACHE.get(key)
    if net is None:
        net = ViTModel.from_pretrained(model).to(DEVICE)
        net.eval()
        _CACHE[key] = net
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def embed(blob: bytes):
        crop = _center_crop_224(_pil(blob))
        arr = np.array(crop, dtype=np.float32) / 255.0
        arr = (arr - mean) / std
        tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(DEVICE)
        with torch.inference_mode():
            out = net(tensor)
        return out.last_hidden_state[0, 0]

    a, b = embed(source), embed(target)
    return float(F.cosine_similarity(a, b, dim=0).detach().cpu())


def image_reward_score(image: bytes, caption: str, *, model_id: str = IMAGE_REWARD_ID) -> float:
    """Raw ImageReward. CPU only. Unit imagereward_raw."""
    from .transformers_compat import patch_transformers_for_imagereward
    patch_transformers_for_imagereward()
    import ImageReward as reward

    key = "ir:" + model_id
    model = _CACHE.get(key)
    if model is None:
        model = reward.load(model_id)
        try:
            model.to(DEVICE)
        except Exception:
            pass
        model.eval()
        _CACHE[key] = model
    return float(model.score(caption, _pil(image)))
