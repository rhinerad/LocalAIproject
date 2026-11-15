from pathlib import Path
import sys
p = Path(sys.argv[1])
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
out = []
i = 0
fixed = False
while i < len(lines):
    line = lines[i]
    if (not fixed) and 'k.startswith("ref_image_") and not k.startswith("ref_images.")' in line:
        # skip this if-block (4 lines expected)
        indent = line[: len(line) - len(line.lstrip())]
        out.append(indent + 'bare = [k for k in inputs if __import__("re").fullmatch(r"ref_image_\\d+", str(k))]\n')
        out.append(indent + "if bare:\n")
        out.append(indent + "    raise GraphBuildError(\n")
        out.append(indent + '        f"node {nid}: bare {bare} invalid; use ref_images.ref_image_N"\n')
        out.append(indent + "    )\n")
        # consume old block lines until we pass the raise block
        while i < len(lines) and "ref_images.ref_image_N" not in lines[i]:
            i += 1
        # consume the closing paren line too
        while i < len(lines) and lines[i].strip() != ")":
            i += 1
        if i < len(lines) and lines[i].strip() == ")":
            i += 1
        fixed = True
        continue
    out.append(line)
    i += 1
if not fixed:
    if any('fullmatch(r"ref_image_\\d+"' in x for x in lines):
        print("already_ok")
        raise SystemExit(0)
    raise SystemExit("did not find target block")
p.write_text("".join(out), encoding="utf-8")
print("fixed")
