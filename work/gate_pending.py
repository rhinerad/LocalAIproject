import json, pathlib, urllib.request
# try status with long timeout
try:
    with urllib.request.urlopen("http://127.0.0.1:8760/api/status", timeout=180) as resp:
        d = json.loads(resp.read().decode())
    print("rev", d.get("app_revision"))
    gw = d.get("gpu_gateway") or {}
    print("pending", json.dumps(gw.get("pending"), indent=2)[:3000])
except Exception as e:
    print("status failed", type(e).__name__, e)
# also read state file directly
for cand in [
    pathlib.Path("local_agent/runtime/gpu_gate.json"),
    pathlib.Path("work/runtime/gpu_gate.json"),
    pathlib.Path("local_agent/gpu_gate.json"),
]:
    if cand.exists():
        print("FILE", cand)
        print(cand.read_text(encoding="utf-8")[:3000])
