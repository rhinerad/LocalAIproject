import json, sys, urllib.request
from pathlib import Path

cid = sys.argv[1]
message = sys.argv[2]
out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("audit_sse_out.txt")
prefer = sys.argv[4] if len(sys.argv) > 4 else "cpu"

body = json.dumps({"id": cid, "message": message, "prefer": prefer}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8760/api/send",
    data=body,
    headers={"Content-Type": "application/json"},
)
resp = urllib.request.urlopen(req, timeout=360)
data = resp.read().decode("utf-8", "replace")
out.write_text(data, encoding="utf-8")
print("bytes", len(data))
# print last few SSE events briefly
lines = [ln for ln in data.splitlines() if ln.startswith("data:")]
for ln in lines[-8:]:
    print(ln[:400])
