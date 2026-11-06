#!/usr/bin/env python3
"""Video temporal-physics expansion for 8-second Backrooms-style renders.

Modern video diffusion models want a dense paragraph, not a tag list.
This layer appends camera and temporal cues, then drops any default that
would fight a motion directive already in the base prompt (dolly, pan,
tripod, static shot, security camera).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

DEFAULT_COMPILED_ARTIFACT = (
    Path(__file__).resolve().parents[1] / "models" / "dspy_compiled" / "temporal_physics_v1.json"
)
OLLAMA_HOST = "http://127.0.0.1:11434"
PREFERRED_OLLAMA_MODELS = (
    "qwen2.5:1.5b",
    "llama3.2:1b",
    "llama3.2:latest",
    "qwen2.5:0.5b",
    "tinyllama",
    "phi3:mini",
    "qwen2.5:7b",
    "mistral:latest",
    "llama3.1:8b",
    "qwen3:8b",
    "dolphin3:latest",
)
SKIP_OLLAMA_PREFIXES = ("nomic-embed", "embed")

# Last runtime_inject result for tests/logs. Never required by ComfyUI dispatch.
LAST_INJECT_META: dict = {"source": "uninitialized", "model": None, "seconds": None}
_COMPILED_MODULE = None

BACKROOMS_PHYSICS = (
    "first-person camcorder tracking",
    "heavy VHS artifacting",
    "handheld walking momentum",
    "continuous unbroken shot",
    "realistic camera shake",
    "1990s home video aesthetic",
)

# Defaults that imply a walking operator with an unlocked camera.
_HANDHELD_FAMILY = frozenset({
    "first-person camcorder tracking",
    "handheld walking momentum",
    "realistic camera shake",
})

_LOCKED_CAMERA_RE = re.compile(
    r"\b(?:"
    r"tripod|static\s+shot|static\s+camera|locked[- ]off|"
    r"security\s+camera|cctv|surveillance\s+camera|fixed\s+camera|"
    r"static\s+security"
    r")\b",
    re.IGNORECASE,
)
_SPECIFIED_MOTION_RE = re.compile(
    r"\b(?:"
    r"dolly(?:\s+(?:in|out))?|"
    r"pan(?:\s+(?:left|right|up|down))?|"
    r"tilt(?:\s+(?:up|down))?|"
    r"crane|truck(?:\s+(?:left|right))?|orbit|"
    r"zoom(?:\s+(?:in|out))?|steadicam|gimbal"
    r")\b",
    re.IGNORECASE,
)


def camera_is_locked(prompt: str) -> bool:
    return bool(_LOCKED_CAMERA_RE.search(str(prompt or "")))


def has_specified_motion(prompt: str) -> bool:
    return bool(_SPECIFIED_MOTION_RE.search(str(prompt or "")))


def _normalize_base(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip(" ,;")
    return cleaned


def _already_present(prompt_l: str, term: str) -> bool:
    return term.lower() in prompt_l


def _physics_clause(terms: list[str]) -> str:
    if not terms:
        return ""
    if len(terms) == 1:
        body = terms[0]
    else:
        body = ", ".join(terms[:-1]) + ", and " + terms[-1]
    clause = body[0].upper() + body[1:]
    if not clause.endswith("."):
        clause += "."
    return clause


def inject_temporal_physics(base_prompt: str, style: str = "backrooms") -> str:
    """Expand ``base_prompt`` with style-specific temporal and camera physics.

    For ``backrooms`` (8-second camcorder renders) the defaults are first-person
    tracking, VHS, handheld walking momentum, an unbroken take, camera shake,
    and 1990s home-video texture. Locked or already-specified camera moves
    suppress the handheld-momentum family so the video model is not given
    two conflicting operators.
    """
    style_key = str(style or "backrooms").strip().lower() or "backrooms"
    if style_key != "backrooms":
        raise ValueError(f"unsupported temporal physics style: {style!r}")

    base = _normalize_base(base_prompt)
    prompt_l = base.lower()
    locked = camera_is_locked(base)
    specified = has_specified_motion(base)

    selected: list[str] = []
    for term in BACKROOMS_PHYSICS:
        if _already_present(prompt_l, term):
            continue
        if term in _HANDHELD_FAMILY and (locked or specified):
            continue
        selected.append(term)

    physics = _physics_clause(selected)
    if not base:
        return physics
    if base[-1] not in ".!?":
        base = base + "."
    if base[0].islower():
        base = base[0].upper() + base[1:]
    if not physics:
        return enforce_physics_terms(base_prompt, base)
    return enforce_physics_terms(base_prompt, f"{base} {physics}")


def enforce_physics_terms(base_prompt: str, injected: str) -> str:
    """Guarantee required tokens survive a tiny local LM.

    Unlocked cameras MUST contain the exact phrase
    ``handheld walking momentum``. Locked/authored cameras must not.
    """
    text = str(injected or "").strip()
    if not text:
        text = str(base_prompt or "").strip()
    locked = camera_is_locked(base_prompt) or has_specified_motion(base_prompt)
    lowered = text.lower()
    if locked:
        return text
    missing = [term for term in BACKROOMS_PHYSICS if term.lower() not in lowered]
    if not missing:
        return text
    extra = _physics_clause(missing)
    if text[-1] not in ".!?":
        text += "."
    return f"{text} {extra}"


def _resolve_artifact_path(artifact_path: str | Path | None) -> Path:
    path = Path(artifact_path or DEFAULT_COMPILED_ARTIFACT)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path


def load_compiled_temporal_physics(
    artifact_path: str | Path | None = "models/dspy_compiled/temporal_physics_v1.json",
) -> dict:
    """Deserialize the baked TemporalPhysicsInjector state JSON.

    Does not require dspy. Raises on missing/invalid files so callers can
    fall back. Never used uncaught from the dispatcher.
    """
    path = _resolve_artifact_path(artifact_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    predict = payload.get("prog.predict")
    if not isinstance(predict, dict):
        raise ValueError("compiled artifact missing prog.predict")
    demos = predict.get("demos")
    signature = predict.get("signature")
    if not isinstance(demos, list) or not demos:
        raise ValueError("compiled artifact has no demos")
    if not isinstance(signature, dict) or "fields" not in signature:
        raise ValueError("compiled artifact missing signature fields")
    prefixes = [str(field.get("prefix") or "") for field in signature.get("fields") or []]
    if "Injected Prompt:" not in prefixes:
        raise ValueError("compiled artifact is not a ChainOfThought injector dump")
    return payload


def ping_ollama(host: str = OLLAMA_HOST, timeout: float = 2.0) -> list[str]:
    """Return installed Ollama model names, or [] if 11434 is down."""
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        names = []
        for item in payload.get("models") or []:
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def _pick_ollama_model(installed: list[str]) -> str | None:
    installed_l = [n.lower() for n in installed]
    for preferred in PREFERRED_OLLAMA_MODELS:
        key = preferred.lower()
        for name, lower in zip(installed, installed_l):
            if lower == key or lower.startswith(key + ":") or lower.split(":")[0] == key.split(":")[0]:
                if not any(lower.startswith(skip) for skip in SKIP_OLLAMA_PREFIXES):
                    return name
    for name in installed:
        lower = name.lower()
        if any(lower.startswith(skip) for skip in SKIP_OLLAMA_PREFIXES):
            continue
        return name
    return None


def unload_ollama_model(host: str = OLLAMA_HOST, model: str | None = None) -> None:
    """Force Ollama to drop weights immediately (keep_alive=0)."""
    if model and "/" in str(model):
        model = str(model).split("/", 1)[-1]
    if not model:
        try:
            import dspy
            from dspy.dsp.utils.settings import settings
            lm = getattr(settings, "lm", None)
            model = getattr(lm, "model", None)
            if model and "/" in str(model):
                model = str(model).split("/", 1)[-1]
        except Exception:
            model = None
    if not model:
        return
    body = json.dumps({"model": model, "prompt": "", "keep_alive": 0}).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception:
        pass


def configure_local_dspy_lm(
    host: str = OLLAMA_HOST,
    model: str | None = None,
) -> bool:
    """Point dspy.settings.lm at local Ollama with keep_alive=0.

    keep_alive=0 is forwarded to LiteLLM/Ollama so the LLM unloads the
    instant the completion returns. Returns False if 11434 is down.
    """
    installed = ping_ollama(host)
    if not installed:
        return False
    chosen = model or _pick_ollama_model(installed)
    if not chosen:
        return False
    try:
        import dspy
        lm = dspy.LM(
            f"ollama_chat/{chosen}",
            api_base=host.rstrip("/"),
            cache=False,
            temperature=0.2,
            max_tokens=8192,
            keep_alive=0,
            extra_body={
                "keep_alive": 0,
                "num_predict": 8192,
                "repeat_penalty": 1.2,
                "stop": ["```\n", "<|im_end|>", "}\n}"],
                "options": {
                    "num_predict": 8192,
                    "repeat_penalty": 1.2,
                    "stop": ["```\n", "<|im_end|>", "}\n}"],
                },
            },
        )
        dspy.configure(lm=lm)
        return True
    except Exception:
        return False


def _dspy_lm_available() -> bool:
    try:
        import dspy
        from dspy.dsp.utils.settings import settings
        return getattr(settings, "lm", None) is not None
    except Exception:
        return False


def _compiled_injector(artifact_path: Path):
    global _COMPILED_MODULE
    if _COMPILED_MODULE is not None:
        return _COMPILED_MODULE
    import dspy

    class TemporalPhysicsInjector(dspy.Module):
        def __init__(self):
            super().__init__()
            self.prog = dspy.ChainOfThought("base_prompt, style -> injected_prompt")

        def forward(self, base_prompt, style):
            return self.prog(base_prompt=base_prompt, style=style)

    module = TemporalPhysicsInjector()
    module.load(str(artifact_path))
    _COMPILED_MODULE = module
    return module


def _infer_with_compiled(base_prompt: str, style: str, artifact_path: Path) -> str | None:
    """Run TemporalPhysicsInjector.load if dspy + an LM are present."""
    module = _compiled_injector(artifact_path)
    pred = module(base_prompt=base_prompt, style=style)
    text = str(getattr(pred, "injected_prompt", "") or "").strip()
    return text or None


def runtime_inject_temporal_physics(
    base_prompt: str,
    style: str = "backrooms",
    artifact_path: str | Path | None = "models/dspy_compiled/temporal_physics_v1.json",
) -> str:
    """Compiled DSPy inference via local Ollama when possible; else rules.

    Failures (missing artifact, Ollama down, dspy import, load errors) fall
    back silently to ``inject_temporal_physics``. Never raises into ComfyUI
    dispatch.
    """
    import time as _time
    started = _time.monotonic()
    LAST_INJECT_META.update({"source": "fallback", "model": None, "seconds": None})
    try:
        path = _resolve_artifact_path(artifact_path)
        load_compiled_temporal_physics(path)
        if not _dspy_lm_available() and os.environ.get(
                "DSPY_DISABLE_OLLAMA", "").strip().lower() not in {"1", "true", "yes"}:
            configure_local_dspy_lm()
        if _dspy_lm_available():
            compiled = _infer_with_compiled(base_prompt, style, path)
            if compiled:
                model_name = None
                try:
                    import dspy
                    from dspy.dsp.utils.settings import settings
                    lm = getattr(settings, "lm", None)
                    model_name = getattr(lm, "model", None)
                except Exception:
                    model_name = None
                unload_ollama_model(model=model_name)
                LAST_INJECT_META.update({
                    "source": "compiled",
                    "model": model_name,
                    "seconds": round(_time.monotonic() - started, 3),
                    "keep_alive": 0,
                })
                # Compiled DSPy output is scored by media_accuracy_gate.
                # Do not post-hoc append physics tokens; that hides LM failures.
                return compiled
    except Exception:
        pass
    try:
        text = inject_temporal_physics(base_prompt, style)
    except Exception:
        text = str(base_prompt or "")
    LAST_INJECT_META.update({
        "source": "fallback",
        "model": None,
        "seconds": round(_time.monotonic() - started, 3),
    })
    return text
