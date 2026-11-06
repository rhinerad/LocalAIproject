"""One-shot authorized C016 gate followed immediately by full resumable batch."""
import json
import subprocess
import sys
import time
from pathlib import Path
from backrooms_watch import atomic_json, RUNTIME, NO_WINDOW
from batch_generate_backrooms import verify_generative, FLF_DIR

ROOT = Path(__file__).resolve().parent

def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-u', str(ROOT / 'batch_generate_backrooms.py'), '--execute']
    atomic_json(RUNTIME / 'rollout.json', dict(state='c016_test', ts=time.time()))
    code = subprocess.call(command + ['--start-at', 'C016', '--limit', '1', '--phase4-only'],
                           cwd=ROOT, creationflags=NO_WINDOW)
    if code:
        atomic_json(RUNTIME / 'rollout.json', dict(state='test_needs_repair', returncode=code, ts=time.time()))
        return code
    verify_generative(FLF_DIR / 'photoreal_video_C016.mp4')
    atomic_json(RUNTIME / 'rollout.json', dict(state='production', clips=24, ts=time.time()))
    print('C016 GATE PASSED: launching full 24-clip production batch without --limit', flush=True)
    code = subprocess.call(command, cwd=ROOT, creationflags=NO_WINDOW)
    atomic_json(RUNTIME / 'rollout.json', dict(state='complete' if code == 0 else 'production_needs_repair', returncode=code, ts=time.time()))
    return code

if __name__ == '__main__':
    raise SystemExit(main())
