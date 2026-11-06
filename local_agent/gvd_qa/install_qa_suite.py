#!/usr/bin/env python3
"""Clone pinned QA node packs, pip CPU/Comfy deps, install GVD adapters.

Does not pin YRIKKA transformers==4.49.0 (Rockernow is on 5.10).
Does not download Qwen2.5-VL Instruct weights; Caption V4 remains the checklist.
Does not start or kill Comfy unless --restart and the queue is idle.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))

GIT = os.environ.get("GIT_EXE", r"C:\Program Files\Git\cmd\git.exe")
COMFY_PY = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe")
COMFY_NODES = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\custom_nodes")
AGENT_PY = Path(sys.executable)
QUARANTINE = ROOT / "local_agent" / "runtime" / "gvd_qa" / "quarantine"
TRUST_RECEIPT = (
    "2026-09-21 user: go ahead and download and install anything else you will "
    "need to complete this blueprint"
)

PINNED = [
    {
        "name": "ComfyUI-InferenceTimeScaling",
        "url": "https://github.com/YRIKKA/ComfyUI-InferenceTimeScaling.git",
        "sha": "e368962c9fbaa594433a9c04016fc00615dde6f4",
    },
    {
        "name": "ComfyUI-Image-Evaluation",
        "url": "https://github.com/wu12023/ComfyUI-Image-Evaluation.git",
        "sha": "6976a642ea317bf7f842714aa22c13c9174fcd47",
    },
    {
        "name": "comfyui_prompttester",
        "url": "https://github.com/drphero/comfyui_prompttester.git",
        "sha": "c1c9d314d130d1e4f6b1ed85dcaaa3b83e4b086f",
    },
]

AGENT_PIPS = [
    "torchmetrics",
    "transformers",
    "timm",
    "fairscale",
    "ftfy",
    "regex",
    "huggingface_hub",
]
COMFY_PIPS = [
    "fairscale",
    "ftfy",
    "regex",
    "image-reward",
]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None)


def clone_pinned() -> dict[str, str]:
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    out = {}
    for spec in PINNED:
        dest = QUARANTINE / spec["name"]
        if dest.exists():
            shutil.rmtree(dest)
        run([GIT, "clone", spec["url"], str(dest)])
        run([GIT, "checkout", spec["sha"]], cwd=dest)
        got = subprocess.check_output([GIT, "rev-parse", "HEAD"], cwd=dest, text=True).strip()
        if not got.startswith(spec["sha"][:12]):
            raise RuntimeError(f"{spec['name']} HEAD {got} != {spec['sha']}")
        out[spec["name"]] = got
        print(f"cloned {spec['name']} {got}", flush=True)
    return out


def patch_yrikka_qwen(repo: Path) -> None:
    path = repo / "src" / "inferencescale" / "nodes.py"
    text = path.read_text(encoding="utf-8")
    if "QwenVLMVerifier unavailable" not in text:
        old = "from .qwen_verifier import QwenVLMVerifier"
        if old not in text:
            raise RuntimeError("YRIKKA nodes.py qwen import not found")
        new = (
            "try:\n"
            "    from .qwen_verifier import QwenVLMVerifier\n"
            "except Exception as _qwen_exc:\n"
            "    logger.warning('QwenVLMVerifier unavailable (%s); Caption V4 is the GVD checklist', _qwen_exc)\n"
            "    QwenVLMVerifier = None  # type: ignore\n"
        )
        text = text.replace(old, new, 1)
    exec_old = "        verifier_instance = QwenVLMVerifier(model_checkpoint, device, score_type=score_type)"
    exec_new = (
        "        if QwenVLMVerifier is None:\n"
        "            raise RuntimeError('LoadQwenVLMVerifier blocked: outlines/Qwen Instruct not installed; use Caption V4')\n"
        "        verifier_instance = QwenVLMVerifier(model_checkpoint, device, score_type=score_type)"
    )
    if exec_old in text and "LoadQwenVLMVerifier blocked" not in text:
        text = text.replace(exec_old, exec_new, 1)
    path.write_text(text, encoding="utf-8")


def pip_install(py: Path, packages: list[str]) -> None:
    run([str(py), "-m", "pip", "install", "--upgrade-strategy", "only-if-needed", *packages])


def install_clip_and_imagereward(py: Path) -> None:
    run([str(py), "-m", "pip", "install", "--upgrade-strategy", "only-if-needed",
         "git+https://github.com/openai/CLIP.git"])
    run([str(py), "-m", "pip", "install", "--upgrade-strategy", "only-if-needed", "image-reward"])


def copy_into_comfy(clones: dict[str, str]) -> dict[str, str]:
    live = {}
    for name in clones:
        src = QUARANTINE / name
        dest = COMFY_NODES / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        live[name] = str(dest)
        print(f"installed {dest}", flush=True)
    return live


def install_gvd_adapters() -> dict:
    from gvd_qa.stage_adapters import stage_comfy_gvd_qa
    return stage_comfy_gvd_qa(
        quarantine_dir=QUARANTINE,
        object_info={},
        comfy_custom_nodes=COMFY_NODES,
        trust_receipt=TRUST_RECEIPT,
        install=True,
    )


def queue_idle(url: str = "http://127.0.0.1:8188") -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/queue", timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return not data.get("queue_running") and not data.get("queue_pending")
    except Exception:
        return True


def restart_comfy() -> None:
    if not queue_idle():
        raise RuntimeError("Comfy queue is busy; refusing restart")
    script = Path(r"A:\Users\rhine\.grok\long-running-background-tasks\restart_comfy_rockernow.ps1")
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-clone", action="store_true")
    parser.add_argument("--skip-pip", action="store_true")
    parser.add_argument("--skip-comfy-copy", action="store_true")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    report = {"utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
    if not args.skip_clone:
        report["clones"] = clone_pinned()
        patch_yrikka_qwen(QUARANTINE / "ComfyUI-InferenceTimeScaling")
        report["yrikka_qwen_lazy"] = True
    if not args.skip_pip:
        pip_install(AGENT_PY, AGENT_PIPS)
        install_clip_and_imagereward(AGENT_PY)
        pip_install(COMFY_PY, COMFY_PIPS)
        install_clip_and_imagereward(COMFY_PY)
        report["pip"] = "ok"
    if not args.skip_comfy_copy:
        clones = {spec["name"]: spec["sha"] for spec in PINNED}
        report["live_nodes"] = copy_into_comfy(clones)
        report["gvd_adapters"] = install_gvd_adapters()
    if args.restart:
        restart_comfy()
        report["restarted"] = True
    dest = ROOT / "local_agent" / "runtime" / "gvd_qa" / "install_qa_suite.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"wrote": str(dest), "keys": list(report)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
