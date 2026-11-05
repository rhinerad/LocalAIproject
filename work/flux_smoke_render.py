import json, urllib.request

prompt = (
    "First-person POV from a retro 1990s VHS camcorder. The date and time "
    "\"AUG 09 1998\" are in the bottom left corner in white VCR font. A skater "
    "wearing baggy jeans and a colorful graphic tee is in mid-air performing a "
    "board slide on a metal handrail at a sunny outdoor concrete skatepark. "
    "Heavy motion blur, amateur filming style, realistic bright sunlight."
)
body = {
    "action": "render_story_image",
    "args": {
        "story": "vhs_liminal_space_story",
        "prompt": prompt,
        "model_profile": "realpro_flux",
        "mode": "t2i",
        "seed": 42,
        "width": 768,
        "height": 512,
        "steps": 8,
        "hires_fix": False,
        "face_detail": False,
    },
}
req = urllib.request.Request(
    "http://127.0.0.1:8760/api/action",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as resp:
    raw = resp.read().decode("utf-8", errors="replace")
print(raw[:4000])
