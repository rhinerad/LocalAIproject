"""Add explicit ON-SCREEN / OFF-SCREEN attribution to every speaking line."""
import json, re, sys

M='/sessions/eager-dazzling-hypatia/mnt/COMFYUI_STORY_HANDOFF_2026-08-09/outputs/equal_shares'

# The Narrator is the only character whose visibility genuinely changes shot to shot.
# Derived from each clip's own action text in story_config.json.
NARRATOR = {
    '00A':'ON',   # narrator close, he is the subject
    '00B':'ON',   # pull-back, still in frame
    '00C':'LEAVES',# starts in frame, camera crops him out mid-shot
    '00D':'OFF','00D2':'OFF','00E':'OFF','00F':'OFF','00G':'OFF','00H':'OFF',
    '00I':'ENTERS',# off at the start, walks into frame during the pull-back
    '00J':'OFF',  # aerial on Kent, narrator never visible
    '00K':'ENTERS','00L':'ON','00M':'ON','00N':'ON','00O':'ON',
}
# Voices that come from a device rather than a face.
DEVICE = {'Terminal voice', 'Doris recording'}

PHRASE = {
    'ON':     'ON-SCREEN. He is visible in this shot and his mouth moves to his line.',
    'OFF':    'OFF-SCREEN voice only. He is never visible in this shot, and no one on screen is him. Nobody in frame mouths his words.',
    'LEAVES': 'ON-SCREEN at the start, then out of frame as the camera passes him. His voice continues after he is gone. Nobody who remains in frame mouths his words.',
    'ENTERS': 'OFF-SCREEN at the start, then walks into frame during the shot. Before he appears, nobody on screen mouths his words.',
}

def speaker_of(line):
    return line.split(':')[0].split(',')[0].strip()

def status(clip_id, spk):
    if spk == 'Narrator':
        return NARRATOR.get(clip_id, 'OFF')
    if spk in DEVICE:
        return 'DEVICE'
    return 'ON'

def tag(st):
    return {'ON':'ON-SCREEN','OFF':'OFF-SCREEN','LEAVES':'ON-SCREEN THEN OFF',
            'ENTERS':'OFF-SCREEN THEN ON','DEVICE':'DEVICE VOICE'}[st]

def speakers_block(clip):
    dt = clip.get('dialogue_timing') or []
    if not dt:
        return ("SPEAKERS IN THIS SHOT\nNobody speaks in this shot. Every mouth in frame stays "
                "closed for its entire duration: no muttering, no mouthed words, no lip movement.")
    lines = ["SPEAKERS IN THIS SHOT"]
    seen = []
    for d in sorted(dt, key=lambda x: x['start']):
        spk = speaker_of(d['line'])
        if spk in seen:
            continue
        seen.append(spk)
        st = status(clip['id'], spk)
        if spk == 'Narrator':
            lines.append(f"{spk} — {PHRASE[st]}")
        elif st == 'DEVICE':
            lines.append(f"{spk} — DEVICE VOICE. It comes from the machine, not from a person. "
                         f"No human in frame mouths these words.")
        else:
            lines.append(f"{spk} — ON-SCREEN. Visible in this shot; their mouth moves only to "
                         f"their own assigned line and is closed at all other times.")
    lines.append("Everyone else in frame is silent for the whole shot. No other character speaks, "
                 "mutters, mouths words, or moves their lips at any point.")
    return "\n".join(lines)

def retag_dialogue(clip, text):
    """Rewrite each DIALOGUE TIMING line to carry the screen status."""
    for d in sorted(clip.get('dialogue_timing') or [], key=lambda x: x['start']):
        spk = speaker_of(d['line'])
        st  = status(clip['id'], spk)
        old = f"[{d['start']:g}s-{d['end']:g}s] {spk}"
        new = f"[{d['start']:g}s-{d['end']:g}s] {spk}, {tag(st)}"
        text = text.replace(old, new, 1)
    return text

if __name__ == '__main__':
    cfg = json.load(open(M+'/story_config.json', encoding='utf-8-sig'))
    changed = 0
    for c in cfg['clips']:
        p = c['prompt']
        blk = speakers_block(c)
        # insert SPEAKERS before DIALOGUE (or before AUDIO if no dialogue section)
        if '\nDIALOGUE' in p:
            p = p.replace('\nDIALOGUE', '\n' + blk + '\n\nDIALOGUE', 1)
        elif '\nAUDIO' in p:
            p = p.replace('\nAUDIO', '\n' + blk + '\n\nAUDIO', 1)
        p = retag_dialogue(c, p)
        if p != c['prompt']:
            c['prompt'] = p; changed += 1
    json.dump(cfg, open(M+'/story_config.json','w',encoding='utf-8'), indent=2, ensure_ascii=False)
    print(f"updated {changed} of {len(cfg['clips'])} prompts")
