import json
import time
import urllib.request

url = "http://127.0.0.1:8760/api/regenerate"
body = json.dumps({"id": "b2542251e7814926", "prefer": "auto"}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
t0 = time.time()
print("POST regenerate start", flush=True)
with urllib.request.urlopen(req, timeout=900) as resp:
    print("status", resp.status, flush=True)
    buf = b""
    events = []
    while True:
        chunk = resp.read(4096)
        if not chunk:
            break
        buf += chunk
        while b"\n\n" in buf:
            frame, buf = buf.split(b"\n\n", 1)
            text = frame.decode("utf-8", "replace")
            events.append(text)
            kind = ""
            data = ""
            for line in text.splitlines():
                if line.startswith("event:"):
                    kind = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
            preview = (data[:160] + "...") if len(data) > 160 else data
            print(f"+{time.time()-t0:.1f}s {kind or '?'}: {preview}", flush=True)
print("DONE elapsed", round(time.time() - t0, 1), "events", len(events), flush=True)
open(r"work/_regen_b254_r87_sse.txt", "w", encoding="utf-8").write("\n\n".join(events))
print("wrote work/_regen_b254_r87_sse.txt", flush=True)
