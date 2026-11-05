import json, time, subprocess, urllib.request
from pathlib import Path

out = {}
root = Path(r"A:/Users/rhine/Documents/Codex/2026-08-07/referenced-chatgpt-conversation-this-is-an-2/COMFYUI_STORY_HANDOFF_2026-08-09")

ns = ""
try:
    ns = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
    listen_pids = []
    for line in ns.splitlines():
        if ":8760" in line and "LISTENING" in line:
            parts = line.split()
            if parts:
                listen_pids.append(parts[-1])
    out["port_listening"] = bool(listen_pids)
    out["listener_pids"] = listen_pids
except Exception as e:
    out["port_error"] = str(e)
    listen_pids = []

pid = listen_pids[0] if listen_pids else None
if pid:
    try:
        ps = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    f"$p=Get-Process -Id {pid} -ErrorAction Stop; "
                    f"$w=Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\"; "
                    "Write-Output (($p.ProcessName)+'|'+($p.StartTime.ToString('g'))+'|'+"
                    "([math]::Round($p.WorkingSet64/1MB,1).ToString())+'|'+$w.CommandLine)"
                ),
            ],
            text=True,
            errors="ignore",
            timeout=20,
        )
        out["proc"] = ps.strip()
    except Exception as e:
        out["proc_error"] = str(e)

t0 = time.time()
try:
    req = urllib.request.urlopen("http://127.0.0.1:8760/api/status", timeout=25)
    body = req.read().decode("utf-8", errors="replace")
    out["status_http"] = req.status
    out["status_ms"] = int((time.time() - t0) * 1000)
    out["status_body"] = body
except Exception as e:
    out["status_error"] = str(e)
    out["status_ms"] = int((time.time() - t0) * 1000)

try:
    out["comfy_8188"] = any(":8188" in line and "LISTENING" in line for line in ns.splitlines())
except Exception:
    out["comfy_8188"] = False

try:
    gpu = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        errors="ignore",
        timeout=10,
    )
    out["nvidia"] = gpu.strip()
except Exception as e:
    out["nvidia"] = str(e)

try:
    oreq = urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=5)
    out["ollama_ps"] = oreq.read().decode("utf-8", errors="replace")
except Exception as e:
    out["ollama_ps"] = f"unreachable:{e}"

owner = root / "work" / "image_render_owner.json"
out["image_render_owner_exists"] = owner.exists()
if owner.exists():
    out["image_render_owner"] = owner.read_text(encoding="utf-8", errors="replace")

mq = root / "work" / "media_queue"
if mq.exists():
    pending = mq / "pending"
    processing = mq / "processing"
    out["media_queue_pending"] = len(list(pending.iterdir())) if pending.exists() else 0
    out["media_queue_processing"] = len(list(processing.iterdir())) if processing.exists() else 0
else:
    out["media_queue"] = "absent"

print(json.dumps(out))
