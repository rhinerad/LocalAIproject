"""QA thresholds and Comfy class names. Thresholds are design defaults."""
from __future__ import annotations

WD14_CLASS = "WD14Tagger|pysssss"

# YRIKKA InferenceTimeScaling — not installed here.
YRIKKA_QWEN_CLASSES = (
    "Load Qwen VLM Verifier",
    "LoadQwenVLMVerifier",
    "QwenVLMVerifier",
)
YRIKKA_IMAGE_REWARD_CLASSES = (
    "ImageReward Verifier",
    "ImageRewardVerifier",
)
YRIKKA_CLIP_CLASSES = (
    "CLIPScore Verifier",
    "CLIPScoreVerifier",
)

# wu12023 ComfyUI-Image-Evaluation — not installed here.
WU_DINO_CLASSES = ("DINOScore", "DINOImageScore", "ImageDINOScore")
WU_CLIP_CLASSES = ("CLIPImageScore", "ImageCLIPScore", "CLIPScore")

DEFAULT_CLIP_MIN = 0.22
DEFAULT_IMAGE_REWARD_MIN = 0.0
DEFAULT_VLM_ALIGNMENT_MIN = 0.60
DEFAULT_ATTEMPT_BUDGET = 3  # initial render + two rerolls

# Duplicate-generation detection. Caption token Jaccard above this AND a
# perceptual dhash distance at or below this flag a near-identical output.
DUP_CAPTION_OVERLAP_MAX = 0.85
DUP_DHASH_MAX_DISTANCE = 8

ADAPTER_YRIKKA = "comfyui-inference-time-scaling"
ADAPTER_WU = "comfyui-image-evaluation"
ADAPTER_PROMPT_TESTER = "comfyui-prompttester"
ADAPTER_WD14 = "comfyui-wd14-tagger"
