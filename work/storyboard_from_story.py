#!/usr/bin/env python3
"""Persist a validated story-to-storyboard plan with a hard reference approval gate.

This is deliberately the non-GPU state half of the storyboard workflow. A local
reasoning model may create the structured input plan later, but this module does
not call a model, create frames, or start a render.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "outputs" / "stories"


class StoryboardError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(value: object, label: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value).strip()).strip("-_")
    if not clean or clean in {".", ".."}:
        raise StoryboardError(f"{label} must contain letters or numbers")
    return clean[:80]


def story_dir(story: str, root: Path = STORIES) -> Path:
    target = (root / _slug(story, "story")).resolve()
    if root.resolve() not in target.parents:
        raise StoryboardError("story output must remain under outputs/stories")
    return target


def _need_string(row: dict, key: str, label: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StoryboardError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def validate_plan(payload: object) -> dict:
    """Validate and normalise a model- or operator-produced storyboard plan."""
    if not isinstance(payload, dict):
        raise StoryboardError("storyboard plan must be a JSON object")
    characters = payload.get("characters")
    shots = payload.get("shots")
    if not isinstance(characters, list) or not characters:
        raise StoryboardError("storyboard plan requires a non-empty characters list")
    if not isinstance(shots, list) or not shots:
        raise StoryboardError("storyboard plan requires a non-empty shots list")
    normal_characters, ids = [], set()
    for index, row in enumerate(characters, 1):
        if not isinstance(row, dict):
            raise StoryboardError(f"character {index} must be an object")
        cid = _slug(row.get("id", ""), f"character {index} id")
        if cid.casefold() in ids:
            raise StoryboardError(f"duplicate character id: {cid}")
        ids.add(cid.casefold())
        identity = str(row.get("identity_source", "none")).strip().lower()
        if identity not in {"none", "registered_lora", "operator_reference"}:
            raise StoryboardError(f"character {cid} has invalid identity_source")
        normal_characters.append({
            "id": cid,
            "description": _need_string(row, "description", f"character {cid}"),
            "identity_source": identity,
        })
    normal_shots, shot_ids = [], set()
    required = ("scene", "setting", "lighting", "action", "camera", "prompt")
    for index, row in enumerate(shots, 1):
        if not isinstance(row, dict):
            raise StoryboardError(f"shot {index} must be an object")
        sid = _slug(row.get("id", ""), f"shot {index} id")
        if sid.casefold() in shot_ids:
            raise StoryboardError(f"duplicate shot id: {sid}")
        shot_ids.add(sid.casefold())
        people = row.get("characters")
        if not isinstance(people, list):
            raise StoryboardError(f"shot {sid}.characters must be a list")
        refs = [_slug(value, f"shot {sid} character") for value in people]
        unknown = [value for value in refs if value.casefold() not in ids]
        if unknown:
            raise StoryboardError(f"shot {sid} names unknown character(s): {', '.join(unknown)}")
        normal = {"id": sid, "characters": refs}
        normal.update({key: _need_string(row, key, f"shot {sid}") for key in required})
        normal_shots.append(normal)
    return {"version": 1, "characters": normal_characters, "shots": normal_shots}


def initialise(story: str, payload: object, *, root: Path = STORIES) -> dict:
    """Write only the plan/review state; neither model nor renderer is invoked."""
    plan = validate_plan(payload)
    directory = story_dir(story, root)
    directory.mkdir(parents=True, exist_ok=True)
    plan.update({"story": _slug(story, "story"), "created_at": _now()})
    (directory / "storyboard_plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    review = {
        "story": plan["story"],
        "reference_overview_approved": False,
        "reference_sheets": {},
        "created_at": _now(),
        "note": "No storyboard-frame plan may be released until reference overview approval.",
    }
    (directory / "reference_review.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    return {"story_dir": str(directory), "plan_path": str(directory / "storyboard_plan.json"),
            "review_path": str(directory / "reference_review.json"), "gpu_action": "none"}


def record_reference_sheets(story: str, sheets: dict[str, str], *, root: Path = STORIES) -> dict:
    """Record operator-reviewed relative sheet names; never copy or generate images."""
    directory = story_dir(story, root)
    try:
        plan = json.loads((directory / "storyboard_plan.json").read_text(encoding="utf-8"))
        review = json.loads((directory / "reference_review.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoryboardError("initialise the storyboard before recording reference sheets") from exc
    known = {row["id"].casefold() for row in plan["characters"]}
    if not isinstance(sheets, dict):
        raise StoryboardError("sheets must be a mapping of character id to relative filename")
    cleaned = {}
    for character, filename in sheets.items():
        cid = _slug(character, "character id")
        if cid.casefold() not in known:
            raise StoryboardError(f"unknown character in reference sheets: {cid}")
        name = Path(str(filename)).name
        if not name:
            raise StoryboardError("reference sheet filename is required")
        cleaned[cid] = name
    review["reference_sheets"] = cleaned
    review["reference_overview_approved"] = False
    review["updated_at"] = _now()
    (directory / "reference_review.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    return review


def approve_reference_overview(story: str, *, operator_confirmed: bool,
                               root: Path = STORIES) -> dict:
    """Require explicit approval and complete reference coverage before frames unlock."""
    if not operator_confirmed:
        raise StoryboardError("reference overview remains pending: explicit operator confirmation is required")
    directory = story_dir(story, root)
    try:
        plan = json.loads((directory / "storyboard_plan.json").read_text(encoding="utf-8"))
        review_path = directory / "reference_review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoryboardError("initialise the storyboard before approval") from exc
    missing = [row["id"] for row in plan["characters"]
               if row["id"] not in (review.get("reference_sheets") or {})]
    if missing:
        raise StoryboardError("reference overview cannot be approved; missing sheet(s): " + ", ".join(missing))
    review["reference_overview_approved"] = True
    review["approved_at"] = _now()
    review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    return review


def frame_plan(story: str, *, root: Path = STORIES) -> dict:
    """Return frames only after reference approval; it never invokes the renderer."""
    directory = story_dir(story, root)
    try:
        plan = json.loads((directory / "storyboard_plan.json").read_text(encoding="utf-8"))
        review = json.loads((directory / "reference_review.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoryboardError("initialise the storyboard before requesting frames") from exc
    if not review.get("reference_overview_approved"):
        raise StoryboardError("reference overview is pending approval; storyboard frames remain locked")
    return {
        "story": plan["story"], "frames_released": True, "gpu_action": "none",
        "shots": [{"id": shot["id"], "prompt": shot["prompt"], "characters": shot["characters"],
                   "reference_sheets": {character: review["reference_sheets"][character]
                                        for character in shot["characters"]}}
                  for shot in plan["shots"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init", help="validate and persist a structured shot plan")
    init.add_argument("--story", required=True)
    init.add_argument("--plan", required=True, type=Path)
    sheets = sub.add_parser("record-sheets", help="record reviewed reference-sheet filenames")
    sheets.add_argument("--story", required=True)
    sheets.add_argument("--sheets", required=True, type=Path)
    approve = sub.add_parser("approve-refs", help="unlock frame planning after review")
    approve.add_argument("--story", required=True)
    approve.add_argument("--confirm", action="store_true")
    frames = sub.add_parser("frame-plan", help="show frames after approval")
    frames.add_argument("--story", required=True)
    args = parser.parse_args()
    try:
        if args.action == "init":
            result = initialise(args.story, json.loads(args.plan.read_text(encoding="utf-8")))
        elif args.action == "record-sheets":
            result = record_reference_sheets(args.story, json.loads(args.sheets.read_text(encoding="utf-8")))
        elif args.action == "approve-refs":
            result = approve_reference_overview(args.story, operator_confirmed=args.confirm)
        else:
            result = frame_plan(args.story)
    except (OSError, json.JSONDecodeError, StoryboardError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
