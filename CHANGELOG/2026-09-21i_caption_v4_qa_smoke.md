# 2026-09-21i Caption V4 still checklist

- `gvd_qa/caption_v4.py`: per-criterion JSON checklist through owned llama.cpp on `:11436`.
- `gvd_qa/smoke_caption_v4.py`: `/free` Comfy, `prepare_for_vlm`, start owned Caption V4, judge one Backrooms still, `release_after_vlm`.
- Offline parse tests: `python local_agent/test_gvd_qa_caption_v4.py`.
- Live 5080 smoke: Caption V4 peaked at 10888 MiB on `br24_C017_start_00001_.png`; yellow_walls=fail, person_visible=pass; VRAM returned to ~359 MiB after release. Report: `local_agent/runtime/gvd_qa/smoke_caption_v4.json`.
