"""VHS / found-footage post-processor (FFmpeg).

Standalone helper: optionally bake a subtle 1990s camcorder look *after*
generation. Diffusion denoise strips grain/scan texture; this restores it
in pixel space when explicitly enabled.

P1-F: REC overlay / effects are optional finishing — OFF by default or gated.
Not wired into the live orchestrator as always-on.
See PATCH_vhs_pipeline.md for the intended call site.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def _ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise FileNotFoundError(
            "ffmpeg not found on PATH. Install FFmpeg and retry."
        )
    return found


def finishing_enabled(
    *,
    enabled: bool | None = None,
    env_var: str = "GVD_VHS_FINISHING",
) -> bool:
    """Resolve whether VHS finishing should run.

    Priority: explicit ``enabled`` arg > env ``GVD_VHS_FINISHING`` > False.
    Env truthy values: 1/true/yes/on.
    """
    if enabled is not None:
        return bool(enabled)
    raw = (os.environ.get(env_var) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def apply_vhs_look(
    input_mp4: str | Path,
    output_mp4: str | Path,
    *,
    grain: int = 15,
    chroma_shift: float = 1.2,
    rec_blink_hz: float = 1.0,
    enabled: bool | None = None,
    rec_overlay: bool = False,
    effects: bool = True,
) -> Path | None:
    """Optionally apply grain, mild chromatic fringe, and/or a blinking REC overlay.

    Returns the path to the newly written MP4, or None if finishing is disabled
    (caller should keep the clean source).

    P1-F defaults:
      - finishing off unless ``enabled=True`` or env GVD_VHS_FINISHING
      - REC overlay off unless ``rec_overlay=True``
    """
    if not finishing_enabled(enabled=enabled):
        return None

    src = Path(input_mp4).expanduser().resolve()
    dst = Path(output_mp4).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"input video not found: {src}")
    if src == dst:
        raise ValueError("output_mp4 must differ from input_mp4")

    dst.parent.mkdir(parents=True, exist_ok=True)

    filters: list[str] = []
    if effects:
        g = max(1, int(grain))
        shift = float(chroma_shift)
        filters.append(f"noise=alls={g}:allf=t+u")
        filters.append(
            f"split=3[r][g][b];"
            f"[r]lutrgb=r=val:g=0:b=0,crop=iw-{shift * 2:.2f}:ih-{shift * 2:.2f}:{shift:.2f}:0[rr];"
            f"[g]lutrgb=r=0:g=val:b=0,crop=iw-{shift * 2:.2f}:ih-{shift * 2:.2f}:{shift:.2f}:{shift:.2f}[gg];"
            f"[b]lutrgb=r=0:g=0:b=val,crop=iw-{shift * 2:.2f}:ih-{shift * 2:.2f}:0:{shift:.2f}[bb];"
            f"[rr][gg][bb]mergeplanes=0x001020:gbrp,format=yuv420p"
        )

    if rec_overlay:
        blink = max(0.25, float(rec_blink_hz))
        enable = f"lt(mod(floor(t*{blink * 2:.4f})\\,2)\\,1)"
        filters.append(
            "drawtext=text='REC':"
            "x=w-tw-24:y=20:"
            "fontsize=22:fontcolor=red@0.95:"
            "borderw=1:bordercolor=black@0.6:"
            f"enable='{enable}'"
        )

    if not filters:
        # Enabled but nothing selected — copy through
        shutil.copy2(src, dst)
        return dst

    vf = ",".join(filters)
    cmd = [
        _ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(dst),
    ]

    subprocess.run(cmd, check=True, capture_output=True, text=True)
    if not dst.is_file() or dst.stat().st_size <= 0:
        raise RuntimeError(f"ffmpeg produced no output at {dst}")
    return dst


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Optionally bake subtle VHS / camcorder look onto an MP4 via FFmpeg. "
            "Finishing is OFF by default (pass --enable or set GVD_VHS_FINISHING=1)."
        )
    )
    p.add_argument("input_mp4", type=Path, help="Source MP4 from ComfyUI")
    p.add_argument("output_mp4", type=Path, help="Destination MP4 path")
    p.add_argument(
        "--enable",
        action="store_true",
        help="Enable VHS finishing (off by default)",
    )
    p.add_argument(
        "--rec-overlay",
        action="store_true",
        help="Enable blinking REC badge (off by default even when finishing is on)",
    )
    p.add_argument(
        "--no-effects",
        action="store_true",
        help="Disable grain/chroma effects (REC-only if --rec-overlay)",
    )
    p.add_argument("--grain", type=int, default=15, help="noise alls= strength")
    p.add_argument(
        "--chroma-shift",
        type=float,
        default=1.2,
        help="Pixel nudge for cheap R/B fringe",
    )
    p.add_argument(
        "--rec-blink-hz",
        type=float,
        default=1.0,
        help="REC badge blink rate in Hz",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    out = apply_vhs_look(
        args.input_mp4,
        args.output_mp4,
        grain=args.grain,
        chroma_shift=args.chroma_shift,
        rec_blink_hz=args.rec_blink_hz,
        enabled=True if args.enable else None,
        rec_overlay=bool(args.rec_overlay),
        effects=not bool(args.no_effects),
    )
    if out is None:
        print("VHS finishing disabled (pass --enable or GVD_VHS_FINISHING=1)")
        return 0
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
