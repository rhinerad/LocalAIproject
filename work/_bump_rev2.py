from pathlib import Path
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
sp = ROOT/"local_agent"/"server.py"
st = sp.read_text(encoding="utf-8")
import re
st2, n = re.subn(
    r'APP_REVISION\s*=\s*"[^"]+"',
    'APP_REVISION = "2026-09-07-managed-prompt-pack-r96"',
    st,
    count=1,
)
print("server replacements", n)
sp.write_text(st2, encoding="utf-8")
ps = ROOT/"local_agent"/"START_LOCAL_AGENT_GUI.ps1"
pt = ps.read_text(encoding="utf-8")
pt2, n2 = re.subn(
    r"\$ExpectedAgentRevision\s*=\s*'[^']+'",
    "$ExpectedAgentRevision = '2026-09-07-managed-prompt-pack-r96'",
    pt,
    count=1,
)
print("launcher replacements", n2)
ps.write_text(pt2, encoding="utf-8")
# verify
for line in sp.read_text(encoding="utf-8").splitlines():
    if "APP_REVISION" in line and "=" in line:
        print(line)
        break
for line in ps.read_text(encoding="utf-8").splitlines():
    if "ExpectedAgentRevision" in line:
        print(line.strip())
        break
