import json, urllib.request
from pathlib import Path
info = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/object_info", timeout=60).read().decode())
# find minimax nodes
mm = [k for k in info if "minimax" in k.lower() or "MiniMax" in k]
print("minimax nodes", mm)
for k in mm:
    node = info[k]
    print("====", k, "====")
    print("required", json.dumps(node.get("input",{}).get("required",{}), indent=2)[:2000])
    print("optional", json.dumps(node.get("input",{}).get("optional",{}), indent=2)[:2000])
    print("outputs", node.get("output"))

# all unets
unets = info["UNETLoader"]["input"]["required"]["unet_name"][0]
print("ALL UNETS count", len(unets))
for u in unets:
    if any(x in u.lower() for x in ("flux","schnell","dev")):
        print(" ", u)

# search diffusion_models folder via filesystem common paths
from pathlib import Path
roots = [
 Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\models"),
 Path(r"A:\Users\rhine\ComfyUI\models"),
]
for r in roots:
    if not r.exists():
        print("missing", r); continue
    print("root", r)
    for sub in ("diffusion_models","unet","checkpoints","vae","clip","text_encoders"):
        d = r/sub
        if d.exists():
            hits = [p.name for p in d.rglob("*.safetensors") if "flux" in p.name.lower() or "ae." in p.name.lower()]
            print(" ", sub, hits[:30], "totalflux", len(hits))
