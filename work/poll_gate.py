import json, time, pathlib, urllib.request
gate = pathlib.Path("local_agent/runtime/gpu_gate.json")
wanted = "gpu_a38b751666c5"
for i in range(36):
    data = json.loads(gate.read_text(encoding="utf-8"))
    pending_ids = [p.get("id") for p in data.get("pending") or []]
    hist = {h.get("id"): h for h in data.get("history") or []}
    if wanted not in pending_ids:
        h = hist.get(wanted)
        print("RESOLVED", wanted, h)
        break
    if i % 6 == 0:
        print(f"still pending {wanted} ({i*5}s)")
    time.sleep(5)
else:
    print("STILL_PENDING", wanted)
