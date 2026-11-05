import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"

replacements = [
    (r"\bMara Vale\b", "Alex Vale"),
    (r"\bMara's\b", "Alex's"),
    (r"\bMara\b", "Alex"),
    (r"\bmara\b", "alex"),
    (r"an indebted caregiver and her wealthy brother", "an indebted caregiver and his wealthy brother"),
    (r"her eviction proceeds", "his eviction proceeds"),
    (r"society validates her feelings", "society validates his feelings"),
    (r"while she hides medical invoices", "while he hides medical invoices"),
    (r"After he leaves, she retrieves", "After he leaves, Alex retrieves"),
    (r"Alex says she would never", "Alex says he would never"),
    (r"She sorts donations while exhausted because she cannot", "He sorts donations while exhausted because he cannot"),
    (r"Her ledger thanks her", "His ledger thanks him"),
    (r"She wraps the bracelet", "He wraps the bracelet"),
    (r"Her bare wrist", "His bare wrist"),
    (r"stop her eviction", "stop his eviction"),
    (r"softens her words", "softens his words"),
    (r"She thanks the council", "He thanks the council"),
    (r"She writes 'UNFAIR'", "He writes 'UNFAIR'"),
    (r"She begins noting", "He begins noting"),
    (r"She helps others", "He helps others"),
    (r"missing her own housing", "missing his own housing"),
    (r"on her mother's loving face", "on his mother's loving face"),
    (r"She writes a short council statement", "He writes a short council statement"),
    (r"reminds her that", "reminds him that"),
    (r"with her statement", "with his statement"),
    (r"reset for her", "reset for him"),
    (r"She says: 'Everyone", "He says: 'Everyone"),
    (r"for her courage", "for his courage"),
    (r"reaches for her hand", "reaches for his hand"),
    (r"validates her pain", "validates his pain"),
    (r"offers Alex a support liaison", "offers Alex a support liaison"),
    (r"Behind her, the equal-aid", "Behind him, the equal-aid"),
]


def recast_text(text):
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def recast(value):
    if isinstance(value, dict):
        return {recast_text(key): recast(item) for key, item in value.items()}
    if isinstance(value, list):
        return [recast(item) for item in value]
    if isinstance(value, str):
        return recast_text(value)
    return value


bible_path = PROJECT / "story_bible.json"
bible = recast(json.loads(bible_path.read_text(encoding="utf-8")))
lead = next(character for character in bible["characters"] if character["id"] == "alex")
lead.update({
    "name": "Alex Vale",
    "role": "protagonist; underpaid home-care aide who cared for his mother",
    "age_description": "adult man in his 30s",
    "immutable_appearance": "recognizable identity matching the approved reference: light-to-medium skin, expressive brown eyes, short dark receding hair, distinctive neat dark mustache, prominent brows, gently rounded face, average build",
    "default_wardrobe": "faded teal cardigan, cream button-up shirt, charcoal trousers, worn brown shoes, canvas shoulder bag",
    "voice": "soft conversational tenor, careful diction, pauses before difficult truths",
    "motivation": "keep his apartment and understand why universal kindness has not protected him",
    "reference_images": ["references/alex_vale_source.jpg", "references/alex_vale_master_v1.png"],
    "forbidden_drift": ["different facial identity", "missing or altered mustache", "different hairline or hair color", "unexplained wardrobe change", "unexplained age change", "exaggerated muscular build"]
})
bible_path.write_text(json.dumps(bible, indent=2, ensure_ascii=False), encoding="utf-8")

plan_path = PROJECT / "shot_plan.json"
plan = recast(json.loads(plan_path.read_text(encoding="utf-8")))
plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

treatment_path = PROJECT / "STORY_TREATMENT.md"
print("recast Equal Shares with Alex Vale as protagonist")
