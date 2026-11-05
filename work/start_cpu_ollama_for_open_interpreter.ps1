$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$LogPath = Join-Path $Root 'COMFYUI_STORY_HANDOFF_2026-08-09\OPEN_INTERPRETER_CPU_OLLAMA.log'
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_KEEP_ALIVE = '0'
& 'A:\Users\rhine\AppData\Local\Programs\Ollama\ollama.exe' serve *>> $LogPath

