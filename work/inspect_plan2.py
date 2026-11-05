import json, pathlib, glob
p = pathlib.Path("local_agent/chats/5404c50e34aa4e53.json")
d = json.loads(p.read_text(encoding="utf-8"))
m = d["messages"][1]
for row in m.get("tool_evidence") or []:
    if row.get("tool") == "plan_story_image":
        s = row.get("summary") or ""
        print(s)
        print("--- next_step ---")
        print(row.get("next_step"))
# find any planned graph/json for this story
for path in pathlib.Path(".").rglob("*vhs_liminal*"):
    if path.is_file() and path.suffix.lower() in {".json",".png",".txt",".md",".log"}:
        print("FILE", path)
