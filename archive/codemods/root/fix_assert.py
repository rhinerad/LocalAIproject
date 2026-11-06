from pathlib import Path
import re
import sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
pat = r"if any\(k\.startswith\(\"ref_image_\"\) and not k\.startswith\(\"ref_images\.\"\) for k in inputs\):\n            raise GraphBuildError\(\n                f\"node \{nid\}: bare ref_image_N is invalid; use ref_images\.ref_image_N\"\n            \)"
repl = (
    "bare = [k for k in inputs if re.fullmatch(r\"ref_image_\\d+\", str(k))]\n"
    "        if bare:\n"
    "            raise GraphBuildError(\n"
    "                f\"node {nid}: bare {bare} invalid; use ref_images.ref_image_N\"\n"
    "            )"
)
t2, n = re.subn(pat, repl, t, count=1)
if n != 1:
    # try already fixed
    if "re.fullmatch(r\"ref_image_\\d+\"" in t or "re.fullmatch(r'ref_image_\\d+'" in t:
        print("already_ok")
        raise SystemExit(0)
    raise SystemExit(f"replace failed n={n}")
if "import re\n" not in t2 and "import re\r\n" not in t2:
    t2 = t2.replace("from typing import Any, Iterable, Sequence\n", "import re\nfrom typing import Any, Iterable, Sequence\n", 1)
p.write_text(t2, encoding="utf-8")
print("fixed", p)
