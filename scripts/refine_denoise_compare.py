#!/usr/bin/env python3
"""Tune REFINE_DENOISE: refine one real chained frame at several denoise values.

The refine checkpoint (batch_run_backrooms_gvd.py --continuity live, at the
chain ceiling) img2img-refines the previous clip's last frame with FLUX before
MiniMax animates it. This renders ONLY that FLUX refine step (stills-only
graph: LoadImage -> ImageScale -> VAEEncode -> KSampler -> VAEDecode ->
SaveImage), once per --denoise, conditioned on the clip's own batch prompts,
so the stills can be compared by eye against the unrefined frame:
same character/pose/scene, less codec softness? Too high a denoise is a fresh
generation in the old pose; too low cleans nothing.

Requires the ComfyUI backend (Rockernow, :8188) to be ALREADY running and idle;
this never starts one (CLAUDE.md "One backend, ever"). FLUX only, no MiniMax.

Example (C013 refined from C012's rendered MP4):
  python scripts/refine_denoise_compare.py --clip C013 ^
      --source-video "A:\\Users\\rhine\\ComfyUI-Shared\\output\\dspy_opt\\gvd_br_c012_....mp4" ^
      --denoise 0.2 --denoise 0.35

Writes local_agent/runtime/gvd_backrooms_batch/refine_tuning/<clip>_<stamp>.json
with the source frame and one output PNG per denoise value.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "local_agent"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import batch_run_backrooms_gvd as batch  # noqa: E402

OUT_DIR = batch.PROGRESS_DIR / "refine_tuning"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clip", required=True, help="Clip whose prompts condition the refine, e.g. C013")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--source-video", help="Rendered previous-clip MP4; its last frame is refined")
    src.add_argument("--frame", help="An already-extracted frame PNG to refine")
    ap.add_argument("--denoise", type=float, action="append",
                    help="Repeatable. Default: 0.2 and 0.35 (the spec's comparison pair)")
    ap.add_argument("--sharpen", type=float, default=0.0, help="ImageSharpen alpha after decode (0 = off)")
    ap.add_argument("--pack", default=str(batch.DEFAULT_PACK))
    args = ap.parse_args(argv)
    values = args.denoise or [0.2, 0.35]
    for d in values:
        if not 0.0 < d < 1.0:
            ap.error(f"--denoise must be between 0 and 1 exclusive, got {d}")

    import comfy_api
    import generate_video as gv
    import video_chain

    if not comfy_api.ping(gv.DEFAULT_COMFY):
        print(f"ComfyUI is not listening on {gv.DEFAULT_COMFY}. Start Rockernow first; "
              "this script never starts a backend.", file=sys.stderr)
        return 2
    cid = args.clip.upper()
    clips = batch.ingest_pack(Path(args.pack))
    clip = next((c for c in clips if str(c.get("id") or "").upper() == cid), None)
    if clip is None:
        ap.error(f"{cid} not in pack {args.pack}")
    override = batch.load_clip_override(cid)
    if batch.wants_literal(override):
        pred, hparams = batch.pred_from_override(override, clip)
    else:
        pred, hparams = batch.clip_to_pred_and_hparams(clip)
    batch.apply_pipeline_rules(pred, clip, cid, override)

    frame = (
        video_chain.extract_last_frame(Path(args.source_video)) if args.source_video else Path(args.frame)
    )
    comfy_name = video_chain.upload_to_comfy_input(
        frame, url=gv.DEFAULT_COMFY, name=f"refine_tune_{cid.lower()}_{frame.name}"
    )
    print(f"source frame {frame} -> comfy input {comfy_name}")

    report = {
        "clip": cid,
        "source_video": args.source_video,
        "source_frame": str(frame),
        "sharpen_alpha": args.sharpen,
        "start_prompt": str(pred.start_prompt),
        "results": [],
    }
    for d in values:
        print(f"\n--- refine denoise {d} ---")
        t0 = time.time()
        out = gv.submit_comfy(
            pred,
            hparams,
            clip_id=f"refine_tune_{cid.lower()}_d{round(d * 100):02d}",
            category=batch.DEFAULT_CATEGORY,
            stills_only=True,
            refine_frame_path=comfy_name,
            refine_denoise=d,
            refine_sharpen_alpha=args.sharpen,
        )
        report["results"].append({"denoise": d, "png": str(out), "seconds": round(time.time() - t0, 1)})
        print(f"  denoise {d}: {out}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{cid}_{time.strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nCompare against the unrefined frame {frame}\nreport -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
