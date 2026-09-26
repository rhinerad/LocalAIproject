#!/usr/bin/env python3
"""Initialize or inspect the PowerInfer vault. Does not load GPU or delete evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import vault


def _vault(args: argparse.Namespace) -> Path:
    return Path(args.vault) if args.vault else vault.default_vault_path()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default="", help="override path; default D:\\PowerInferModels when possible")
    parser.add_argument("--allow-in-repo", action="store_true", help="test-only; refuse this in production")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create production/quarantine/scratch/private/keys")
    pre = sub.add_parser("preflight", help="refuse if free disk is below need plus 20%")
    pre.add_argument("--need-bytes", type=int, default=0)
    pre.add_argument("--model-id", default="")
    pre.add_argument("--source-bytes", type=int, default=0)

    bundle = sub.add_parser("create-bundle")
    bundle.add_argument("--model-id", required=True)
    bundle.add_argument("--build-id", required=True)
    bundle.add_argument("--force", action="store_true")

    prot = sub.add_parser("protect-source")
    prot.add_argument("--source", required=True)

    enc = sub.add_parser("encrypt")
    enc.add_argument("--file", required=True)
    enc.add_argument("--label", required=True)

    dec = sub.add_parser("decrypt")
    dec.add_argument("--envelope", required=True)
    dec.add_argument("--dest", required=True)

    sub.add_parser("status")

    args = parser.parse_args()
    root = _vault(args)

    if args.cmd == "init":
        print(json.dumps(vault.init_vault(root, allow_in_repo=args.allow_in_repo), indent=2))
        return 0
    if args.cmd == "preflight":
        need = args.need_bytes
        extra = {}
        if args.model_id:
            extra = vault.estimate_bundle_bytes(args.model_id, source_bytes=args.source_bytes)
            need = extra["need_bytes"]
        report = vault.preflight(root, need_bytes=need)
        report["estimate"] = extra or None
        print(json.dumps(report, indent=2))
        return 0
    if args.cmd == "create-bundle":
        paths = vault.create_bundle(root, args.model_id, args.build_id, force=args.force)
        print(json.dumps({k: str(v) for k, v in paths.items()}, indent=2))
        return 0
    if args.cmd == "protect-source":
        print(json.dumps(vault.protect_source(Path(args.source), root), indent=2, default=str))
        return 0
    if args.cmd == "encrypt":
        print(json.dumps(vault.encrypt_private(root, Path(args.file), label=args.label), indent=2))
        return 0
    if args.cmd == "decrypt":
        print(json.dumps(vault.decrypt_private(root, Path(args.envelope), Path(args.dest)), indent=2))
        return 0
    if args.cmd == "status":
        meta = {}
        marker = root / "vault.json"
        if marker.exists():
            meta = json.loads(marker.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "vault": str(root),
                    "exists": root.exists(),
                    "preferred": str(vault.PREFERRED_VAULT),
                    "default": str(vault.default_vault_path()),
                    "meta": meta,
                    "disk": vault.disk_status(root) if root.exists() or root.parent.exists() else None,
                },
                indent=2,
            )
        )
        return 0
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
