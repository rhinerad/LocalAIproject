#!/usr/bin/env python3
"""Deterministic, resumable coordinator for the H3 Omni voice-lock experiment."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
RUNTIME = EQ / "runtime"
OWNER = RUNTIME / "omni_pipeline_owner.json"
RENDER_OWNER = RUNTIME / "render_queue_owner.json"
LOG = RUNTIME / "omni_pipeline_supervisor.log"
RECEIPT = RUNTIME / "omni_voice_lock_test_receipt.json"
PYTHON = Path(sys.executable)
WORK = ROOT / "work"
MISSING_VOX = [
    "VOX_CREW_LEAD_REF",
    "VOX_MALE_VISITOR_ONE_REF",
    "VOX_MALE_VISITOR_TWO_REF",
]


def emit(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load(path: Path, default: dict) -> dict:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
        capture_output=True,
    ).returncode == 0


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def run(label: str, args: list[str]) -> None:
    emit(label)
    result = subprocess.run([str(PYTHON), *args], cwd=ROOT, text=True)
    if result.returncode:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


def main() -> int:
    current = load(OWNER, {})
    current_pid = int(current.get("pid", 0) or 0)
    if current_pid != os.getpid() and process_exists(current_pid):
        emit(f"coordinator already live at pid={current_pid}; not duplicating")
        return 3
    render = load(RENDER_OWNER, {})
    render_pid = int(render.get("pid", 0) or 0)
    if process_exists(render_pid):
        emit(f"render queue already live at pid={render_pid}; not duplicating")
        return 3

    atomic_write(OWNER, {
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "MiniMax H3 immutable Omni-Reference voice-lock experiment",
    })
    try:
        run(
            "Render/reuse the three missing 0.2 MP VOX identity masters",
            [str(WORK / "render_vox_references.py"), *sum((["--only", item] for item in MISSING_VOX), [])],
        )
        run("Build immutable 5-10 second checksum-pinned masters",
            [str(WORK / "prepare_omni_voice_masters.py")])
        master_map = load(EQ / "omni_voice_master_map.json", {})
        missing = [
            name for name, row in master_map.get("references", {}).items()
            if not row.get("eligible")
        ]
        if missing:
            raise RuntimeError("voice masters still missing: " + ", ".join(missing))

        run("Build native-tag Omni-Reference prompts",
            [str(WORK / "build_audio_pass_prompts.py")])
        run("Preflight controlled Narrator tests 00A and 00I", [
            str(WORK / "render_audio_pass.py"), "--clip", "00A", "--clip", "00I",
            "--max-attempts", "1", "--prompt-profile", "omni_master_v1_test", "--check",
        ])
        run("Render controlled Narrator tests 00A and 00I", [
            str(WORK / "render_audio_pass.py"), "--clip", "00A", "--clip", "00I",
            "--max-attempts", "1", "--rerender-pending",
            "--prompt-profile", "omni_master_v1_test",
        ])

        manifest = load(EQ / "audio_pass_manifest.json", {"clips": {}})
        tests = {}
        for clip_id in ("00A", "00I"):
            attempts = [
                item for item in manifest.get("clips", {}).get(clip_id, {}).get("attempts", [])
                if item.get("prompt_profile") == "omni_master_v1_test"
            ]
            latest = attempts[-1] if attempts else {}
            tests[clip_id] = {
                "status": latest.get("status", "missing"),
                "source_video": latest.get("source_video"),
                "candidate_full_wav": latest.get("candidate_full_wav"),
                "validation_report": latest.get("validation_report"),
                "audio_reference_sha256": latest.get("audio_reference_sha256"),
                "human_checks_required": [
                    "same Narrator identity as master",
                    "exactly one dry voice layer",
                    "exact scripted words",
                    "speech only in assigned window",
                    "no leaked master words or spoken control prose",
                ],
            }
        atomic_write(RECEIPT, {
            "stage": "controlled Omni-Reference Narrator experiment complete",
            "full_audio_pass_started": False,
            "picture_pass_started": False,
            "tests": tests,
            "next_gate": "audit both tests before full Stage-1 audio generation",
            "completed_at": datetime.now().isoformat(timespec="seconds"),
        })
        emit(f"Controlled test complete; review receipt: {RECEIPT}")
        return 0
    except Exception as error:
        atomic_write(RECEIPT.with_name("omni_voice_lock_test_blocker.json"), {
            "status": "blocked",
            "reason": str(error),
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
        })
        emit(f"Coordinator stopped on blocker: {error}")
        return 1
    finally:
        atomic_write(OWNER, {
            "pid": 0,
            "released_at": datetime.now().isoformat(timespec="seconds"),
            "purpose": "released",
        })


if __name__ == "__main__":
    raise SystemExit(main())
