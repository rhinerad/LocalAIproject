"""One bounded real startup through the production path; no graph submission."""
import json
import argparse
import time
import uuid
import image_render as ir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=45)
    args = ap.parse_args()
    dest = ir.ROOT / "work/runtime/startup_diagnostics" / ("verified_" + uuid.uuid4().hex)
    dest.mkdir(parents=True, exist_ok=False)
    report = {"started_at": time.time(), "ready": False, "submitted_graphs": 0}
    proc = None
    claimed = False
    try:
        ir.preflight_execute()
        ir._write_owner()
        claimed = True
        proc = ir._start_owned_backend(startup_timeout=args.seconds)
        report.update(ready=True, object_info_nodes=len(ir.object_info()), pid=proc.pid,
                      elapsed_seconds=time.time() - report["started_at"])
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        try:
            ir._stop_owned_backend(proc)
            if claimed:
                ir._release_owner()
        except Exception as exc:
            report["cleanup_error"] = str(exc)
        report["port_released"] = not ir._port_open()
        (dest / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(dest / "report.json"), **report}, indent=2))
    return 0 if report["ready"] and report["port_released"] and not report.get("cleanup_error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
