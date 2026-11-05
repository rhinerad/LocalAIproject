"""Live localhost acceptance of the operator's reviewed prompt pack.

Uses the same /api/send endpoint as the GUI. Never edits the source document.
--render-anchor sends a real render request; default only ingests/exports.
"""
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'A:\Users\rhine\Documents\Codex\2026-09-07\i-w\outputs\backrooms_sitcom_prompt_pack_EDITED.md')
CID = 'f8f7f70e364d40c0'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--render-anchor', action='store_true')
    parser.add_argument('--retry-anchor', action='store_true')
    args = parser.parse_args()
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    message = 'render the first frame again' if args.retry_anchor else ('render' if args.render_anchor else SOURCE.read_text(encoding='utf-8'))
    body = json.dumps({'id': CID, 'message': message, 'prefer': 'cpu'}).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:8760/api/send', data=body,
        headers={'Content-Type': 'application/json'}, method='POST')
    events = []
    with urllib.request.urlopen(req, timeout=120) as response:
        for line in response:
            text = line.decode('utf-8').strip()
            if text.startswith('data: '):
                event = json.loads(text[6:])
                events.append(event)
                if event['kind'] in ('done', 'error'):
                    print(event['kind'], str(event['data'])[:1400], flush=True)
    progress = json.loads((ROOT / 'local_agent/runtime/managed_tasks' / CID / 'progress.json').read_text())
    out = Path(progress['output_dir'])
    clips = [json.loads((out / (c + '.json')).read_text(encoding='utf-8')) for c in progress['clip_ids']]
    assert len(clips) == 102
    assert all(c.get('editor_overrides_applied') for c in clips)
    assert all(c.get(k, '').strip() for c in clips for k in ('start_frame', 'last_frame', 'video_prompt'))
    assert all('autofocus hunting' not in c[k].lower() and 'motion smear' not in c[k].lower()
               for c in clips for k in ('start_frame', 'last_frame'))
    assert all('yellow wallpaper' not in c['start_frame'].lower() and not c.get('start_frame_lora') for c in clips[:14])
    assert all(c['references']['start'] == clips[i-1]['id'] + '_approved_last_frame' for i,c in enumerate(clips) if i)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before
    result = {'source': str(SOURCE), 'source_sha256': before, 'source_unchanged': True,
        'conversation_id': CID, 'output_dir': str(out), 'complete_clip_records': len(clips),
        'complete_still_prompts': len(clips)*2, 'complete_video_prompts': len(clips),
        'editor_overrides_verified': True, 'render_requested': args.render_anchor or args.retry_anchor,
        'production_complete': False, 'events': events}
    evidence = ROOT / 'work/runtime' / ('reviewed_pack_acceptance_' + str(time.time_ns()) + '.json')
    evidence.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Evidence:', evidence, flush=True)


if __name__ == '__main__':
    main()
