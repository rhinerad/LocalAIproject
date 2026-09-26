#!/usr/bin/env python3
"""Snapshot a Hugging Face repo into a hashed source directory. Does not load GPU."""
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline_lib import sha256_tree, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=args.repo, local_dir=str(dest), local_dir_use_symlinks=False)
    write_json(
        dest.parent / "source_manifest.json",
        {
            "created_at": utc_now(),
            "repo": args.repo,
            "dest": str(dest),
            "tree": sha256_tree(dest),
        },
    )
    print("downloaded", args.repo, "->", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
