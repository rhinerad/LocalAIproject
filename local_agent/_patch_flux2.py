from __future__ import annotations
import ast, json, re, shutil, sys, time, urllib.request, urllib.error
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
TS = time.strftime("%Y%m%dT%H%M%S")

# Locate graph JSON (directive path + known variants)
cands = [
    BASE / "graphs" / "flux_minimax_i2v_api.json",
    BASE / "graphs" / "flux_minimax_i2v_api.json",
    BASE / "graphs" / "flux_minimax_i2v_api.json",
]
# also search
found = list(BASE.glob("**/flux*minimax*.json")) + list(BASE.glob("**/graphs/*.json"))
print("found graphs:", [str(p.relative_to(BASE)) for p in found])
gpath = None
for p in found:
    try:
        g = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    n14 = g.get("14") or {}
    if isinstance(n14, dict) and n14.get("class_type") == "UNETLoader":
        gpath = p
        print("using", p)
        break
assert gpath, "graph not found"

g = json.loads(gpath.read_text(encoding="utf-8"))
shutil.copy2(gpath, gpath.with_name(gpath.name + f".bak_flux2_{TS}"))

# Phase 1 patches
assert g["14"]["class_type"] == "UNETLoader"
old_unet = g["14"]["inputs"]["unet_name"]
g["14"]["inputs"]["unet_name"] = "flux2_dev_fp8mixed.safetensors"
assert g["10"]["class_type"] == "VAELoader"
old_vae = g["10"]["inputs"]["vae_name"]
g["10"]["inputs"]["vae_name"] = "flux2-vae.safetensors"
print(f"UNET {old_unet} -> {g['14']['inputs']['unet_name']}")
print(f"VAE  {old_vae} -> {g['10']['inputs']['vae_name']}")

# FLUX.2 often needs mistral text encoder; check DualCLIPLoader and adjust if present
n11 = g.get("11")
if isinstance(n11, dict) and n11.get("class_type") == "DualCLIPLoader":
    print("clip node11 before", n11["inputs"])
    # Prefer FLUX2-native text encoder if graph still has FLUX.1 T5+clip_l
    clips = n11["inputs"]
    if clips.get("clip_name1") == "t5xxl_fp16.safetensors" or clips.get("type") == "flux":
        # Keep type flux if Comfy accepts; try mistral for flux2
        # DualCLIPLoader for classic flux wants t5+clip_l; flux2_dev may need different.
        # We'll validate with Comfy after save; if 400 on clip, patch then.
        pass

gpath.write_text(json.dumps(g, indent=2) + "\n", encoding="utf-8")
print("saved", gpath)

# Ensure orchestrator first_frame + denoise locks still good
sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if "dspy_orchestrator" in mod or "generalized_video_director" in mod:
        del sys.modules[mod]
import dspy_orchestrator as o

# confirm force_frame_length doesn't smash first_frame
src = Path(o.__file__).read_text(encoding="utf-8")
assert "first_frame" in src.split("def _force_frame_length")[1][:1500]
build = getattr(o, "build_minimax_graph", None) or getattr(o, "build_flux_minimax_graph")
g2 = build(
    "yellow liminal hallway, fluorescent lights, VHS grain",
    "slow handheld push forward down the corridor",
    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 20},
    negative="blur, text",
    prefix="dspy_opt/flux2check",
)
print("built unet", g2["14"]["inputs"]["unet_name"])
print("built vae", g2["10"]["inputs"]["vae_name"])
print("first_frame", g2["20"]["inputs"]["first_frame"])
print("length", g2["20"]["inputs"].get("length") or g2["20"]["inputs"].get("num_frames"))
print("denoise", g2["3"]["inputs"]["denoise"])
assert g2["14"]["inputs"]["unet_name"] == "flux2_dev_fp8mixed.safetensors"
assert g2["10"]["inputs"]["vae_name"] == "flux2-vae.safetensors"
assert g2["20"]["inputs"]["first_frame"] == ["8", 0]
assert float(g2["3"]["inputs"]["denoise"]) == 1.0

# Validate with Comfy
prompt = {k: v for k, v in g2.items() if not str(k).startswith("_")}
req = urllib.request.Request(
    "http://127.0.0.1:8188/prompt",
    data=json.dumps({"prompt": prompt, "client_id": "flux2-check"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode())
        print("Comfy ACCEPT", body.get("prompt_id"), "node_errors", body.get("node_errors"))
        accepted = True
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print("Comfy REJECT", e.code)
    print(body[:3000])
    accepted = False
    err = json.loads(body) if body.startswith("{") else {}
    # If clip mismatch, try patching DualCLIP for flux2
    node_errors = (err.get("node_errors") or {})
    if "11" in node_errors or any("clip" in json.dumps(node_errors).lower() for _ in [0]):
        print("Attempting FLUX2 clip patch...")
        raw = json.loads(gpath.read_text(encoding="utf-8"))
        if raw.get("11", {}).get("class_type") == "DualCLIPLoader":
            # Common Comfy FLUX2 setup: DualCLIPLoader with mistral + clip_l type flux2 if available
            # Check object_info for allowed type values
            info = json.loads(urllib.request.urlopen("http://127.0.0.1:8188/object_info/DualCLIPLoader", timeout=30).read().decode())
            types = info["DualCLIPLoader"]["input"]["required"]["type"][0]
            print("clip types", types)
            clips1 = info["DualCLIPLoader"]["input"]["required"]["clip_name1"][0]
            # Prefer mistral flux2 if present
            prefer = "mistral_3_small_flux2_bf16.safetensors"
            if prefer in clips1:
                raw["11"]["inputs"]["clip_name1"] = prefer
                raw["11"]["inputs"]["clip_name2"] = "clip_l.safetensors"
                if "flux2" in types:
                    raw["11"]["inputs"]["type"] = "flux2"
                elif "flux" in types:
                    raw["11"]["inputs"]["type"] = "flux"
                gpath.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
                print("patched clip11", raw["11"]["inputs"])
                # rebuild
                for mod in list(sys.modules):
                    if "dspy_orchestrator" in mod:
                        del sys.modules[mod]
                import dspy_orchestrator as o2
                build2 = getattr(o2, "build_minimax_graph", None) or getattr(o2, "build_flux_minimax_graph")
                g3 = build2(
                    "yellow liminal hallway",
                    "slow handheld push forward",
                    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 20},
                    negative="blur",
                    prefix="dspy_opt/flux2check2",
                )
                prompt = {k: v for k, v in g3.items() if not str(k).startswith("_")}
                req = urllib.request.Request(
                    "http://127.0.0.1:8188/prompt",
                    data=json.dumps({"prompt": prompt, "client_id": "flux2-check2"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        body = json.loads(resp.read().decode())
                        print("Comfy ACCEPT after clip patch", body.get("prompt_id"))
                        accepted = True
                except urllib.error.HTTPError as e2:
                    print("still reject", e2.read().decode()[:3000])
                    accepted = False

# Clear queue after validation enqueue
for path, body in [("/interrupt", {}), ("/queue", {"clear": True}), ("/free", {"unload_models": True, "free_memory": True})]:
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                "http://127.0.0.1:8188" + path,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=20,
        )
    except Exception as ex:
        print("cleanup", path, ex)

print("VALIDATION", "OK" if accepted else "FAIL")
if not accepted:
    raise SystemExit(2)
print("PHASE1 DONE", gpath)
