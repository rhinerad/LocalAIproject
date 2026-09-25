# Project context for Claude

- **User setup:** Windows + PowerShell. RTX 5080 (16 GB VRAM, Blackwell/sm_120 — needs CUDA 12.8+ / PyTorch cu128 builds), Ryzen 7 9800X3D.
- **Local project root:** `A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09`
- **Services (localhost only):** ComfyUI API `http://127.0.0.1:8188` (`/prompt`, `/history/{id}`, `/view`, `/ws`); Ollama `http://127.0.0.1:11434` (`/api/generate`, `/api/chat`).
- The cloud container cannot reach these services. Write code that runs on the user's machine; mock/guard network calls if you need to test here. Never hardcode Linux paths — use `pathlib`/relative paths or the root above.
- Scripts must be PowerShell (not bash) for anything the user runs directly.
- Workflow: user runs `sync_down.bat` to pull, tests locally, then `sync_up.bat` to push logs/debug output. Read those commits for results.
- When a feature is finalized, commit with a descriptive message and push to the session branch.
