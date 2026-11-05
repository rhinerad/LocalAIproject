#!/usr/bin/env python3
"""VHS liminal CLIP 1-18 Minimax FLF2V runner — reuses Equal Shares fl2va graph."""
from __future__ import annotations
import json, shutil, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
import render_single_pass as h3

INV = ROOT / "work" / "runtime" / "_vhs_clip1_18_inventory.json"
OUT_DIR = ROOT / "outputs" / "stories" / "_comfy_output" / "stories" / "vhs_minimax_flf2v"
MANIFEST = ROOT / "work" / "runtime" / "_vhs_flf2v_manifest.json"
DURATION = 6.0  # seconds; lower if OOM

PROMPTS = {
1: "[First-person POV, shaky tracking shot into falling tilt] The camera physically held by a person follows a skateboarder grinding a metal rail, shaking slightly. The camera abruptly tilts backward, staring at the sky for a second, and violently plummets straight down through the solid concrete ground, tumbling through darkness before cutting to static. Sunny outdoor concrete skatepark, bright natural sunlight, 1990s VHS camcorder aesthetic.",
2: "[First-person POV, continuing from static fall into slow tilt up] The static clears to reveal the camera lying sideways on a moist beige carpet, the lens resting on the floor. The camera is physically picked up by a hand, tilting up to eye level, revealing empty winding hallways. The camera bobs slightly in place. Endless maze of yellow patterned wallpaper, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
3: "[First-person POV, static hold turning to slow physical pan] Continuing to hold at eye level, the camera bobs slightly in place as it slowly pans to the left, showing a blank yellow wall, then steadily pans all the way back to the right, showing an identical empty yellow room. Endless backrooms maze, moist beige carpet, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
4: "[First-person POV, finishing pan turning to slow tracking shot] Finishing the right pan, the camera begins moving slowly and hesitantly forward down the yellow hallway, physically bobbing up and down with each slow footstep. The lens gradually approaches a dark, sharp corner of the wall for the entire duration of the clip. Endless backrooms maze, moist beige carpet, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
5: "[First-person POV, continuing slow tracking shot into sudden stop] Continuing the slow forward walk, the camera slowly steps around the sharp corner, physically panning right to reveal a flat, featureless wall blocking the path. The camera abruptly stops moving forward and shakes slightly up and down in exasperation, staring at the dead end. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
6: "[First-person POV, static hold turning to fast 180 whip pan] Staring at the dead end, the camera suddenly spins around 180 degrees to face the long hallway it just came from. The camera immediately begins walking steadily forward, bobbing up and down with a consistent walking pace down the center of the hall. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
7: "[First-person POV, steady walking turning to complete stop] Continuing the steady forward walk, the camera completely stops walking, holding still in the center of the hallway. The camera points straight down the long empty yellow hallway, maintaining a constant, subtle physical hand-shake for the entire duration, keeping the distant walls in focus. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
8: "[First-person POV, static hold turning to sudden jolt] Continuing to hold perfectly still, the bright fluorescent lights abruptly violently flicker and dim to near darkness, causing the camera to physically jolt downward toward the beige carpet in a startled reaction and hold there. Endless backrooms maze, harsh flickering fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
9: "[First-person POV, jolted hold turning to slow push] Continuing to stare at the floor, the camera slowly tilts up to look straight ahead. The lens reveals an impossibly long hallway stretching into infinity. The camera physically steps forward, slowly zooming in toward the dark shadows at the far end while bobbing slightly. Endless backrooms maze, harsh fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
10: "[First-person POV, continuing slow push] Continuing the slow forward walk, the camera walks steadily down the long yellow hallway, bobbing with each footstep. The camera approaches a bizarre carpeted staircase built directly into the floor, leading straight upward into a flat, solid ceiling with no doors or openings. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
11: "[First-person POV, continuing slow push into upward climb] Continuing to approach the stairs, the camera slowly climbs the carpeted steps, physically tilting up and bobbing heavily with each upward step. The camera stops moving forward just as the lens comes inches away from the solid, blank yellow ceiling blocking the top of the stairs. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
12: "[First-person POV, static hold turning to 180 whip pan] Staring inches away from the solid ceiling, the camera quickly turns around 180 degrees to look back down the stairs. The camera suddenly stops shaking, revealing a tiny, crooked, enclosed square room with no doors, completely replacing the long hallway. The camera slowly pans left across the crooked walls. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
13: "[First-person POV, finishing pan turning to upward tilt] Continuing to look across the small room, the camera physically looks up, panning the lens toward the top of the wall to reveal a standard electrical wall outlet installed completely upside down near the ceiling. The camera holds still on the outlet, shaking slightly. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
14: "[First-person POV, upward tilt turning to slanted tracking shot] Tilting back down to eye level, the camera walks down a long hallway that is sharply slanted downward at a 45-degree angle. The camera is held physically tilted to match the slant, bobbing irregularly as the person holding it slips slightly on the beige carpet while moving forward. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
15: "[First-person POV, continuing slanted walk into slow pan] Continuing to walk forward, the camera steps into a massive, cavernous room, bobbing continuously with each footstep. The camera slowly pans left to right across hundreds of thick, repeating structural pillars wrapped in yellow wallpaper stretching into the distance. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
16: "[First-person POV, slow pan turning to fast tracking shot] Pausing the pan, the camera quickly steps forward toward a specific yellow pillar, the camera bobbing heavily. The camera stops moving forward and physically pushes the lens inches away from messy black shoe scuff marks left on the yellow wallpaper, shaking rapidly with nervous energy. Endless backrooms maze, harsh buzzing fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
17: "[First-person POV, nervous hold turning to static shot] Staring at the scuff marks, the camera physically turns to stare straight down a long hallway, remaining physically still except for a natural hand-shake. The ceiling lights in the far distance shut off one by one in a cascading sequence, the heavy darkness rolling sequentially toward the camera lens until the hallway is nearly black. Endless backrooms maze, fading fluorescent overhead lighting, 1990s VHS camcorder aesthetic.",
18: "[First-person POV, static hold in darkness] Continuing to hold perfectly still in the dark, the camera clicks on a night vision light, illuminating a tight circular spotlight on the grainy damp beige carpet directly in front of the lens. The camera slowly sweeps the spotlight left and right across the empty floor, shaking nervously. Pitch-black backrooms hallway, zero ambient lighting with harsh camera flashlight, 1990s VHS camcorder aesthetic.",
}


def load_frame_map():
    inv = json.loads(INV.read_text(encoding="utf-8"))
    by_story = {f["story"]: Path(f["png"]) for f in inv["frames"]}
    ends = {}
    for n in range(1, 19):
        key = f"clip{n:02d}_end"
        if key not in by_story or not by_story[key].is_file():
            raise FileNotFoundError(f"missing end frame {key}")
        ends[n] = by_story[key]
    starts = {}
    starts[1] = by_story["clip01_start"]
    for n in range(2, 19):
        starts[n] = ends[n - 1]
    return starts, ends


def stage_input(src: Path, tag: str) -> str:
    h3.SHARED_INPUT.mkdir(parents=True, exist_ok=True)
    fname = f"vhs_{tag}{src.suffix.lower()}"
    dst = h3.SHARED_INPUT / fname
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dst)
    return fname


def free_comfy():
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"{h3.API}/free",
                data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=30,
        ).read()
        h3.emit("Posted /free unload_models")
    except Exception as exc:
        h3.emit(f"/free failed: {exc}")


def load_manifest():
    if MANIFEST.is_file():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"clips": {}, "updated_at": None}


def save_manifest(man):
    man["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(man, indent=2), encoding="utf-8")


def render_one(n: int, start_png: Path, end_png: Path, duration: float, man: dict) -> bool:
    clip_id = f"clip{n:02d}"
    existing = man["clips"].get(clip_id, {})
    if existing.get("status") == "ok" and existing.get("mp4") and Path(existing["mp4"]).is_file():
        h3.emit(f"{clip_id}: already ok -> {existing['mp4']}")
        return True
    prompt = PROMPTS[n]
    first = stage_input(start_png, f"{clip_id}_start")
    last = stage_input(end_png, f"{clip_id}_end")
    out_prefix = f"stories/vhs_minimax_flf2v/{clip_id}"
    seed = 2026090700 + n
    attempts = 0
    dur = duration
    while attempts < 3:
        attempts += 1
        h3.emit(f"{clip_id}: attempt {attempts} dur={dur}s first={first} last={last}")
        free_comfy()
        time.sleep(2)
        try:
            wf = h3.build_fl2va_workflow(
                clip_id, dur, first, prompt, seed, out_prefix, last_frame_file=last
            )
            # Override megapixels downward on retry
            if attempts >= 2:
                wf["115"]["inputs"]["megapixels"] = 0.6 if attempts == 2 else 0.4
                h3.emit(f"{clip_id}: lowered megapixels to {wf['115']['inputs']['megapixels']}")
            pid = h3.submit_workflow(wf)
            h3.emit(f"{clip_id}: submitted prompt_id={pid}")
            outputs = h3.wait_for_completion(pid, clip_id, timeout_s=3600)
            mp4 = h3.find_video_output(outputs)
            if not mp4 or not Path(mp4).is_file():
                # also search output dir by prefix
                cand = list((h3.SHARED_OUTPUT / "stories" / "vhs_minimax_flf2v").glob(f"{clip_id}*.mp4"))
                mp4 = str(cand[-1]) if cand else None
            if mp4 and Path(mp4).is_file():
                # copy into repo outputs for convenience
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                dest = OUT_DIR / Path(mp4).name
                if Path(mp4).resolve() != dest.resolve():
                    shutil.copy2(mp4, dest)
                    mp4 = str(dest)
                man["clips"][clip_id] = {
                    "status": "ok",
                    "mp4": mp4,
                    "bytes": Path(mp4).stat().st_size,
                    "prompt_id": pid,
                    "duration": dur,
                    "start": str(start_png),
                    "end": str(end_png),
                    "attempts": attempts,
                }
                save_manifest(man)
                h3.emit(f"{clip_id}: OK {mp4} ({Path(mp4).stat().st_size} bytes)")
                free_comfy()
                return True
            raise RuntimeError(f"no mp4 in outputs keys={list(outputs.keys())}")
        except Exception as exc:
            msg = str(exc)
            h3.emit(f"{clip_id}: FAIL attempt {attempts}: {msg}")
            man["clips"][clip_id] = {
                "status": "error",
                "error": msg,
                "attempts": attempts,
                "duration": dur,
            }
            save_manifest(man)
            free_comfy()
            if "out of memory" in msg.lower() or "oom" in msg.lower() or "cuda" in msg.lower():
                dur = max(3.0, dur - 1.5)
                continue
            if "ECONNREFUSED" in msg or "urlopen" in msg.lower() or "Connection" in msg:
                time.sleep(5)
                if not h3.api_ready():
                    h3.emit("Comfy down; restarting")
                    h3.start_comfy()
                continue
            # one more retry on unknown errors
            continue
    return False


def main():
    only = None
    if len(sys.argv) > 1:
        only = [int(x) for x in sys.argv[1:]]
    starts, ends = load_frame_map()
    man = load_manifest()
    if not h3.api_ready():
        h3.emit("Starting ComfyUI for fl2va…")
        h3.start_comfy()
    else:
        h3.emit("ComfyUI already up")
    nums = only or list(range(1, 19))
    ok = 0
    for n in nums:
        if render_one(n, starts[n], ends[n], DURATION, man):
            ok += 1
    free_comfy()
    h3.emit(f"DONE ok={ok}/{len(nums)} manifest={MANIFEST}")
    print(json.dumps(man, indent=2))


if __name__ == "__main__":
    main()
