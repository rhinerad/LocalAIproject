#!/usr/bin/env python3
"""Offline checks for prompt-aware creative stills QA."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import creative_still_qa as q

def main() -> int:
    stills = Path(r"A:\Users\rhine\ComfyUI-Shared\input\astra_backrooms_stills")
    clips = {c["id"]: c for c in json.loads((ROOT / "outputs_compile" / "clips_compiled.json").read_text(encoding="utf-8"))["clips"]}
    fails = []
    # 1) known identity/room mismatch must fail
    c = clips["C001"]
    rep = q.compare_stills(candidate=stills/"C001_start.png", anchor=stills/"C001_last.png", prompt=c["start_frame"], clip=c, kind="start")
    if rep["ok"]:
        fails.append("C001_start_vs_last_should_fail")
    # 2) self match pass
    rep2 = q.compare_stills(candidate=stills/"C001_last.png", anchor=stills/"C001_last.png", prompt=c["last_frame"], clip=c, kind="last")
    if not rep2["ok"]:
        fails.append(f"self_match_failed:{rep2['reject_reasons']}")
    # 3) empty expectation: missing face must NOT be a reason
    empty_prompt = (
        "Backrooms yellow wallpaper empty corridor. Handheld camcorder POV; "
        "camcorder body lens and operator are completely outside the frame. "
        "No character visible in frame. Static environment only."
    )
    exp = q.infer_visibility_expectation(prompt=empty_prompt)
    if not exp.expect_empty_of_people or exp.expect_actor_visible:
        fails.append(f"empty_expectation_wrong:{exp}")
    # Synthetic: compare identical empty-ish image against itself under empty prompt should pass face-absent
    # Use C001_last as stand-in only for expectation unit (not ideal). Better: if no face, empty mode ok.
    # Unit: if we force empty mode on an image with faces, unexpected_face fires — that is correct.
    # Unit: expectation parser for actor prompt
    exp_a = q.infer_visibility_expectation(prompt=c["last_frame"])
    if not exp_a.expect_actor_visible:
        fails.append(f"actor_expectation_wrong:{exp_a}")
    print({"ok": not fails, "fails": fails, "sample_mismatch_reasons": rep["reject_reasons"], "empty_exp": exp})
    return 0 if not fails else 1

if __name__ == "__main__":
    raise SystemExit(main())
