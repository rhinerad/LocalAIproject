import json, pathlib
gate = json.loads(pathlib.Path("local_agent/runtime/gpu_gate.json").read_text(encoding="utf-8"))
print("pending:", [(p.get("id"), p.get("workload")) for p in gate.get("pending") or []])
for h in (gate.get("history") or [])[-5:]:
    print("hist", h.get("id"), h.get("workload"), h.get("decision"))
# any pngs?
from pathlib import Path
outs = list(Path("outputs/stories").rglob("*.png")) if Path("outputs/stories").exists() else []
print("pngs", len(outs))
for p in outs[:10]:
    print(p, p.stat().st_size)
runtime = Path("work/runtime/image_render_runtime")
if runtime.exists():
    pngs2 = list(runtime.rglob("*.png"))
    print("runtime pngs", len(pngs2))
    for p in pngs2[:10]:
        print(p, p.stat().st_size)
