#!/usr/bin/env python3
"""Patch minimax_ref2vid.py and final_master_audit.py on the handoff root."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

INSERT = '''
# Production Autogrow helper (shared). Prefer this over ad-hoc C001_master_voice defaults.
try:
    from gvd_graph_builder import (  # type: ignore
        AudioRef,
        ImageRef,
        RefBindingPlan,
        apply_ref2va_autogrow,
        assert_no_bare_ref_images_key,
    )
    _HAS_GVD_GRAPH = True
except Exception:  # pragma: no cover
    _HAS_GVD_GRAPH = False


def apply_minimax_ref2vid_from_plan(
    graph: dict,
    *,
    video_prompt: str,
    plan,
    width: int | None = None,
    height: int | None = None,
    length: int | None = None,
):
    """Production entry: bind per-character image/audio refs via dotted Autogrow keys."""
    if not _HAS_GVD_GRAPH:
        raise RuntimeError("gvd_graph_builder unavailable; cannot emit production Autogrow keys")
    # Allow import from local_agent/ by adding parent to path lazily
    w = int(width or 864)
    h = int(height or 480)
    n = int(length or 124)
    g = apply_ref2va_autogrow(
        graph,
        prompt=video_prompt,
        plan=plan,
        width=w,
        height=h,
        length=n,
    )
    assert_no_bare_ref_images_key(g)
    return g

'''

ADDON = '''

def probe_duration_seconds(path: Path | str) -> float | None:
    """ffprobe duration; None if unavailable."""
    import subprocess
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nk=1:nw=1",
                str(path),
            ],
            text=True,
            timeout=60,
        )
        return float(out.strip())
    except Exception:
        return None


def execute_normalize_concat(
    plan: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute a concat plan produced by build_normalize_concat_plan.

    Refuses to run when media is missing. Sets plan["executed"]=True only after success.
    """
    import subprocess
    result = {
        "ok": False,
        "executed": False,
        "dry_run": dry_run,
        "missing": list(plan.get("missing") or []),
        "returncode": None,
        "error": None,
    }
    if result["missing"]:
        result["error"] = "missing SELECTED media; refusing assembly"
        return result
    argv = list(plan.get("argv") or [])
    if not argv:
        result["error"] = "empty argv"
        return result
    if dry_run:
        result["ok"] = True
        return result
    try:
        cp = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=3600)
        result["returncode"] = cp.returncode
        if cp.returncode != 0:
            result["error"] = (cp.stderr or cp.stdout or "ffmpeg failed")[:2000]
            return result
        plan["executed"] = True
        result["executed"] = True
        result["ok"] = True
        out = plan.get("output_path")
        if out is None and len(argv) >= 1:
            out = argv[-1]
        if out:
            result["output_path"] = str(out)
            result["duration_s"] = probe_duration_seconds(out)
            try:
                result["sha256"] = _sha256_file(out)
            except Exception as exc:
                result["sha256_error"] = str(exc)
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result


def classify_master_scope(
    *,
    input_paths: list[str],
    output_duration_s: float | None,
    unique_sha256: set[str] | None = None,
) -> dict[str, Any]:
    """Distinguish assembly smoke vs distinct narrative masters."""
    n = len(input_paths)
    uniq = len(unique_sha256 or set())
    scope = "unknown"
    if n <= 2 and uniq <= 1 and (output_duration_s or 0) > 60:
        scope = "assembly_smoke_repeated_or_padded"
    elif uniq >= max(3, n // 2) and (output_duration_s or 0) > 60:
        scope = "multi_shot_narrative_candidate"
    elif n >= 1 and (output_duration_s or 0) <= 30:
        scope = "short_assembly"
    return {
        "scope": scope,
        "input_count": n,
        "unique_input_sha256": uniq,
        "output_duration_s": output_duration_s,
        "proves_long_form_generation": scope == "multi_shot_narrative_candidate",
    }

'''


def patch_minimax():
    path = ROOT / "local_agent" / "minimax_ref2vid.py"
    text = path.read_text(encoding="utf-8")
    if "apply_minimax_ref2vid_from_plan" in text:
        print("minimax_ref2vid already patched")
        return
    # Ensure parent root importable for gvd_graph_builder
    boot = (
        "import sys as _sys\n"
        "from pathlib import Path as _Path\n"
        "_ROOT = _Path(__file__).resolve().parents[1]\n"
        "if str(_ROOT) not in _sys.path:\n"
        "    _sys.path.insert(0, str(_ROOT))\n"
    )
    if "LOAD_AUDIO_CLASS" not in text:
        raise SystemExit("unexpected minimax_ref2vid.py")
    text = text.replace(
        'LOAD_AUDIO_CLASS = "LoadAudio"\n',
        'LOAD_AUDIO_CLASS = "LoadAudio"\n' + boot + INSERT,
        1,
    )
    # Soft-warn in apply_minimax_ref2vid docstring area
    text = text.replace(
        "ref_audio_name: str = C001_MASTER_VOICE_WAV,",
        "ref_audio_name: str = C001_MASTER_VOICE_WAV,  # legacy default; prefer apply_minimax_ref2vid_from_plan",
        1,
    )
    path.write_text(text, encoding="utf-8")
    print("patched", path)


def patch_final_master():
    path = ROOT / "final_master_audit.py"
    text = path.read_text(encoding="utf-8")
    if "def execute_normalize_concat" in text:
        print("final_master_audit already patched")
        return
    if "def main(" not in text:
        raise SystemExit("no main in final_master_audit")
    text = text.replace("def main(", ADDON + "\ndef main(", 1)
    if "--execute" not in text:
        needle = 'parser.add_argument(\n        "--write-concat-plan"'
        # tolerate formatting variants
        if '--write-concat-plan"' in text and "--execute" not in text:
            text = text.replace(
                'parser.add_argument(\n        "--write-concat-plan"',
                'parser.add_argument("--execute", action="store_true", '
                'help="Run ffmpeg concat plan after audit passes")\n'
                '    parser.add_argument("--dry-run-execute", action="store_true", '
                'help="Validate execute path without running ffmpeg")\n'
                '    parser.add_argument(\n        "--write-concat-plan"',
                1,
            )
    # Wire execute into main body lightly
    if "execute_normalize_concat" in text and "args.execute" not in text:
        text = text.replace(
            "out = {\"audit\": report, \"concat_plan\": plan}",
            "exec_report = None\n"
            "    if getattr(args, \"execute\", False) or getattr(args, \"dry_run_execute\", False):\n"
            "        if not report.get(\"ok\"):\n"
            "            exec_report = {\"ok\": False, \"error\": \"audit failed; refusing execute\"}\n"
            "        else:\n"
            "            exec_report = execute_normalize_concat(\n"
            "                plan, dry_run=bool(getattr(args, \"dry_run_execute\", False))\n"
            "            )\n"
            "    out = {\"audit\": report, \"concat_plan\": plan, \"execute\": exec_report}",
            1,
        )
    path.write_text(text, encoding="utf-8")
    print("patched", path)


if __name__ == "__main__":
    patch_minimax()
    patch_final_master()
