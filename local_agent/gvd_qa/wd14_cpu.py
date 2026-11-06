"""Pin WD14 ONNX to CPU in an isolated QA worker. Does not edit Rockernow live."""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from .validate import qa_activation_report  # noqa: F401  (bootstrap/tests import via this module)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "wd-v1-4-moat-tagger-v2"
DEFAULT_HF_ENDPOINT = "https://huggingface.co"
KNOWN_REPOS = {
    "wd-v1-4-moat-tagger-v2": "SmilingWolf/wd-v1-4-moat-tagger-v2",
    "wd-v1-4-convnextv2-tagger-v2": "SmilingWolf/wd-v1-4-convnextv2-tagger-v2",
    "wd-v1-4-swinv2-tagger-v2": "SmilingWolf/wd-v1-4-swinv2-tagger-v2",
    "wd-v1-4-vit-tagger-v2": "SmilingWolf/wd-v1-4-vit-tagger-v2",
    "wd-v1-4-convnext-tagger-v2": "SmilingWolf/wd-v1-4-convnext-tagger-v2",
    "wd-swinv2-tagger-v3": "SmilingWolf/wd-swinv2-tagger-v3",
    "wd-vit-tagger-v3": "SmilingWolf/wd-vit-tagger-v3",
    "wd-convnext-tagger-v3": "SmilingWolf/wd-convnext-tagger-v3",
    "wd-eva02-large-tagger-v3": "SmilingWolf/wd-eva02-large-tagger-v3",
}
_SESSION_CACHE: dict[tuple[str, tuple[str, ...]], Any] = {}


def _runner():
    spec = importlib.util.spec_from_file_location("_gvd_qa_runner_cpu", ROOT / "gvd_qa.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["_gvd_qa_runner_cpu"] = mod
    spec.loader.exec_module(mod)
    return mod


def cpu_ort_settings() -> dict[str, Any]:
    return {"ortProviders": ["CPUExecutionProvider"]}


def write_qa_worker_wd14_settings(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {"settings": cpu_ort_settings()}
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def assert_cpu_providers(settings: dict[str, Any]) -> None:
    providers = (settings.get("settings") or settings).get("ortProviders") or []
    _runner().onnx_must_be_cpu(providers)


def models_dir() -> Path:
    return ROOT / "local_agent" / "runtime" / "gvd_qa" / "wd14_models"


def model_urls(model: str = DEFAULT_MODEL, hf_endpoint: str | None = None) -> dict[str, str]:
    repo = KNOWN_REPOS.get(model)
    if not repo:
        raise _runner().QAError(f"Unknown WD14 model {model}")
    endpoint = (hf_endpoint or os.environ.get("HF_ENDPOINT") or DEFAULT_HF_ENDPOINT).rstrip("/")
    if not endpoint.startswith("https://"):
        endpoint = "https://" + endpoint
    base = f"{endpoint}/{repo}/resolve/main"
    return {"onnx": f"{base}/model.onnx", "csv": f"{base}/selected_tags.csv"}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "gvd-qa-wd14-cpu"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    if tmp.stat().st_size < 1:
        tmp.unlink(missing_ok=True)
        raise _runner().QAError(f"WD14 download empty: {url}")
    os.replace(tmp, dest)


def ensure_model(
    dest_dir: Path | None = None,
    model: str = DEFAULT_MODEL,
    *,
    download: bool = True,
    hf_endpoint: str | None = None,
) -> tuple[Path, Path]:
    dest = Path(dest_dir) if dest_dir is not None else models_dir()
    dest.mkdir(parents=True, exist_ok=True)
    onnx = dest / f"{model}.onnx"
    csv_path = dest / f"{model}.csv"
    if onnx.is_file() and csv_path.is_file() and onnx.stat().st_size > 0 and csv_path.stat().st_size > 0:
        return onnx, csv_path
    if not download:
        raise _runner().QAError(f"WD14 model files missing under {dest}")
    urls = model_urls(model, hf_endpoint=hf_endpoint)
    if not onnx.is_file() or onnx.stat().st_size < 1:
        _download(urls["onnx"], onnx)
    if not csv_path.is_file() or csv_path.stat().st_size < 1:
        _download(urls["csv"], csv_path)
    return onnx, csv_path


def load_session(
    onnx_path: Path,
    *,
    providers: list[str] | None = None,
    cache: bool = True,
):
    import onnxruntime as ort

    chosen = list(providers or cpu_ort_settings()["ortProviders"])
    _runner().onnx_must_be_cpu(chosen)
    key = (str(onnx_path.resolve()), tuple(chosen))
    if cache and key in _SESSION_CACHE:
        return _SESSION_CACHE[key]
    session = ort.InferenceSession(str(onnx_path), providers=chosen)
    used = [str(p) for p in session.get_providers()]
    _runner().onnx_must_be_cpu(used)
    if cache:
        _SESSION_CACHE[key] = session
    return session


def _preprocess(image, height: int):
    import numpy as np
    from PIL import Image

    if image.mode != "RGB":
        image = image.convert("RGB")
    ratio = float(height) / max(image.size)
    new_size = tuple(int(x * ratio) for x in image.size)
    image = image.resize(new_size, Image.LANCZOS)
    square = Image.new("RGB", (height, height), (255, 255, 255))
    square.paste(image, ((height - new_size[0]) // 2, (height - new_size[1]) // 2))
    arr = np.array(square).astype("float32")
    arr = arr[:, :, ::-1]
    return np.expand_dims(arr, 0)


def _read_vocab(csv_path: Path, replace_underscore: bool) -> tuple[list[str], int, int]:
    tags: list[str] = []
    general_index = None
    character_index = None
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader)
        for row in reader:
            if general_index is None and row[2] == "0":
                general_index = reader.line_num - 2
            elif character_index is None and row[2] == "4":
                character_index = reader.line_num - 2
            name = row[1].replace("_", " ") if replace_underscore else row[1]
            tags.append(name)
    if general_index is None or character_index is None:
        raise _runner().QAError("WD14 selected_tags.csv missing general or character category")
    return tags, general_index, character_index


def tag_image(
    image: bytes | Path,
    *,
    models_dir_path: Path | None = None,
    model: str = DEFAULT_MODEL,
    threshold: float = 0.35,
    character_threshold: float = 0.85,
    replace_underscore: bool = True,
    session: Any | None = None,
    csv_path: Path | None = None,
    providers: list[str] | None = None,
    download: bool = False,
) -> dict[str, Any]:
    from PIL import Image

    chosen = list(providers or cpu_ort_settings()["ortProviders"])
    _runner().onnx_must_be_cpu(chosen)
    if isinstance(image, Path):
        blob = image.read_bytes()
    else:
        blob = image
    pil = Image.open(BytesIO(blob))
    if session is None:
        onnx_path, csv_file = ensure_model(models_dir_path, model, download=download)
        csv_path = csv_path or csv_file
        session = load_session(onnx_path, providers=chosen)
    if csv_path is None:
        _, csv_path = ensure_model(models_dir_path, model, download=download)
    tags, general_index, character_index = _read_vocab(Path(csv_path), replace_underscore)
    inp = session.get_inputs()[0]
    height = int(inp.shape[1])
    batch = _preprocess(pil, height)
    label_name = session.get_outputs()[0].name
    probs = session.run([label_name], {inp.name: batch})[0]
    scored = list(zip(tags, [float(x) for x in probs[0]]))
    general = [
        {"tag": name, "score": score}
        for name, score in scored[general_index:character_index]
        if score > threshold
    ]
    character = [
        {"tag": name, "score": score}
        for name, score in scored[character_index:]
        if score > character_threshold
    ]
    ordered = character + general
    tag_string = ", ".join(item["tag"].replace("(", "\\(").replace(")", "\\)") for item in ordered)
    used = [str(p) for p in getattr(session, "get_providers", lambda: chosen)()]
    _runner().onnx_must_be_cpu(used)
    return {
        "model": model,
        "providers": used,
        "threshold": threshold,
        "character_threshold": character_threshold,
        "tags": tag_string,
        "general": general,
        "character": character,
    }


def cpu_wd14_fn(
    *,
    models_dir_path: Path | None = None,
    model: str = DEFAULT_MODEL,
    download: bool = False,
    session: Any | None = None,
    csv_path: Path | None = None,
) -> Callable[[bytes], str]:
    def _fn(blob: bytes) -> str:
        return tag_image(
            blob,
            models_dir_path=models_dir_path,
            model=model,
            download=download,
            session=session,
            csv_path=csv_path,
        )["tags"]
    return _fn
