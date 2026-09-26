# 2026-09-21j Isolated CPU WD14 tagger

- `gvd_qa/wd14_cpu.py`: download and pin `wd-v1-4-moat-tagger-v2` ONNX+CSV under `local_agent/runtime/gvd_qa/wd14_models`. Inference uses `CPUExecutionProvider` only. Does not write Rockernow `custom_nodes` or the live pysssss CUDA provider list.
- `cpu_wd14_fn` feeds `LocalQaClient` the same `outputs["30"]["tags"]` string shape as `WD14Tagger|pysssss`.
- Smoke: `python local_agent/gvd_qa/smoke_wd14_cpu.py` tags `br24_C017_start_00001_.png` and writes `local_agent/runtime/gvd_qa/smoke_wd14_cpu.json`.
- Offline tests: `python local_agent/test_gvd_qa_wd14_cpu.py`.
- Live 5080 CPU smoke on `br24_C017_start_00001_.png`: providers `CPUExecutionProvider`; tags `solo, long sleeves, 1boy, holding, male focus, shoes, black footwear, camera, photo background, holding camera`; VRAM stayed 355 MiB. Report: `local_agent/runtime/gvd_qa/smoke_wd14_cpu.json`.
