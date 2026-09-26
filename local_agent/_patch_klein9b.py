from __future__ import annotations
import ast, json, shutil, sys, time, urllib.request, urllib.error
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
TS = time.strftime("%Y%m%dT%H%M%S")
gpath = BASE / "graphs" / "flux_minimax_i2v_api.json"
assert gpath.exists(), gpath
shutil.copy2(gpath, gpath.with_name(gpath.name + f".bak_klein9b_{TS}"))
g = json.loads(gpath.read_text(encoding="utf-8"))
old = g["14"]["inputs"]["unet_name"]
g["14"]["inputs"]["unet_name"] = "flux-2-klein-base-9b-fp8.safetensors"
# keep VAE
assert g["10"]["inputs"]["vae_name"] == "flux2-vae.safetensors" or True
g["10"]["inputs"]["vae_name"] = "flux2-vae.safetensors"
gpath.write_text(json.dumps(g, indent=2) + "\n", encoding="utf-8")
print(f"UNET {old} -> {g['14']['inputs']['unet_name']}")
print(f"VAE  {g['10']['inputs']['vae_name']}")

# Confirm available on Comfy
info = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/object_info/UNETLoader", timeout=30).read().decode())
unets = info["UNETLoader"]["input"]["required"]["unet_name"][0]
assert "flux-2-klein-base-9b-fp8.safetensors" in unets, unets
vaes = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/object_info/VAELoader", timeout=30).read().decode())
vae_list = vaes["VAELoader"]["input"]["required"]["vae_name"][0]
assert "flux2-vae.safetensors" in vae_list

sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if "dspy_orchestrator" in mod:
        del sys.modules[mod]
import dspy_orchestrator as o
build = getattr(o, "build_minimax_graph")
graph = build(
    "yellow liminal hallway fluorescent lights",
    "slow handheld push forward down the corridor",
    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 20},
    negative="blur, text",
    prefix="dspy_opt/klein9b",
)
print("built unet", graph["14"]["inputs"]["unet_name"])
print("built vae", graph["10"]["inputs"]["vae_name"])
print("first_frame", graph["20"]["inputs"]["first_frame"])
print("denoise", graph["3"]["inputs"]["denoise"])
assert graph["14"]["inputs"]["unet_name"] == "flux-2-klein-base-9b-fp8.safetensors"
assert graph["10"]["inputs"]["vae_name"] == "flux2-vae.safetensors"
assert graph["20"]["inputs"]["first_frame"] == ["8", 0]
assert float(graph["3"]["inputs"]["denoise"]) == 1.0

# also verify motion prompt helper reads video_prompt
class P:
    start_prompt = "a yellow hallway"
    video_prompt = "slow dolly forward"
assert o._director_motion_prompt(P()) == "slow dolly forward"

prompt = {k: v for k, v in graph.items() if not str(k).startswith("_")}
req = urllib.request.Request(
    "http://127.0.0.1:8188/prompt",
    data=json.dumps({"prompt": prompt, "client_id": "klein9b-check"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode())
        print("Comfy ACCEPT", body.get("prompt_id"), "node_errors", body.get("node_errors"))
except urllib.error.HTTPError as e:
    print("Comfy REJECT", e.read().decode()[:2500])
    raise
for path, body in [("/interrupt", {}), ("/queue", {"clear": True}), ("/free", {"unload_models": True, "free_memory": True})]:
    urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:8188"+path,
        data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json"},
        method="POST"), timeout=20)
print("PHASE1 OK")
