"""Phase controller for agent-side still QA. Starts Caption V4 only for qwen_qa."""
from __future__ import annotations

import subprocess
from typing import Any


def nvidia():
    try:
        raw = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            text=True, timeout=8,
        )
        used, free = [int(float(x.strip())) for x in raw.strip().split(",")]
        return {"used_mib": used, "free_mib": free}
    except Exception as exc:
        return {"error": str(exc)}


class CaptionV4Phases:
    def __init__(self, qa, *, start_vlm: bool = True):
        self.qa = qa
        self.start_vlm = start_vlm
        self.vlm = False
        self.peak: list[Any] = []

    def enter(self, phase: str):
        if phase == "generate":
            raise RuntimeError("CaptionV4Phases has no generate worker")
        if phase == "qwen_qa" and self.start_vlm and not self.vlm:
            import vram_controller
            import capabilities
            try:
                vram_controller.comfy_free_memory(unload_models=True, free_memory=True, update_state=False)
            except Exception:
                pass
            vram_controller.prepare_for_vlm("gvd_qa caption v4")
            if not capabilities.ensure_qwen25_vl_runtime(timeout_seconds=150):
                raise RuntimeError("Caption V4 runtime did not come up")
            self.vlm = True
            self.peak.append(nvidia())
        return self.qa

    def idle(self) -> None:
        if self.vlm:
            import vram_controller
            try:
                vram_controller.release_after_vlm("gvd_qa caption v4 complete")
            except Exception:
                pass
            self.vlm = False
            self.peak.append(nvidia())


class HybridPhaseController:
    """Generate on Comfy GPU; score CLIP/WD14/ImageReward on CPU; Caption V4 for qwen."""

    def __init__(self, qa, *, comfy_url: str = "http://127.0.0.1:8188", start_vlm: bool = True,
                 comfy=None):
        self.qa = qa
        self.comfy_url = comfy_url
        self.start_vlm = start_vlm
        self.vlm = False
        self.comfy = comfy
        self.peak: list[Any] = []

    def _comfy_client(self):
        if self.comfy is not None:
            return self.comfy
        if self.comfy is None:
            import importlib.util
            import sys
            from pathlib import Path
            root = Path(__file__).resolve().parents[2]
            spec = importlib.util.spec_from_file_location("_gvd_qa_runner_hybrid", root / "gvd_qa.py")
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            sys.modules.setdefault("_gvd_qa_runner_hybrid", mod)
            spec.loader.exec_module(mod)
            self.comfy = mod.ComfyClient(self.comfy_url)
        return self.comfy

    def _stop_vlm(self) -> None:
        if not self.vlm:
            return
        import vram_controller
        try:
            vram_controller.release_after_vlm("gvd_qa hybrid phase")
        except Exception:
            pass
        self.vlm = False
        self.peak.append(nvidia())

    def _free_comfy(self) -> None:
        import vram_controller
        try:
            vram_controller.comfy_free_memory(unload_models=True, free_memory=True, update_state=False)
        except Exception:
            pass

    def enter(self, phase: str):
        if phase == "generate":
            self._stop_vlm()
            import vram_controller
            try:
                vram_controller.prepare_for_comfyui(reason="gvd_qa generate still")
            except Exception:
                pass
            self.peak.append(nvidia())
            return self._comfy_client()
        self._free_comfy()
        if phase == "qwen_qa" and self.start_vlm and not self.vlm:
            import vram_controller
            import capabilities
            vram_controller.prepare_for_vlm("gvd_qa hybrid caption v4")
            if not capabilities.ensure_qwen25_vl_runtime(timeout_seconds=150):
                raise RuntimeError("Caption V4 runtime did not come up")
            self.vlm = True
            self.peak.append(nvidia())
        return self.qa

    def idle(self) -> None:
        self._stop_vlm()
        self._free_comfy()
        self.peak.append(nvidia())
