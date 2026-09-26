#!/usr/bin/env python3
"""QA workstation bootstrap. Never starts Comfy, never installs custom nodes."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))

from gvd_qa.stage_adapters import stage_comfy_gvd_qa
from gvd_qa.validate import qa_activation_report
from gvd_qa.wd14_cpu import write_qa_worker_wd14_settings
from gvd_tool_router.family_profiles import scan_families
from gvd_tool_router.inventory import DEFAULT_COMFY_ROOT, DEFAULT_COMFY_URL, _nvidia_query

OUT = ROOT / "local_agent" / "runtime" / "gvd_qa"


def _http(url: str, timeout: float = 4.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read()
            if resp.status != 200:
                return None
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {"raw": raw[:200].decode("utf-8", "replace")}
    except Exception as exc:
        return {"error": type(exc).__name__, "detail": str(exc)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    gpu = _nvidia_query()
    object_info = _http(DEFAULT_COMFY_URL.rstrip("/") + "/object_info")
    if isinstance(object_info, dict) and object_info.get("error"):
        object_info_ok = None
        comfy = {"up": False, **object_info}
    elif isinstance(object_info, dict) and object_info:
        object_info_ok = object_info
        comfy = {"up": True, "class_count": len(object_info)}
        (OUT / "object_info.json").write_text(json.dumps(object_info, indent=2), encoding="utf-8")
    else:
        object_info_ok = None
        comfy = {"up": False}
    activation = qa_activation_report(object_info_ok if isinstance(object_info_ok, dict) else {})
    families = scan_families(DEFAULT_COMFY_ROOT)
    staged = stage_comfy_gvd_qa(
        quarantine_dir=OUT / "quarantine",
        object_info=object_info_ok if isinstance(object_info_ok, dict) else {},
        install=False,
    )
    wd14 = write_qa_worker_wd14_settings(OUT / "wd14_cpu_pysssss.json")
    vlm = _http("http://127.0.0.1:11436/v1/models")
    ollama = _http("http://127.0.0.1:11434/api/ps")
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "gpu": gpu,
        "comfy": comfy,
        "ollama": ollama,
        "caption_v4": vlm,
        "families": families,
        "activation": activation,
        "staged_adapters": staged,
        "wd14_cpu_settings": str(wd14),
        "note": (
            "ComfyUI was not started. GVD adapters quarantine copy refreshed. "
            "Live install is a separate trust-receipt path. CLIP floors live in "
            "profiles/provisional_loop_labels_v1.json (3-image split, not production calibration)."
        ),
    }
    dest = OUT / "bootstrap.json"
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "wrote": str(dest),
        "comfy_up": comfy.get("up"),
        "gpu_free_mib": gpu.get("memory_free_mib"),
        "activable": activation.get("activable"),
        "missing": activation.get("missing"),
        "staged": staged.get("staged"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
