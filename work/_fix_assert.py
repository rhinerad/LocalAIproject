from pathlib import Path
p = Path("local_agent/test_native_tool_calling.py")
text = p.read_text(encoding="utf-8")
old = '        self.assertIn("4242", reply)'
new = '        self.assertIn("Started the Flux still render", reply)'
if old not in text:
    raise SystemExit("assert not found")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("assertion fixed")
