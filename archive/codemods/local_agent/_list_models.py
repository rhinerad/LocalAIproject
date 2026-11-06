import json, urllib.request
from pathlib import Path
BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")

# object_info for UNETLoader / DualCLIPLoader / VAELoader / MiniMax
info = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/object_info", timeout=60).read().decode())
for name in ["UNETLoader", "DualCLIPLoader", "VAELoader", "CheckpointLoaderSimple", "MiniMaxH3ImageToVideo"]:
    node = info.get(name)
    if not node:
        print(name, "MISSING")
        continue
    inputs = node.get("input", {}).get("required", {})
    print("===", name, "===")
    for k,v in inputs.items():
        print(" ", k, v if not isinstance(v, list) or len(str(v))<300 else (v[0] if isinstance(v,list) else v)[:50] if False else str(v)[:400])

# list flux-like unets from UNETLoader
unet = info["UNETLoader"]["input"]["required"]["unet_name"][0]
flux = [u for u in unet if "flux" in u.lower()]
print("FLUX unets:", flux)
vae = info["VAELoader"]["input"]["required"]["vae_name"][0]
print("VAE flux-ish:", [v for v in vae if any(x in v.lower() for x in ("ae","flux","sdxl","vae")) ][:20])
clip = info["DualCLIPLoader"]["input"]["required"]["clip_name1"][0]
print("CLIP1 sample:", [c for c in clip if any(x in c.lower() for x in ("t5","clip_l","flux"))][:20])

# current graph filenames
g = json.loads((BASE/"graphs"/"flux_minimax_i2v_api.json").read_text(encoding="utf-8"))
for nid in ("14","11","10","31","32"):
    print("graph node", nid, g.get(nid))
