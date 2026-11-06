#!/usr/bin/env python3
"""Checkpointed Backrooms batch. A verified generative Phase 4 is required."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'local_agent'))
from local_agent.dispatcher import DEFAULT_COMFY_URL, PipelineOrchestrator
from local_agent import comfy_api, temporal_physics as tp
from live_vram_test import (TILE_UNET, TILE_CONTROL_NAME, TILE_WIDTH, TILE_HEIGHT,
                           VIDEO_LENGTH, VIDEO_TIMEOUT_S, _submit_still, _upload_png,
                           build_fl2va_graph, build_tile_upscale_graph, wait_for_video)
from backrooms_watch import BackroomsWatch, RUNTIME, api, atomic_json, NO_WINDOW
CLIPS_PATH = ROOT / 'backrooms_24_clips.json'
FLF_DIR = ROOT / 'local_agent' / 'runtime' / 'dspy_opt'
OUT_DIR = RUNTIME

def probe(path):
    return json.loads(subprocess.check_output(
        ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
        text=True, encoding='utf-8', timeout=30, creationflags=NO_WINDOW))

def valid_video(path):
    if not path or not Path(path).is_file() or Path(path).stat().st_size < 10_000:
        return False
    try:
        return any(s.get('codec_type') == 'video' and int(s.get('nb_frames', 0)) > 0
                   for s in probe(path)['streams'])
    except Exception:
        return False

def existing_flf_mp4(cid):
    from auto_boot_and_test import COMFY_ROOT
    for folder in (FLF_DIR, comfy_api.comfy_output_root() / 'dspy_opt', COMFY_ROOT / 'output' / 'dspy_opt'):
        for path in sorted(folder.glob(f'br24_{cid}*.mp4')):
            if '_aud' not in path.stem and valid_video(path):
                return path.resolve()
    return None

def normalize_graph(graph):
    return {key: {'class_type': node['class_type'], 'inputs': node['inputs']}
            for key, node in graph.items()}

def verify_generative(path, expected=None):
    data = probe(path)
    stream = next(s for s in data['streams'] if s.get('codec_type') == 'video')
    if (stream['width'], stream['height'], int(stream['nb_frames'])) != (TILE_WIDTH, TILE_HEIGHT, VIDEO_LENGTH):
        raise ValueError('Wrong output dimensions or frame count')
    if stream['r_frame_rate'] != '8/1':
        raise ValueError('Wrong output frame rate')
    graph = data['format'].get('tags', {}).get('prompt')
    for _ in range(4):
        if not isinstance(graph, str):
            break
        graph = json.loads(graph)
    if not isinstance(graph, dict):
        raise ValueError('Missing embedded workflow')
    graph = normalize_graph(graph)
    if any(n['class_type'] == 'ImageScale' for n in graph.values()):
        raise ValueError('Legacy spatial output is not accepted')
    if graph['32']['class_type'] != 'UNETLoader' or graph['32']['inputs']['unet_name'] != TILE_UNET:
        raise ValueError('Phase 4 did not use the required 1.3B base')
    if graph['32b']['inputs']['lora_name'] != TILE_CONTROL_NAME:
        raise ValueError('Wrong tile LoRA')
    if graph['40']['class_type'] != 'KSampler' or graph['40']['inputs']['denoise'] <= 0:
        raise ValueError('Missing generative sampling')
    for node, key, link in [('42','images',['41',0]), ('41','samples',['40',0]),
                            ('40','model',['32c',0]), ('32c','model',['32b',0]),
                            ('32b','model',['32',0]), ('40','positive',['38',0]),
                            ('40','negative',['38',1]), ('40','latent_image',['39',0])]:
        if graph[node]['inputs'][key] != link:
            raise ValueError(f'Broken generative path: {node}.{key}')
    if expected is not None and graph != normalize_graph(expected):
        raise ValueError('Embedded graph differs from submitted graph')
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-'],
                   check=True, capture_output=True, timeout=60, creationflags=NO_WINDOW)
    return dict(verified=True, width=stream['width'], height=stream['height'],
                frames=int(stream['nb_frames']), duration=float(data['format']['duration']),
                model=TILE_UNET, graph=graph,
                sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

def ensure_video_has_audio(path):
    if any(s.get('codec_type') == 'audio' for s in probe(path)['streams']):
        return path.resolve()
    out = path.with_name(path.stem + '_aud.mp4')
    if valid_video(out) and any(s.get('codec_type') == 'audio' for s in probe(out)['streams']):
        return out.resolve()
    if out.exists():
        out = path.with_name(path.stem + f'_aud_{time.time_ns()}.mp4')
    subprocess.run(['ffmpeg', '-n', '-v', 'error', '-i', str(path), '-f', 'lavfi', '-i',
                    'anullsrc=channel_layout=stereo:sample_rate=48000', '-c:v', 'copy', '-c:a', 'aac',
                    '-shortest', str(out)], check=True, timeout=60, creationflags=NO_WINDOW)
    return out.resolve()

class GuardedOrchestrator(PipelineOrchestrator):
    def __init__(self, watch):
        super().__init__(comfy_url=DEFAULT_COMFY_URL)
        self.watch = watch
    def submit_prompt(self, graph, **kwargs):
        self.watch.check()
        queued = super().submit_prompt(graph, **kwargs)
        pid = queued['prompt_id']
        atomic_json(OUT_DIR / f'prompt_{pid}.json', graph)
        self.watch.event('prompt_submitted', prompt_id=pid)
        return queued
    def track_prompt_id(self, prompt_id, *, timeout_s=VIDEO_TIMEOUT_S, **kwargs):
        deadline = time.monotonic() + timeout_s
        last_print = 0
        while time.monotonic() < deadline:
            self.watch.check()
            try:
                history = api('/history/' + prompt_id)
            except OSError:
                time.sleep(2)
                continue
            item = history.get(prompt_id)
            if item:
                status = item.get('status', {})
                if status.get('status_str') == 'error':
                    atomic_json(OUT_DIR / f'error_{prompt_id}.json', item)
                    messages = [x[1] for x in status.get('messages', []) if x[0] in ('execution_error','execution_interrupted')]
                    detail = messages[-1] if messages else {}
                    raise RuntimeError(f"Node {detail.get('node_id')} {detail.get('exception_type')}: {detail.get('exception_message', 'execution interrupted')}")
                if status.get('completed') and status.get('status_str') == 'success':
                    atomic_json(OUT_DIR / f'history_{prompt_id}.json', item)
                    self.watch.event('prompt_completed', prompt_id=prompt_id)
                    return {'state': 'complete', 'prompt_id': prompt_id}
            if time.monotonic() - last_print >= 30:
                s = self.watch.sample()
                print(f"Running {self.watch.phase}: GPU {s['temperature_c']:.0f} C, VRAM {s['vram_mib']:.0f} MiB, RAM free {s['ram_available_bytes']/1024**3:.1f} GiB", flush=True)
                last_print = time.monotonic()
            time.sleep(2)
        raise TimeoutError(f'Prompt {prompt_id} exceeded {timeout_s} seconds')

def run_phase4(orch, cid, mp4, motion):
    watch = orch.watch
    mp4_for_load = ensure_video_has_audio(Path(mp4))
    watch.restart(cid + ':phase4')
    graph = build_tile_upscale_graph(str(mp4_for_load), motion, f'dspy_opt/photoreal_video_{cid}')
    pid = orch.submit_prompt(graph)['prompt_id']
    print(f'Phase 4 {cid}: {TILE_UNET}; prompt_id={pid}', flush=True)
    orch.track_prompt_id(pid, timeout_s=VIDEO_TIMEOUT_S)
    photo = wait_for_video(pid, orch.comfy_url, timeout_s=60)
    verification = verify_generative(photo, graph)
    canonical = FLF_DIR / f'photoreal_video_{cid}.mp4'
    if canonical.exists():
        shutil.copy2(canonical, canonical.with_name(canonical.stem + f'_preserved_{time.time_ns()}.mp4'))
    temp = canonical.with_suffix('.mp4.tmp')
    shutil.copy2(photo, temp)
    os.replace(temp, canonical)
    atomic_json(OUT_DIR / f'verified_{cid}.json', dict(source=str(photo), canonical=str(canonical), prompt_id=pid, **verification))
    print(f'GENERATIVE VERIFIED {cid}: {canonical} ({canonical.stat().st_size} bytes)', flush=True)
    watch.stop()
    return dict(photoreal_mp4=str(canonical), raw_photoreal_mp4=str(photo), tile_prompt_id=pid,
                photoreal_bytes=canonical.stat().st_size, sha256=verification['sha256'])

def load_clips(path):
    payload = json.loads(path.read_text(encoding='utf-8'))
    clips = payload.get('clips') if isinstance(payload, dict) else payload
    if not clips or len({c['id'] for c in clips}) != len(clips):
        raise ValueError('Empty or duplicate clip list')
    return clips

def motion_prompt(clip):
    return str(clip.get('motion') or '')

def process_clip(orch, clip, phase4_only=False):
    cid = clip['id']
    path = OUT_DIR / f'checkpoint_{cid}.json'
    state = json.loads(path.read_text()) if path.exists() else {'id': cid}
    photo = state.get('photoreal_mp4')
    if photo and valid_video(photo):
        try:
            if verify_generative(photo)['sha256'] == state.get('sha256'):
                print(f'SKIP {cid}: verified generative checkpoint', flush=True)
                return state
        except Exception:
            pass
    mp4 = Path(state['mp4']) if valid_video(state.get('mp4')) else existing_flf_mp4(cid)
    if phase4_only:
        mp4 = FLF_DIR / 'br24_C016_00001.mp4'
        if cid != 'C016' or not valid_video(mp4):
            raise ValueError('Phase-4-only gate requires existing br24_C016_00001.mp4')
    if mp4:
        print(f'{cid}: reuse Phase 3 {mp4}; skip Phases 1-3', flush=True)
        state.update(mp4=str(mp4), stage='phase3_complete')
        atomic_json(path, state)
    else:
        injected = state.get('injected')
        if not injected:
            orch.watch.stop()
            injected = {key: tp.runtime_inject_temporal_physics(clip[key], style=clip.get('style','backrooms'))
                        for key in ('start','end','motion')}
            tp.unload_ollama_model()
            state.update(injected=injected, stage='injected')
            atomic_json(path, state)
        for key in ('start','end'):
            saved = state.get(key + '_png')
            if saved and Path(saved).is_file():
                continue
            orch.watch.restart(cid + ':' + key)
            try:
                png = _submit_still(orch, injected[key], f'br24_{cid}_{key}')
            except SystemExit as exc:
                raise RuntimeError(str(exc)) from exc
            state.update({key + '_png': str(png), 'stage': key + '_complete'})
            atomic_json(path, state)
            orch.watch.stop()
        orch.watch.restart(cid + ':phase3')
        start = _upload_png(Path(state['start_png']), orch.comfy_url)
        end = _upload_png(Path(state['end_png']), orch.comfy_url)
        graph = build_fl2va_graph(start, end, injected['motion'], f'dspy_opt/br24_{cid}')
        pid = orch.submit_prompt(graph)['prompt_id']
        orch.track_prompt_id(pid, timeout_s=VIDEO_TIMEOUT_S)
        mp4 = wait_for_video(pid, orch.comfy_url, timeout_s=60)
        if not valid_video(mp4):
            raise RuntimeError('Phase 3 output is invalid')
        state.update(mp4=str(mp4), video_prompt_id=pid, stage='phase3_complete')
        atomic_json(path, state)
        orch.watch.stop()
    state.update(run_phase4(orch, cid, mp4, state.get('injected', {}).get('motion') or motion_prompt(clip)))
    state.update(stage='complete', completed_at=time.time())
    atomic_json(path, state)
    return state

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--clips', type=Path, default=CLIPS_PATH)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--start-at', default='')
    parser.add_argument('--phase4-only', action='store_true')
    parser.add_argument('--attempts', type=int, default=3)
    args = parser.parse_args(argv)
    clips = load_clips(args.clips)
    if args.start_at:
        clips = clips[[c['id'] for c in clips].index(args.start_at):]
    if args.limit:
        clips = clips[:args.limit]
    if args.phase4_only and (args.limit != 1 or [c['id'] for c in clips] != ['C016']):
        parser.error('--phase4-only requires --start-at C016 --limit 1')
    print(f'clips={len(clips)} execute={args.execute} phase4_only={args.phase4_only}', flush=True)
    if not args.execute:
        for clip in clips:
            print(f"PLAN {clip['id']}: resume checkpoints; generative 1.3B Phase 4 required")
        return 0
    OUT_DIR.mkdir(exist_ok=True, parents=True)
    # Explicit file logging survives Windows hidden-process standard-handle loss.
    sys.stdout = sys.stderr = (OUT_DIR / f'runner_{os.getpid()}.log').open('a', encoding='utf-8', buffering=1)
    watch = BackroomsWatch()
    watch.acquire()
    try:
        orch = GuardedOrchestrator(watch)
        for index, clip in enumerate(clips):
            for attempt in range(1, args.attempts + 1):
                atomic_json(OUT_DIR / 'status.json', dict(state='running', clip=clip['id'],
                            index=index+1, total=len(clips), attempt=attempt, pid=os.getpid(), ts=time.time()))
                try:
                    artifacts = process_clip(orch, clip, args.phase4_only)
                    row = dict(id=clip['id'], ok=True, artifacts=artifacts, ts=time.time())
                except Exception as exc:
                    row = dict(id=clip['id'], ok=False, attempt=attempt, error=str(exc), trace=traceback.format_exc(), ts=time.time())
                    print(f"FAILED {clip['id']} attempt {attempt}: {exc}", flush=True)
                    watch.stop()
                    tp.unload_ollama_model()
                with (OUT_DIR / 'manifest_generative.jsonl').open('a', encoding='utf-8') as fh:
                    fh.write(json.dumps(row) + '\n'); fh.flush(); os.fsync(fh.fileno())
                if row['ok']:
                    break
                if attempt == args.attempts:
                    atomic_json(OUT_DIR / 'status.json', dict(state='needs_repair', clip=clip['id'], error=row['error'], pid=os.getpid(), ts=time.time()))
                    return 1
                print(f"Cooling and retrying {clip['id']} from its last checkpoint", flush=True)
                time.sleep(10)
        atomic_json(OUT_DIR / 'status.json', dict(state='complete', total=len(clips), pid=os.getpid(), ts=time.time()))
        return 0
    finally:
        watch.close()

if __name__ == '__main__':
    raise SystemExit(main())
