from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OLLAMA_GPU_HOST = "http://127.0.0.1:11434"
OLLAMA_CPU_HOST = "http://127.0.0.1:11435"
COMFYUI_HOST = "http://127.0.0.1:8188"
VLM_HOST = "http://127.0.0.1:11436"

RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
VRAM_STATE_PATH = RUNTIME_DIR / "vram_owner.json"


@dataclass
class VramOwner:
    owner: str
    reason: str
    since: float


def _http_json(
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 20.0,
    method: str = "POST",
) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach {url}: {e}") from e


def set_vram_owner(owner: str, reason: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = VRAM_STATE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps({"owner": owner, "reason": reason, "since": time.time()}, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(VRAM_STATE_PATH)


def get_vram_owner() -> dict[str, Any]:
    if not VRAM_STATE_PATH.exists():
        return {"owner": "unknown", "reason": "no state file", "since": None}
    try:
        return json.loads(VRAM_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"owner": "unknown", "reason": "state unreadable", "since": None}


def mark_gpu_idle(reason: str = "released") -> None:
    set_vram_owner("idle", reason)


def wait_for_ollama_unload(host: str = OLLAMA_GPU_HOST, timeout: float = 5.0) -> None:
    """Poll Ollama until it reports no loaded models."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            ps = _http_json(f"{host}/api/ps", method="GET", timeout=2.0)
            if not ps.get("models"):
                return
        except Exception:
            pass
        time.sleep(0.5)


def ollama_chat_once(
    model: str,
    messages: list[dict[str, str]],
    *,
    host: str = OLLAMA_GPU_HOST,
    options: dict[str, Any] | None = None,
    timeout: float = 300.0,
) -> dict[str, Any]:
    set_vram_owner("ollama", f"chat model {model}")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": 0,
    }
    if options:
        payload["options"] = options
    try:
        return _http_json(f"{host}/api/chat", payload, timeout=timeout)
    finally:
        set_vram_owner("ollama_releasing", f"keep_alive=0 sent for {model}")


def ollama_generate_once(
    model: str,
    prompt: str,
    *,
    host: str = OLLAMA_GPU_HOST,
    options: dict[str, Any] | None = None,
    timeout: float = 300.0,
) -> dict[str, Any]:
    set_vram_owner("ollama", f"generate model {model}")
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": 0,
    }
    if options:
        payload["options"] = options
    try:
        return _http_json(f"{host}/api/generate", payload, timeout=timeout)
    finally:
        set_vram_owner("ollama_releasing", f"keep_alive=0 sent for {model}")


def comfy_free_memory(
    *,
    unload_models: bool = True,
    free_memory: bool = True,
    timeout: float = 30.0,
    update_state: bool = True,
) -> dict[str, Any]:
    payload = {"unload_models": unload_models, "free_memory": free_memory}
    result = _http_json(f"{COMFYUI_HOST}/free", payload, timeout=timeout)
    if update_state:
        mark_gpu_idle("ComfyUI /free called")
    return result


def wait_for_vram_headroom(
    *,
    required_free_mib: int = 10240,
    max_used_mib: int = 6144,
    timeout: float = 45.0,
    interval: float = 0.5,
) -> None:
    """Poll nvidia-smi until Comfy/Qwen can load without overlapping."""
    import subprocess

    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            raw = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=5,
            )
            used_s, free_s = raw.strip().splitlines()[0].split(",")
            used = int(float(used_s.strip()))
            free = int(float(free_s.strip()))
            last = {"used_mib": used, "free_mib": free}
            if free >= required_free_mib and used <= max_used_mib:
                return
        except Exception:
            return
        time.sleep(interval)
    raise TimeoutError(f"VRAM headroom not reached before Wan/Qwen handoff: {last}")


_OWNED_VLM_PROC = None


def _vlm_host() -> str:
    return VLM_HOST.replace("http://", "").replace("https://", "")


def _stop_owned_vlm(timeout: float = 15.0) -> None:
    """Stop only the llama-server this controller launched. Never kill strangers."""
    global _OWNED_VLM_PROC
    proc = _OWNED_VLM_PROC
    _OWNED_VLM_PROC = None
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except Exception:
            proc.kill()
            proc.wait(timeout=timeout)
    except Exception:
        pass


def vlm_is_live() -> bool:
    try:
        import llama_cpp_client
        return bool(llama_cpp_client.up(_vlm_host()))
    except Exception:
        return False


def _offload_optimizer_vlm() -> None:
    """Stop Caption V4 started by dspy_optimizer or recorded in runtime state."""
    try:
        import dspy_optimizer
        dspy_optimizer.offload_vlm_vram()
    except Exception:
        pass
    try:
        import capabilities
        state_path = capabilities.QWEN25_VL_RUNTIME_STATE
        if not state_path.is_file():
            return
        state = json.loads(state_path.read_text(encoding="utf-8"))
        pid = int(state.get("pid") or 0)
        server = str(state.get("server") or "")
        expected = str(capabilities.QWEN25_VL_LLAMA_SERVER)
        if pid <= 0 or (server and expected and Path(server) != Path(expected)):
            return
        import subprocess
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, text=True, timeout=20,
        )
        try:
            state_path.unlink()
        except FileNotFoundError:
            pass
    except Exception:
        pass


def prepare_for_comfyui(reason: str = "media generation") -> None:
    """Unload Ollama + owned Qwen, then /free ComfyUI so Wan can occupy the 16 GB card."""
    set_vram_owner("comfyui_pending", reason)
    wait_for_ollama_unload(OLLAMA_GPU_HOST)
    _stop_owned_vlm()
    _offload_optimizer_vlm()
    if vlm_is_live():
        raise RuntimeError(
            "Qwen2.5-VL is live on :11436 without this process's handle; "
            "refusing Wan load to avoid a 16 GB CUDA OOM"
        )
    try:
        comfy_free_memory(unload_models=True, free_memory=True, update_state=False)
    except Exception:
        set_vram_owner("comfyui_pending", "ComfyUI free failed; continuing cautiously")
    mark_comfyui_active(reason)


def mark_comfyui_active(reason: str = "render active") -> None:
    set_vram_owner("comfyui", reason)


def release_after_comfyui(reason: str = "render complete") -> None:
    """Always /free ComfyUI after Wan, even on timeout or failure."""
    try:
        comfy_free_memory(unload_models=True, free_memory=True, update_state=True)
    except Exception:
        mark_gpu_idle(reason)
    try:
        wait_for_vram_headroom()
    except TimeoutError:
        mark_gpu_idle(f"{reason}; VRAM headroom wait timed out")
        raise


def prepare_for_vlm(reason: str = "Qwen2.5-VL judge") -> None:
    set_vram_owner("vlm_pending", reason)
    wait_for_ollama_unload(OLLAMA_GPU_HOST)
    set_vram_owner("vlm", reason)


def release_after_vlm(reason: str = "Qwen2.5-VL complete") -> None:
    """Unload Caption V4 llama.cpp so the next Wan job can load."""
    _stop_owned_vlm()
    _offload_optimizer_vlm()
    try:
        wait_for_vram_headroom()
    except TimeoutError:
        mark_gpu_idle(f"{reason}; VRAM headroom wait timed out")
        raise
    mark_gpu_idle(reason)
