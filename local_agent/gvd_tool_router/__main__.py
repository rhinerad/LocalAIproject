"""CLI: python -m gvd_tool_router --inventory"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python local_agent/gvd_tool_router/...` and package execution.
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from gvd_tool_router.catalog_seed import write_seed_catalog
    from gvd_tool_router.inventory import bootstrap
    from gvd_tool_router.paths import GvdLayout
    from gvd_tool_router.service import ensure_control_plane
else:
    from .catalog_seed import write_seed_catalog
    from .inventory import bootstrap
    from .paths import GvdLayout
    from .service import ensure_control_plane


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GVD tool router control plane")
    parser.add_argument("--gvd-root", default=None)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--seed-catalog", action="store_true")
    args = parser.parse_args(argv)
    layout = GvdLayout.from_env(args.gvd_root)
    if args.seed_catalog:
        write_seed_catalog(layout)
        print(str(layout.catalog_json))
    if args.inventory:
        report = bootstrap(layout)
        print(json.dumps({
            "gpu": (report.get("environment") or {}).get("gpu"),
            "comfy_commit": (report.get("environment") or {}).get("comfy_commit"),
            "paths": report.get("paths"),
        }, indent=2))
        return 0
    ensure_control_plane(layout)
    print(str(layout.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
