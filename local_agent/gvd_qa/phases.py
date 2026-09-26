"""PhaseController using the GVD GPU lease. enter() is never a no-op."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from gvd_tool_router.gpu_lease import acquire
from gvd_tool_router.paths import GvdLayout

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("_gvd_qa_runner", ROOT / "gvd_qa.py")
_RUNNER = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["_gvd_qa_runner"] = _RUNNER
_SPEC.loader.exec_module(_RUNNER)
ComfyClient = _RUNNER.ComfyClient
QAError = _RUNNER.QAError
free_idle_comfy = _RUNNER.free_idle_comfy
unload_owned_ollama = _RUNNER.unload_owned_ollama


ALLOWED_PHASES = ("generate", "fast_qa", "qwen_qa", "reward_qa")
DEFAULT_HEADROOM_MIB = 2048


class LeasePhaseController:
    """Admits one phase at a time under the existing GPU lease."""

    def __init__(
        self,
        *,
        layout: GvdLayout | None = None,
        comfy_url: str = "http://127.0.0.1:8188",
        ollama_url: str = "http://127.0.0.1:11434",
        owned_ollama_model: str | None = None,
        job_id: str = "gvd-qa",
        attempt_id: str = "qa",
        session: Any | None = None,
        client_factory=None,
        skip_live_free: bool = False,
        phase_urls: dict[str, str] | None = None,
        min_headroom_mib: int = DEFAULT_HEADROOM_MIB,
        free_vram_mib: int | None = None,
    ) -> None:
        self.layout = layout or GvdLayout.from_env()
        self.comfy_url = comfy_url
        self.ollama_url = ollama_url
        self.owned_ollama_model = owned_ollama_model
        self.job_id = job_id
        self.attempt_id = attempt_id
        self.session = session
        self.client_factory = client_factory or (lambda url: ComfyClient(url))
        self.skip_live_free = skip_live_free
        self.phase_urls = phase_urls or {}
        self.min_headroom_mib = min_headroom_mib
        self.free_vram_mib = free_vram_mib
        self._cm = None
        self._lease = None
        self._phase: str | None = None

    def _url_for(self, phase: str) -> str:
        return self.phase_urls.get(phase) or self.comfy_url

    def enter(self, phase: str) -> ComfyClient:
        if phase not in ALLOWED_PHASES:
            raise QAError(f"unknown QA phase {phase!r}")
        if self.free_vram_mib is not None and self.free_vram_mib < self.min_headroom_mib:
            raise QAError("RESOURCE_BLOCKED: free VRAM below 2GiB reserve")
        if self._cm is not None:
            self._cm.__exit__(None, None, None)
            self._cm = None
        self._cm = acquire(
            self.layout,
            job_id=self.job_id,
            attempt_id=f"{self.attempt_id}:{phase}",
            family_key=f"qa_{phase}",
        )
        self._lease = self._cm.__enter__()
        if not self.skip_live_free and self.session is not None:
            if self.owned_ollama_model:
                unload_owned_ollama(self.session, self.ollama_url, self.owned_ollama_model)
            if phase != "generate":
                free_idle_comfy(self.session, self._url_for("generate"))
        self._phase = phase
        return self.client_factory(self._url_for(phase))

    def idle(self) -> None:
        if not self.skip_live_free and self.session is not None:
            try:
                free_idle_comfy(self.session, self._url_for(self._phase or "generate"))
            except QAError:
                pass
        if self._cm is not None:
            self._cm.__exit__(None, None, None)
            self._cm = None
        self._phase = None
        self._lease = None
