"""Owned ComfyUI lifecycle, hardware guard, and durable telemetry for Backrooms."""
from __future__ import annotations
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
import psutil
from auto_boot_and_test import COMFY_ROOT, COMFY_PYTHON, COMFY_MAIN, EXTRA_PATHS
from gpu_lock import GpuLock, GpuLockHeld

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'logs' / 'backrooms_batch'
LOCK_PATH = RUNTIME / 'runner.lock'
OWNER_PATH = ROOT / 'batch_render_queue_owner.json'

_thermal_guard = None


def thermal_guard_module():
    """Lazy `work.thermal_guard` import: `work/` is gitignored, so a fresh clone (or a
    Linux test box) must still be able to import this module; the guard is resolved
    on first use and can be injected by tests via `set_thermal_guard()`."""
    global _thermal_guard
    if _thermal_guard is None:
        from work import thermal_guard as _tg  # noqa: WPS433 (deliberately lazy)
        _thermal_guard = _tg
    return _thermal_guard


def set_thermal_guard(module) -> None:
    global _thermal_guard
    _thermal_guard = module
URL = 'http://127.0.0.1:8188'
VRAM_CAP_MIB = int(15_500_000_000 / 1024**2)  # conservative decimal 15.5 GB
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

def api(path, data=None, timeout=5):
    req = urllib.request.Request(URL + path, data=None if data is None else json.dumps(data).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}

def port_open():
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(('127.0.0.1', 8188)) == 0

def atomic_json(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)

class BackroomsWatch:
    def __init__(self):
        RUNTIME.mkdir(parents=True, exist_ok=True)
        self.proc = None
        self.owned = None
        self.phase = 'idle'
        self.trip = None
        self.baseline_available = None
        self.halt = threading.Event()
        self.log_lock = threading.Lock()
        self.lifecycle_lock = threading.RLock()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.lock_file = None
        self.gpu_lock = None
        self.backend_log = None

    def event(self, event, **fields):
        row = dict(ts=time.time(), event=event, phase=self.phase, **fields)
        with self.log_lock, (RUNTIME / 'watcher.jsonl').open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(row) + '\n')

    def acquire(self):
        # Shared OS lock + owner JSON (gpu_lock.py); same files as before:
        # logs/backrooms_batch/runner.lock and batch_render_queue_owner.json.
        self.gpu_lock = GpuLock('backrooms_watch', purpose='Backrooms generative batch',
                                lock_path=LOCK_PATH, owner_path=OWNER_PATH)
        try:
            self.gpu_lock.acquire()
        except GpuLockHeld as exc:
            raise RuntimeError(f'Another renderer owns the queue: {exc.owner or exc}') from exc
        self.lock_file = self.gpu_lock.lock_file
        try:
            if port_open():
                raise RuntimeError('Port 8188 is already owned; refusing to start a second backend')
            for process in psutil.process_iter(['pid', 'name', 'cmdline']):
                args = process.info['cmdline'] or []
                if 'python' in (process.info['name'] or '').lower() and any(
                    'comfyui' in arg.lower() and arg.lower().endswith('main.py') for arg in args
                ):
                    raise RuntimeError(f'Existing ComfyUI process {process.pid}; refusing duplicate')
        except Exception:
            self.gpu_lock.release()
            self.lock_file = None
            raise
        self.thread.start()
        self.event('owner_acquired', pid=os.getpid(), vram_cap_mib=VRAM_CAP_MIB, temperature_cap_c=82)

    def sample(self):
        raw = subprocess.check_output(['nvidia-smi', '--query-gpu=temperature.gpu,memory.used,utilization.gpu',
                                       '--format=csv,noheader,nounits'], text=True, timeout=5, creationflags=NO_WINDOW)
        temp, vram, util = [float(x.strip()) for x in raw.splitlines()[0].split(',')]
        mem = psutil.virtual_memory()
        rss = 0
        owned = self.owned
        if owned:
            try:
                rss = sum(p.memory_info().rss for p in [owned] + owned.children(recursive=True))
            except psutil.NoSuchProcess:
                pass
        return dict(temperature_c=temp, vram_mib=vram, gpu_util_percent=util,
                    ram_available_bytes=mem.available, ram_used_bytes=mem.used,
                    backend_rss_bytes=rss, backend_pid=owned.pid if owned else None,
                    port_8188=port_open())

    def run(self):
        failures = 0
        while not self.halt.is_set():
            try:
                sample = self.sample()
                failures = 0
                self.event('sample', **sample)
                reason = None
                if sample['temperature_c'] >= min(82, thermal_guard_module().EMERGENCY_C):
                    reason = 'thermal ceiling reached'
                elif sample['vram_mib'] >= VRAM_CAP_MIB:
                    reason = 'VRAM ceiling reached'
                elif self.owned and sample['ram_available_bytes'] < 1024**3:
                    reason = 'less than 1 GiB system RAM available'
                if reason and self.owned and not self.trip:
                    self.emergency(reason, sample)
            except Exception as exc:
                failures += 1
                self.event('telemetry_error', error=str(exc), consecutive=failures)
                if failures >= 3 and self.owned and not self.trip:
                    self.emergency('three consecutive telemetry failures', {})
            self.halt.wait(2)

    def emergency(self, reason, sample):
        self.trip = reason
        self.event('hardware_trip', reason=reason, **sample)
        print(f'HARDWARE STOP: {reason}', flush=True)
        try:
            api('/interrupt', {}, timeout=2)
        except Exception:
            pass
        self.terminate_owned()

    def terminate_owned(self):
        with self.lifecycle_lock:
            if not self.owned:
                return
            parent = self.owned
            try:
                targets = parent.children(recursive=True) + [parent]
            except psutil.NoSuchProcess:
                targets = []
            self.event('stop_owned_backend', pids=[p.pid for p in targets])
            for p in reversed(targets):
                try:
                    p.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(targets, timeout=8)
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(alive, timeout=5)
            if alive:
                raise RuntimeError(f'Owned backend did not exit: {[p.pid for p in alive]}')
            if self.proc:
                self.proc.wait(timeout=5)
            self.owned = None
            self.proc = None

    def stop(self):
        before = self.sample()
        self.terminate_owned()
        deadline = time.monotonic() + 90
        while True:
            after = self.sample()
            ram_ok = self.baseline_available is None or after['ram_available_bytes'] >= self.baseline_available - 2 * 1024**3
            if not after['port_8188'] and ram_ok:
                self.event('restart_cleanup_verified', before=before, after=after,
                           ram_available_delta_bytes=after['ram_available_bytes'] - before['ram_available_bytes'])
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Backend stopped but port or RAM recovery verification failed')
            time.sleep(2)
        thermal_guard_module().wait_after_render(lambda message: print(message, flush=True))

    def restart(self, phase):
        self.stop()
        self.phase = phase
        self.trip = None
        thermal_guard_module().wait_before_render(lambda message: print(message, flush=True))
        sample = self.sample()
        if sample['vram_mib'] >= VRAM_CAP_MIB or sample['port_8188']:
            raise RuntimeError('Hardware/port preflight refused')
        self.baseline_available = sample['ram_available_bytes']
        stamp = time.strftime('%Y%m%dT%H%M%S')
        self.backend_log = RUNTIME / f'comfy_{stamp}_{phase.replace(":", "_")}.log'
        cmd = [str(COMFY_PYTHON), '-u', str(COMFY_MAIN), '--listen', '127.0.0.1', '--port', '8188',
               '--extra-model-paths-config', str(EXTRA_PATHS), '--reserve-vram', '2', '--preview-method', 'none']
        # Only the batch's required extensions; avoid unrelated startup installers.
        cmd += ['--cache-none', '--disable-all-custom-nodes', '--disable-api-nodes', '--whitelist-custom-nodes',
                'ComfyUI-GGUF', 'ComfyUI-VideoHelperSuite', 'comfyui-impact-pack', 'comfyui-impact-subpack']
        with self.backend_log.open('w', encoding='utf-8') as log:
            with self.lifecycle_lock:
                backend_env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
                self.proc = subprocess.Popen(cmd, cwd=COMFY_ROOT, stdout=log, stderr=subprocess.STDOUT,
                                             creationflags=NO_WINDOW, env=backend_env)
                self.owned = psutil.Process(self.proc.pid)
        self.event('backend_started', pid=self.proc.pid, log=str(self.backend_log), baseline=sample)
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            self.check()
            try:
                api('/system_stats', timeout=3)
                self.event('backend_ready', **self.sample())
                print(f'Backend ready: {phase}; log={self.backend_log}', flush=True)
                return
            except (OSError, ValueError):
                time.sleep(2)
        raise TimeoutError('ComfyUI startup exceeded 600 seconds')

    def check(self):
        if self.trip:
            raise RuntimeError(self.trip)
        if not self.proc or self.proc.poll() is not None:
            raise RuntimeError(f'ComfyUI exited; inspect {self.backend_log}')
        if not self.thread.is_alive():
            raise RuntimeError('Hardware watcher is not alive')

    def close(self):
        try:
            self.stop()
        finally:
            self.halt.set()
            self.thread.join(timeout=10)
            if self.gpu_lock is not None:
                self.gpu_lock.release()  # writes the pid=0 'released' owner record
                self.gpu_lock = None
            self.lock_file = None
