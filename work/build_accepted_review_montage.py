import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
MANIFEST = PROJECT / "manifest.json"
OUT_DIR = PROJECT / "validation_contacts" / "accepted_montages"


def contact_for(clip_id: str, record: dict) -> Path | None:
    candidates = [
        record.get("validation_every_second"),
        record.get("validation_contact"),
        str(PROJECT / "validation_contacts" / f"{clip_id}_manual_overview.jpg"),
    ]
    for value in candidates:
        if value and Path(value).is_file():
            return Path(value)
    return None


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    accepted = [
        (clip_id, record, contact_for(clip_id, record))
        for clip_id, record in manifest["clips"].items()
        if record.get("status") == "valid"
    ]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=22)
    cell_w, cell_h = 640, 390
    columns, page_size = 3, 12
    pages = []
    for page_index in range(0, len(accepted), page_size):
        group = accepted[page_index : page_index + page_size]
        rows = (len(group) + columns - 1) // columns
        canvas = Image.new("RGB", (cell_w * columns, cell_h * rows), "#111111")
        draw = ImageDraw.Draw(canvas)
        for index, (clip_id, _record, contact) in enumerate(group):
            x = (index % columns) * cell_w
            y = (index // columns) * cell_h
            draw.text((x + 10, y + 8), clip_id, fill="white", font=font)
            if contact:
                with Image.open(contact) as source:
                    image = source.convert("RGB")
                    image.thumbnail((cell_w - 20, cell_h - 48), Image.Resampling.LANCZOS)
                    canvas.paste(image, (x + (cell_w - image.width) // 2, y + 40))
            else:
                draw.text((x + 10, y + 55), "MISSING REVIEW CONTACT", fill="#ff6961", font=font)
        page = OUT_DIR / f"accepted_{page_index // page_size + 1:02d}.jpg"
        canvas.save(page, quality=90)
        pages.append(str(page))
    report = {
        "accepted": len(accepted),
        "with_contact": sum(contact is not None for _, _, contact in accepted),
        "pages": pages,
    }
    (OUT_DIR / "montage_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
