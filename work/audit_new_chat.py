import json, urllib.request
body = json.dumps({
    "first": "audit placeholder",
    "model": "huihui_ai/qwen3-abliterated:8b",
    "workspace": "general",
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8760/api/new",
    data=body,
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(req, timeout=60).read().decode())
