"""Physical evidence audit; never imports historical PNGs as current successes."""
import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local_agent"))
import capabilities as caps
import prompt_pack_production as prod
from media_accuracy_gate import check_still
from production_integrity import physical_counts, sha256, write_evidence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cid", required=True)
    args = ap.parse_args()
    ledger = prod.load_production(args.cid)
    jobs = prod.build_still_jobs(args.cid)
    report = {"observed_at": time.time(), "conversation_id": args.cid,
              "source_sha256": ledger["source_sha256"], "ledger": ledger,
              "ledger_counts": physical_counts(ledger, prod.load_explicit_approval(args.cid, ledger["source_sha256"])),
              "physical_stills": [], "semantic_check": "not_run", "live_video_example": None}
    for job in jobs:
        directory = ROOT / "outputs/stories/_comfy_output/stories" / job["story"] / "renders"
        for path in sorted(directory.glob("*.png")):
            from PIL import Image
            metadata_match = False
            try:
                with Image.open(path) as image:
                    graph = json.loads(image.info.get("prompt", "{}"))
                metadata_match = any(n.get("class_type") == "CLIPTextEncode" and
                                     n.get("inputs", {}).get("text") == job["prompt"] for n in graph.values())
            except Exception:
                pass
            report["physical_stills"].append({"story": job["story"], "path": str(path),
                "bytes": path.stat().st_size, "sha256": sha256(path),
                "embedded_prompt_matches_current_job": metadata_match,
                "mechanical_qa": check_still(path, job["prompt"], job["clip_id"], job["frame"]),
                "approval_status": "unapproved", "attempt_provenance": "historical_unverified"})
    files = report["physical_stills"]
    report["physical_counts"] = {"png_files": len(files),
        "distinct_still_jobs": len({x["story"] for x in files}),
        "current_prompt_matching_jobs": len({x["story"] for x in files if x["embedded_prompt_matches_current_job"]}),
        "mechanically_passing_jobs": len({x["story"] for x in files if x["mechanical_qa"]["status"] == "pass"}),
        "semantically_passing_jobs": 0, "approved_jobs": report["ledger_counts"]["stills_approved"]}
    identity = {"model": caps.QWEN25_VL_MODEL, "runtime": "llama.cpp",
                "runtime_path": str(caps.QWEN25_VL_LLAMA_SERVER), "loaded_for_this_audit": False}
    for name, path, expected in (("model", caps.QWEN25_VL_GGUF, caps.QWEN25_VL_WEIGHTS_SHA256),
                                 ("projector", caps.QWEN25_VL_MMPROJ, caps.QWEN25_VL_MMPROJ_SHA256)):
        digest = sha256(path) if path.is_file() else None
        identity[name + "_file"] = {"path": str(path), "sha256": digest, "expected_sha256": expected,
                                    "identity_matches": digest == expected}
    server = caps.QWEN25_VL_LLAMA_SERVER
    if server.is_file():
        identity["runtime_sha256"] = sha256(server)
        version = subprocess.run([str(server), "--version"], capture_output=True, text=True, timeout=15)
        identity["version_output"] = (version.stdout + version.stderr).strip()
    report["vlm_identity"] = identity
    dest = prod.production_path(args.cid).parent / "audits" / f"physical_{uuid.uuid4().hex}.json"
    write_evidence(dest, report)
    print(json.dumps({"audit": str(dest), "physical_counts": report["physical_counts"],
                      "ledger_counts": report["ledger_counts"], "vlm_identity": identity}, indent=2))


if __name__ == "__main__":
    main()
