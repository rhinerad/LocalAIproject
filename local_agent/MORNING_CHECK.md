# Morning check — the one thing left to verify

Everything else on the acceptance list is green. All 14 tools confirmed in place;
everything built in the prior session is holding.

## The gap

**GPU-idle → GPU-tier routing has never been exercised.** Port 8188 was listening
for the entire session, so the router correctly reported BUSY every time and the
GPU path was never taken. It is untested, not broken — but untested is untested.

## Do this with ComfyUI CLOSED

```powershell
python local_agent\router.py
```

**Expected:**

```
routing to : GPU  qwen2.5-coder:14b  @ 127.0.0.1:11434
```

If it says GPU with that model, the whole routing chain is verified.

## Then one question through the GUI

Send any project question and confirm the route event shows **tier=gpu**.

That second step matters for a reason beyond routing: it is also the first real
test of whether **`qwen2.5-coder:14b` follows the `TOOL:` protocol**. That was
never exercised either, because the card was occupied all session and every reply
came from the CPU tier.

## If it ignores the protocol

If `qwen2.5-coder:14b` answers project questions from memory the way `qwen3:8b`
did, the fix is one line:

```python
# local_agent/router.py — move dolphin3 to the front
GPU_MODELS = ["dolphin3:latest", "equal-shares-gpu", "equal-shares", ...]
```

Worth checking **before** relying on it for project questions. A model that
answers counts and clip details from memory instead of calling a tool is exactly
the failure mode this project has been burned by repeatedly — a confident wrong
answer costs more than an honest "I don't know".

## Quick sanity trio, if you want it

```powershell
python local_agent\validate_h3_prompt.py --dir outputs\equal_shares\prompts_native_r2v
python local_agent\tools.py
python work\classify_voice_requirements.py --check
```

Expect **124/124 valid**, 14 actions listed, and 18 speakers = 10 recurring + 8
one-off.
