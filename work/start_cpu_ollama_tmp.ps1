$ErrorActionPreference = "Continue"
$env:OLLAMA_HOST = "127.0.0.1:11435"
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_KEEP_ALIVE = "0"
$log = "A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\OPEN_INTERPRETER_CPU_OLLAMA.log"
& "A:\Users\rhine\AppData\Local\Programs\Ollama\ollama.exe" serve *>> $log
