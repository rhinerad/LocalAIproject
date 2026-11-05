import json, pathlib
p = pathlib.Path("local_agent/chats/5404c50e34aa4e53.json")
d = json.loads(p.read_text(encoding="utf-8"))
m = d["messages"][1]
for row in m.get("tool_evidence") or []:
    if row.get("tool") == "plan_story_image":
        print((row.get("summary") or "")[:2000])
