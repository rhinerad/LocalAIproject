import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "outputs" / "equal_shares" / "manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("clip_id")
    parser.add_argument("reason")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    record = manifest.get("clips", {}).get(args.clip_id)
    if not record:
        raise SystemExit(f"No manifest record for {args.clip_id}")
    if record.get("status") != "valid":
        raise SystemExit(f"{args.clip_id} is not currently valid")
    record["status"] = "rejected_visual"
    record["visual_rejection_reason"] = args.reason
    record["visual_rejected_at"] = datetime.now().isoformat(timespec="seconds")
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Rejected {args.clip_id}: {args.reason}")


if __name__ == "__main__":
    main()
