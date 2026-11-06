"""Stage ComfyUI-GVD-QA into quarantine. Live custom_nodes copy needs a trust receipt."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .validate import qa_activation_report

PACKAGE = Path(__file__).resolve().parent / "ComfyUI-GVD-QA"


def stage_comfy_gvd_qa(
    *,
    quarantine_dir: Path,
    object_info: dict[str, Any] | None,
    comfy_custom_nodes: Path | None = None,
    trust_receipt: str | None = None,
    install: bool = False,
) -> dict[str, Any]:
    dest = quarantine_dir / "ComfyUI-GVD-QA"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(PACKAGE, dest)
    for extra in ("comfy_adapters.py", "transformers_compat.py"):
        src = PACKAGE.parent / extra
        if src.is_file():
            shutil.copy2(src, dest / extra)
    report = {
        "staged": str(dest),
        "installed": False,
        "activation": qa_activation_report(object_info),
    }
    if not install:
        report["note"] = "Staged only. Live custom_nodes unchanged."
        return report
    if not trust_receipt:
        raise ValueError("install requires an explicit trust_receipt")
    if comfy_custom_nodes is None:
        raise ValueError("install requires comfy_custom_nodes")
    live = comfy_custom_nodes / "ComfyUI-GVD-QA"
    if live.exists():
        shutil.rmtree(live)
    shutil.copytree(dest, live)
    (live / "TRUST_RECEIPT.txt").write_text(trust_receipt, encoding="utf-8")
    report["installed"] = True
    report["live_path"] = str(live)
    return report
