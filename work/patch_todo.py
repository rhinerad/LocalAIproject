from pathlib import Path
p = Path("TODO.md")
t = p.read_text(encoding="utf-8")
if "stills batch + review gate" in t:
    print("TODO already has note")
else:
    note = (
        "\n## Done — stills batch + review gate (2026-09-06o / r93)\n\n"
        "- [x] render_story_image_batch sequential still queue\n"
        "- [x] Review gate before video (approve_story_stills)\n"
        "- [x] Stale pid_running when owner released\n"
        "- [x] Unit tests + APP_REVISION r93 (restart to load tools)\n\n"
    )
    lines = t.splitlines(True)
    insert_at = 0
    for i, line in enumerate(lines[:40]):
        if line.startswith("# "):
            insert_at = i + 1
            break
    lines.insert(insert_at, note)
    p.write_text("".join(lines), encoding="utf-8")
    print("TODO updated")
