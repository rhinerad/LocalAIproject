from pathlib import Path
import re
raw = Path(r"A:\Users\rhine\.codex\attachments\7a6a1cac-a5cb-4e78-8ad4-beab1bea0e7a\pasted-text.txt").read_bytes()
print("size", len(raw))
print("crlf", raw.count(b"\r\n"), "lf", raw.count(b"\n"), "cr alone", raw.count(b"\r"))
text = raw.decode("utf-8")
idx = text.find("# Backrooms")
text = text[idx:]
print("sample first 500 repr:", repr(text[:500]))
print("has #### C001", "#### C001" in text)
print("newline before ####", "\n#### C001" in text)
# count Start Frame without ^
print("Start Frame count", len(re.findall(r"Start\s+Frame\s*:", text, re.I)))
print("#### C count", len(re.findall(r"#{2,4}\s*C\d{2,4}", text)))
# show around first C001
i = text.find("C001")
print("around C001", repr(text[max(0,i-30):i+80]))
