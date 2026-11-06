#!/usr/bin/env python3
"""Write a license-declared C4 JSONL calibration set plus a manifest. No private text."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pipeline_lib import sha256_file, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="calibration directory")
    parser.add_argument("--docs", type=int, default=8000)
    parser.add_argument("--max-chars", type=int, default=8000)
    parser.add_argument("--dataset", default="allenai/c4")
    parser.add_argument("--subset", default="en")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jsonl = out / "sparse_calib.jsonl"
    from datasets import load_dataset

    ds = load_dataset(args.dataset, args.subset, split="train", streaming=True)
    written = 0
    hasher = hashlib.sha256()
    with jsonl.open("w", encoding="utf-8") as handle:
        for row in ds:
            text = (row.get("text") or "").strip()
            if len(text) < 64:
                continue
            line = json.dumps({"prompt": text[: args.max_chars]}, ensure_ascii=False) + "\n"
            handle.write(line)
            hasher.update(line.encode("utf-8"))
            written += 1
            if written >= args.docs:
                break
    manifest = {
        "created_at": utc_now(),
        "source": args.dataset,
        "subset": args.subset,
        "license_note": "C4 is derived from Common Crawl; keep this calibration public/licensed only.",
        "redaction": "no private chats, story assets, or credentials",
        "docs": written,
        "max_chars": args.max_chars,
        "jsonl": str(jsonl),
        "jsonl_sha256": sha256_file(jsonl),
        "streaming_hash": hasher.hexdigest(),
    }
    write_json(out / "calibration_manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
