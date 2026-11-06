# CHANGELOG 2026-09-21 — empty-POV people/body QA

## Problem
Face-only YuNet QA passed Backrooms empty-POV stills that still contained people/bodies (e.g. slumped figure in C015_last with no visible face).

## Fix
- `creative_still_qa.py`: tiled YOLOv8n person detection (+ SSD fallback) on empty-POV path; fail-closed on any person OR face.
- Verified FAIL on operator-rejected C015–C018 last frames (C015 caught via tile at conf≈0.10).
- `flux_still_batch.py`: for empty-POV clips, prepend vacant POV language and append strong no-people negatives before render.
- Models: `models/opencv_person/yolov8n.pt|.onnx`, `ssd_mobilenet_v1_10.onnx`.

## Status
Generation remains PAUSED until Rhine re-approves pilot regen.
