import json, pathlib, time
p = pathlib.Path("local_agent/chats/5404c50e34aa4e53.json")
d = json.loads(p.read_text(encoding="utf-8"))
print("n_msgs", len(d["messages"]))
print("updated", d.get("updated"))
for i,m in enumerate(d["messages"]):
    print("====", i, m.get("role"))
    print((m.get("content") or "")[:500])
    te = m.get("tool_evidence") or []
    for row in te[:5]:
        print("  tool", row.get("tool"), row.get("outcome"), (row.get("summary") or "")[:300])
