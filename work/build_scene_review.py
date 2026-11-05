import json
import subprocess
import sys
from pathlib import Path

project = Path(sys.argv[1])
scene_number = int(sys.argv[2])
scene_dir = project / "frames" / f"scene_{scene_number:03d}"
inputs = []
for index in range(7):
    inputs.extend(["-i", str(scene_dir / f"boundary_{index:02d}.png")])
inputs.extend(["-f", "lavfi", "-i", "color=c=black:s=640x360"])
filters = ";".join(f"[{index}:v]scale=640:360[{chr(97+index)}]" for index in range(7))
filters += ";[7:v]null[h];[a][b][c][d][e][f][g][h]xstack=inputs=8:layout=0_0|640_0|0_360|640_360|0_720|640_720|0_1080|640_1080[out]"
review_path = scene_dir / f"scene_{scene_number:03d}_review_sheet.jpg"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", filters, "-map", "[out]", "-frames:v", "1", "-update", "1", str(review_path)], check=True)

manifest_path = project / "frame_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
scene_prefix = f"scene_{scene_number:03d}_"
for frame in manifest["frames"]:
    if frame["id"].startswith(scene_prefix):
        frame["status"] = "generated_awaiting_final_review"
        frame["generated_with"] = "ChatGPT image generation"
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(review_path)
