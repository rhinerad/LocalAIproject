from pathlib import Path

p = Path("local_agent/server.py")
t = p.read_text(encoding="utf-8")
old = 'APP_REVISION = "2026-09-06-flux-photo-intent-r89"'
new = 'APP_REVISION = "2026-09-06-specialist-tool-confirm-r90"'
if old not in t:
    raise SystemExit(f"server revision not found; have: {[line for line in t.splitlines() if 'APP_REVISION' in line][:3]}")
p.write_text(t.replace(old, new, 1), encoding="utf-8")

p = Path("local_agent/START_LOCAL_AGENT_GUI.ps1")
t = p.read_text(encoding="utf-8")
old = "$ExpectedAgentRevision = '2026-09-06-flux-photo-intent-r89'"
new = "$ExpectedAgentRevision = '2026-09-06-specialist-tool-confirm-r90'"
if old not in t:
    raise SystemExit("gui revision not found")
p.write_text(t.replace(old, new, 1), encoding="utf-8")
print("revisions bumped")
