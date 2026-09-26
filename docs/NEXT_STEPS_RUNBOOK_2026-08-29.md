# Next-steps runbook — written for zero prior knowledge (2026-08-29)

This assumes you've never run a command in a terminal before. Every command
is something you type yourself on your Windows computer — nothing here runs
by itself, and nothing here happens just from reading this document.

## The basics you need before any of the sections below

**What's a "terminal" / "PowerShell window"?** It's a plain black or dark-blue
window where you type text commands instead of clicking icons. You'll open
one, type a line of text, press **Enter**, and it does something and prints
text back at you.

**Two different kinds of PowerShell window matter here:**
- **Ordinary PowerShell** — click the Start button, type `powershell`, press
  Enter. Fine for sections 2, 3, and 4 below.
- **"Developer PowerShell for VS 2022"** — a special version that also knows
  where your CUDA/compiler tools live. Required for section 1 (PowerInfer).
  Click Start, type `developer powershell`, and click the result called
  **"Developer PowerShell for VS 2022"** (not plain PowerShell, not "Developer
  Command Prompt"). If it's not there, Visual Studio 2022 with the Desktop
  C++ workload needs installing first — stop and say so if that's the case.
  Section 1 also needs CUDA Toolkit 12.8+ (`nvcc`, targeting `sm_120`)
  already installed; if that's missing, stop there too. This document does
  not walk through those installs.

**How to get to the right folder.** Every section below starts by pasting
this into whichever PowerShell window you just opened:

```powershell
cd "A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09"
```

Press Enter. Nothing dramatic happens — the prompt just changes to show
you're now "in" that folder. If you see a red error instead, the path is
wrong; double check it matches the folder on your machine exactly.

**How to copy a command from this document into the window.** Select the
text of the command in this document (click and drag over it, or triple-click
the line), press **Ctrl+C**, click inside the PowerShell window so it's the
active window, then press **Ctrl+V** (or right-click, which also pastes in
PowerShell). Then press **Enter** to actually run it — pasting alone does not
run it.

**How to tell if a command worked.** After it finishes, look at the last few
lines it printed:
- Red text starting with something like `Exception` or ending in
  `throw` usually means it failed. Read the message — the scripts in this
  project are written to explain in plain English *why* they refused, not
  just "error 1."
- If it just returns you to a normal prompt with no red text, it worked.
- Some steps also print their own "ok" / "done" / a summary — those are
  designed to be readable, not just log noise.

**If anything prints something you don't understand and it's not obviously
one of the "expected" messages below**, stop and paste the exact text back
to me (or the next Claude session) rather than guessing and continuing.

---

## Section 1 — PowerInfer: prove the pipeline works on `relu-llama-7b`

This is the live, already-compatible sparse model to test with first
(`SparseLLM/ReluLLaMA-7B`, plain ReLU, `hidden_act` is `relu`) before ever
touching your actual Llama-3.1 model. It downloads several gigabytes and
uses your graphics card, so budget real time for this — the "train" step
especially can take a long while.

**Do not use `-ModelId prosparse-7b`.** That id is parked and retired.
The checkpoint already on disk at
`C:\PowerInferVault\prosparse-7b\20260829-prosparse` is FATReLU /
`SparseLlamaForCausalLM`, not plain ReLU. Running the relu-gate on that
vault is **expected to fail** with exit code 2. That is not a broken
download. Do not continue past a FATReLU fail. Do not bypass the gate.
Do not tell anyone (including another LLM session) to skip this check
or to treat ProSparse as the thing to compile and run.

### 1.0 — Before you type anything: two tools must already be installed,
and the graphics card must be free

This section compiles a C++/CUDA program. That will not work unless
**both** of these are already on this computer:

1. **CUDA Toolkit 12.8 or newer**, with `nvcc` (the CUDA compiler) that
   can target **`sm_120`** (that's this computer's graphics-card
   architecture).
2. **Visual Studio 2022** with the **Desktop C++** workload.

If either is missing, **stop here.** Do not continue Section 1. Do not
try to compile anyway. Tell the next session which one is missing.
This document does not walk through installing those — they are
operator installs, not something to guess at from click-paths.

You also must use **"Developer PowerShell for VS 2022"** (see the
basics at the top of this document), not ordinary PowerShell, for
every compile step in this section. Developer PowerShell is the window
that knows where the CUDA/compiler tools live.

Open that Developer PowerShell window, then type:

```powershell
nvcc --version
```

and press Enter. You want a version of **12.8 or higher**. If it says
the command is not recognized, you either opened the wrong PowerShell
window, or CUDA Toolkit isn't installed. **Stop.** If the version is
older than 12.8, **stop.**

Then check the graphics card is free. In the same window, type:

```powershell
nvidia-smi
```

and press Enter. You'll see a table. Near the bottom is a list of
"Processes" — this shows anything currently using the graphics card. As long
as ComfyUI, a render, or anything you don't recognize isn't listed there,
you're clear to continue. If something IS using it, close that program first.

### 1.1 — Go to the project folder, and point the vault at C:\PowerInferVault

```powershell
cd "A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09"
$env:POWERINFER_VAULT = "C:\PowerInferVault"
```

Press Enter after each line. Nothing dramatic happens — the prompt just
changes to show you're now "in" that folder, and the vault variable is set
for this window only.

This computer's model vault lives at `C:\PowerInferVault` — not a D:
drive, and not inside this project's own folder. Setting
`$env:POWERINFER_VAULT` only lasts for this PowerShell window. If you close
the window or open a new one, paste both lines again before any other
pipeline command.

### 1.2 — Preview the plan (this step is 100% safe — it doesn't download,
build, or touch the graphics card at all)

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage show
```

You'll see a block of text listing things like `model_id`, `route`,
`vault/bundle`, etc. Things to check in that printout:

- The line `model_id` should say `relu-llama-7b`, not `prosparse-7b`. If
  it says `prosparse-7b`, you used the parked id — stop and use
  `relu-llama-7b`.
- The line `vault/bundle` should point somewhere under
  `C:\PowerInferVault\relu-llama-7b\...`. If it points at a D: drive,
  at this project's `artifacts` folder, or at `...\prosparse-7b\...`,
  you either forgot the `$env:POWERINFER_VAULT` line from step 1.1 or
  used the parked id. Fix that, then rerun this preview. Do not continue
  with the wrong vault.
- The line `vram-budget` will say
  `(not set -- required before validate/bench)` — that's expected right now,
  you'll supply a real number much later in step 1.10.

If instead you see red text saying something about the vault being "inside
the git repository" — that only happens much later at step 1.6 onward if
you forgot the vault line, not here at step 1.2, so ignore that for now.

### 1.3 — Download and build PowerInfer itself (this is the big one — expect
several minutes to tens of minutes depending on your internet and CPU)

Only do this after step 1.0 showed `nvcc` 12.8+ and Developer PowerShell
for VS 2022. If those were missing, you should have already stopped.

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage setup -Execute
```

What this does, in order: downloads the PowerInfer source code from GitHub,
creates a private Python environment just for this tool, installs a bunch of
Python packages (including a large one for CUDA — this is the slow download
part), then compiles the C++/CUDA program itself (the slow CPU part).

**If it stops early with `nvcc not on PATH`:** you opened plain PowerShell
instead of "Developer PowerShell for VS 2022," or CUDA Toolkit isn't
installed. Close this window. If Developer PowerShell + CUDA 12.8+ are
actually missing, **stop** (see step 1.0). If you just opened the wrong
window, reopen the correct one, repeat step 1.1, and start again from
step 1.1.

**When it finishes successfully**, the last lines will just return you to a
normal prompt with no red text. That's it — no special celebration message,
just no errors.

### 1.4 — Download the actual model weights

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage intake -Execute
```

This downloads the `SparseLLM/ReluLLaMA-7B` model from Hugging Face — a few
gigabytes. Just wait for it to finish; you'll see a progress readout while
it downloads. Do **not** substitute `prosparse-llama-2-7b` / `prosparse-7b`
here. That snapshot is the parked FATReLU checkpoint.

### 1.5 — Confirm the download is the right kind of model (fast, seconds)

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage relu-gate
```

Note: no `-Execute` needed for this one specifically — it's just a quick
check, not real work.

On ReluLLaMA (`hidden_act` `relu`, `model_type` `llama`) it should pass
almost instantly.

**If it fails with exit code 2 and a reason about FATReLU** — that is the
parked ProSparse vault (`hidden_act=fatrelu`, `SparseLlamaForCausalLM`).
That fail is **expected** for ProSparse. **Stop.** Do not continue. Do not
bypass the gate. Do not pass `-Force`. Do not comment out the check. Do
not tell the operator (or another LLM) to keep going. If you used
`-ModelId prosparse-7b` by mistake, switch back to `relu-llama-7b` and
rerun this check on the ReluLLaMA vault only. If ReluLLaMA itself fails
the gate, stop and paste the printed JSON back rather than guessing.

**If it fails for any other reason** — don't continue past this point until
it passes, and don't skip the gate to "just try dump."

### 1.6 — Build the calibration data

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage calib -Execute
```

**If this refuses and says the vault path is "inside the git repository"** —
you forgot the `$env:POWERINFER_VAULT = "C:\PowerInferVault"` line from
step 1.1 (it only lasts for this window). Paste that line, press Enter,
then run the step 1.6 command again. Do not let the tool write large
files into this project's own folder.

### 1.7 — Dump activations (this one actually uses the graphics card)

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage dump -Execute
```

Before doing anything, this automatically checks the GPU is free the same
way you manually checked in step 1.0 — if something's using the card, it'll
refuse and tell you what's using it. Close that program and rerun.

This step can take a while; it's doing real GPU work.

### 1.8 — Train the predictors (the slowest step — can take a long time)

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage train -Execute
```

Just let this run. There's no way to meaningfully speed it up; go do
something else and check back.

### 1.9 — Convert and compress the model

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage convert -Execute
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage quantize -Execute
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage package -Execute
```

Three separate commands — run them one at a time, waiting for each to finish
and show no red text before typing the next.

### 1.10 — Test it actually runs, and measure how fast it is

First, check how much free video memory you currently have:

```powershell
nvidia-smi
```

Look for a line like `12000MiB / 16384MiB` under memory usage — that means
12,000 used out of 16,384 total, so roughly 4,000 MiB (4 GB) is free. Pick a
number for the next command that's comfortably **below** whatever is
currently free, in whole gigabytes. If you have no idea and the card looks
basically empty, `12` is a reasonable starting number for a 16 GB card.

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage validate -Execute -VramBudget 12
```

(Replace `12` with your own chosen number if different.) This runs a tiny
16-word test generation. If it errors immediately saying you must pass
`-VramBudget`, you forgot that part of the command — copy it again exactly.

If that works, run the full benchmark:

```powershell
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage bench -Execute -VramBudget 12
```

This one actually matters as evidence — it writes a file with real numbers
(speed, memory used, etc.) rather than just "it ran." You'll find it at:

```
<the vault/bundle folder printed back in step 1.2>\validation\acceptance_gate.json
```

Open that file in Notepad afterward and skim it — that's the proof this
whole thing actually works, not just "no red text."

### What NOT to do yet

Don't try any of this on `-ModelId prosparse-7b`. It is parked because
FATReLU / `SparseLlamaForCausalLM`. The relu-gate on that vault is
expected to fail (exit 2). Do not continue past that fail. Do not bypass
the gate.

Don't try any of this on your actual Llama-3.1 model (`llama31-8b-abliterated-relu`
in the tool). It needs a version of that model that's already been through a
separate training process nobody has done yet — running the pipeline on the
model you currently have will just fail on purpose at step 1.5's equivalent.

---

## Section 1B — Actually talk to it: start the server and connect local_agent

This is what makes Section 1's work useful instead of just a file sitting on
disk. Two programs need to run at once: the PowerInfer server itself (which
loads the model and talks to the GPU), and a small translator program called
the "proxy" (which makes it speak the same language your local_agent chat
already understands). Do this only after Section 1 finished all the way
through step 1.10 successfully.

**Important boundary, so you know what this does and doesn't do yet:** this
gets you a real, working chat endpoint you can talk to directly. It does
**not** yet make this model show up as a pickable option inside your normal
local_agent chat window — that's a separate, bigger step (changing
`router.py` and the model picker) that hasn't been built, on purpose, until
this basic serving path is proven out first. Once you've confirmed this
works, say so and that picker-integration work can start.

### 1B.1 — Figure out the exact model file path

Go back to the text your terminal printed in step 1.2 (the `-Stage show`
preview) and find the `vault/bundle` line — that's a folder path. Your
model file is inside that folder at:

```
<that bundle path>\output\relu-llama-7b.q4.powerinfer.gguf
```

For example, if `vault/bundle` printed as
`C:\PowerInferVault\relu-llama-7b\20260829-141500`, your model file is at
`C:\PowerInferVault\relu-llama-7b\20260829-141500\output\relu-llama-7b.q4.powerinfer.gguf`.
Confirm the file actually exists there (type `dir` after `cd`-ing into that
`output` folder, or just look in File Explorer) before continuing — if
Section 1 finished cleanly, it'll be there.

### 1B.2 — Start the PowerInfer server (leave this window open the whole time)

Open the "Developer PowerShell for VS 2022" window again, go to the project
folder, then run this — replacing the model path with your own from 1B.1,
and the VRAM number with whatever you used in step 1.10:

```powershell
cd "A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09"
.\external\PowerInfer\build\bin\Release\server.exe -m "<your model path from 1B.1>" --vram-budget 12 -t 8 -c 2048 --host 127.0.0.1 --port 8080 -a powerinfer-local
```

You should see it print that it's loaded the model and is listening on
`127.0.0.1:8080`. **Leave this window open** — closing it stops the server.
If it errors about VRAM, lower the `--vram-budget` number; if it errors
about the file not being found, re-check the path from 1B.1 for typos.

### 1B.3 — Start the proxy (a second, separate window)

Open a **new** plain PowerShell window (doesn't need the Developer version
for this one), go to the project folder, then:

```powershell
cd "A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09"
$env:POWERINFER_BACKEND_URL = "http://127.0.0.1:8080"
$env:POWERINFER_MODEL_ALIAS = "powerinfer-local"
$env:POWERINFER_PROXY_API_KEY = "just-a-local-secret-you-make-up"
python local_agent\powerinfer_openai_proxy.py
```

The `POWERINFER_PROXY_API_KEY` value can be any text you want — it's just a
local password between your own two programs on your own computer, not
something that leaves your machine. It should print that it's listening on
`127.0.0.1:8091`. **Leave this window open too.**

### 1B.4 — Actually send it a message

Open a **third** PowerShell window and run:

```powershell
$body = @{
    model = "powerinfer-local"
    messages = @(@{ role = "user"; content = "Say hello in one short sentence." })
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8091/v1/chat/completions" `
    -Method Post `
    -Headers @{ Authorization = "Bearer just-a-local-secret-you-make-up" } `
    -ContentType "application/json" `
    -Body $body
```

(Use the exact same text you picked for `POWERINFER_PROXY_API_KEY` in the
`Authorization` line — they have to match.) If everything's working, you'll
get back a reply with the model's actual answer inside it. That's it — you
just had a real conversation with your own PowerInfer model.

### When you're done testing

Close the two windows from 1B.2 and 1B.3 (or press Ctrl+C inside each) to
stop the server and proxy — there's no reason to leave a GPU model loaded
when you're not using it.


## Section 2 — Feed the worker farm a real conversation export

Do this only when you're genuinely ready to have a real ChatGPT/Claude
export processed. It's encrypted at rest and nothing gets added to memory
automatically — you review the output before anything is trusted — but it
is still your real data going through the pipeline, so this is a deliberate
step, not a routine one.

### 2.1 — Start the two background pieces (each in its own window)

Open a normal PowerShell window (Start → type `powershell` → Enter), go to
the project folder (paste the `cd "..."` line from the top of this
document), then:

```powershell
local_agent\worker_farm\START_PHASE1_BROKER.ps1
```

Wait for it to finish printing and settle (no more new lines appearing for a
few seconds). **Leave this window open** — closing it stops the broker.

Now open a **second, separate** PowerShell window (same Start-menu steps),
`cd` into the project folder again in that new window, and run:

```powershell
local_agent\worker_farm\START_PHASE1_CPU_WORKER.ps1
```

You should see a line saying it's starting a worker on the `distill` queue.
**Leave this window open too.**

### 2.2 — Submit your file, in a third window

Open a **third** PowerShell window, `cd` into the project folder, then:

```powershell
local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.submit_distillation "C:\path\to\your\export.json"
```

Replace `C:\path\to\your\export.json` with the actual full path to your
export file on your computer (drag the file into the PowerShell window after
typing the opening quote — Windows will paste its full path for you
automatically). It needs to be a `.json`, `.html`, or `.txt` file and under
25 MB.

You'll get back a short printed summary including a `job_id` and
`"status": "queued"`.

### 2.3 — Check on it

```powershell
local_agent\worker_farm\SHOW_PHASE1_STATUS.ps1
```

Once it's done, the status will say `completed`. Nothing further happens
automatically — the extracted candidates sit there encrypted, waiting for
you to look at them, before anything is ever promoted into real memory.

---

## Section 3 — Add a second worker laptop (on hold for now)

Correction from earlier: the laptop is actually a **Mac**, not Windows — the
walkthrough below was written for Windows on both ends and is wrong for a
Mac (different WireGuard app, different install steps, different way of
finding the IP address). Since PowerInfer + local_agent (Sections 1 and 1B)
is the actual priority right now, this section is left as-is rather than
rewritten twice — say when you're ready to come back to it and it'll get
redone with correct Mac steps for the laptop side and Windows steps for the
workstation side.

This connects two machines over an encrypted private tunnel so the laptop
can safely reach the workstation's task queue. It has more moving parts than
the sections above — go slowly and confirm each piece before moving to the
next.

### 3.1 — Install WireGuard on both machines

On **both** the workstation and the laptop:

1. Open a browser, go to `https://www.wireguard.com/install/`.
2. Download and run the **Windows** installer.
3. Once installed, open the "WireGuard" app from the Start menu. It shows an
   empty list of tunnels.

### 3.2 — Find each machine's local network address

On **each** machine (workstation and laptop, separately), open plain
PowerShell and type:

```powershell
ipconfig
```

Look for a section called `Wireless LAN adapter Wi-Fi` (or `Ethernet
adapter` if it's wired) and find the line `IPv4 Address`. It'll look like
`192.168.1.XX`. Write down the workstation's number and the laptop's number
— you'll need both in the next step.

### 3.3 — Create the tunnel on the workstation

In the WireGuard app on the **workstation**, click **"Add Tunnel"** →
**"Add empty tunnel..."**. It creates a new tunnel and automatically fills
in a `PrivateKey` line for you — leave that alone. Replace the rest of the
text box so the whole thing reads:

```
[Interface]
PrivateKey = <leave whatever WireGuard already put here>
Address = 10.90.90.1/30
ListenPort = 51820

[Peer]
PublicKey = <you'll fill this in during step 3.5>
AllowedIPs = 10.90.90.2/32
Endpoint = <laptop's IPv4 address from step 3.2>:51820
PersistentKeepalive = 25
```

Name the tunnel something like `EqualSharesTunnel`. Don't click Activate
yet — you're missing the laptop's public key.

Click the tunnel name in the list; WireGuard shows its own **Public key**
for this tunnel near the top. Copy it somewhere safe (Notepad is fine) —
you'll paste it into the laptop's config in a moment.

### 3.4 — Create the tunnel on the laptop

Same steps, on the **laptop** this time: "Add Tunnel" → "Add empty tunnel...",
then fill in:

```
[Interface]
PrivateKey = <leave whatever WireGuard already put here>
Address = 10.90.90.2/30
ListenPort = 51820

[Peer]
PublicKey = <paste the workstation's public key you copied in step 3.3>
AllowedIPs = 10.90.90.1/32
Endpoint = <workstation's IPv4 address from step 3.2>:51820
PersistentKeepalive = 25
```

Click the tunnel name here too, copy the laptop's own **Public key**.

### 3.5 — Finish the workstation side

Go back to the workstation's WireGuard window, edit the tunnel you made in
3.3, and paste the laptop's public key (copied at the end of 3.4) into the
`PublicKey =` line under `[Peer]`. Save.

### 3.6 — Turn both tunnels on

On both machines, click the toggle switch next to the tunnel name to
activate it. It should turn green / say "Active."

### 3.7 — Test the connection

On the **workstation**, open PowerShell and type:

```powershell
ping 10.90.90.2
```

You should see replies (`Reply from 10.90.90.2: bytes=32...`), not
"Request timed out." If it times out: double-check both tunnels show
"Active," double-check the `Endpoint` lines have the correct IPv4 addresses
from step 3.2 (these can change if a router reassigns them — a common
gotcha), and make sure both machines are actually on the same Wi-Fi/network.

### 3.8 — Create the laptop's login credential (on the workstation)

With the broker already running (section 2.1's first window, or start it
now the same way), in a PowerShell window on the **workstation**:

```powershell
cd "A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09"
local_agent\worker_farm\Add-Phase1SecondaryWorkerCredential.ps1
```

This creates a file called `local_agent\worker_farm\.env.laptop_worker.generated`.
It contains a private password — do not open it and paste its contents
anywhere, including back to me. Just note that it exists.

### 3.9 — Copy that file to the laptop

Move `local_agent\worker_farm\.env.laptop_worker.generated` from the
workstation to the laptop yourself — a USB drive is the simplest way. On the
laptop, put it inside that same project folder (if the project isn't on the
laptop yet, copy the whole project folder over first), and rename it from
`.env.laptop_worker.generated` to just `.env`, inside the laptop's own
`local_agent\worker_farm\` folder.

### 3.10 — Start the relay (on the workstation, new window)

```powershell
local_agent\worker_farm\.venv\Scripts\python.exe local_agent\worker_farm\relay\tunnel_relay.py --bind-ip 10.90.90.1
```

Leave this window open the whole time the laptop is working — it's the
bridge that lets the laptop's traffic reach the workstation's Redis.

### 3.11 — Start the worker on the laptop

The laptop needs Python installed and this project's `local_agent\worker_farm\requirements.txt`
installed into its own private environment first (same idea as the
workstation's `.venv` — if you're not sure how, say so and this needs its
own separate walkthrough). Once that's done, from the laptop's PowerShell,
inside the project folder:

```powershell
python -m local_agent.worker_farm.worker --queues preprocess,research
```

If it connects and stays running without errors, the laptop is now a live
second worker.

### One more check before trusting this for real work

The rule that limits what the laptop's credential is allowed to touch is
new and hasn't been battle-tested. Before relying on it, try this sanity
check from the laptop: attempt to read something from the `distill` queue
(which belongs only to the workstation) and confirm you get an "access
denied"-style refusal, not actual data. If you're not sure how to do that
check yourself, ask for help with that specific step before trusting the
laptop with anything sensitive.

---

## Section 4 — Decide where backups go

This section is a decision to make, not really a command to run yet. Before
anything is backed up, answer these for yourself (pen and paper, or a text
file — just don't put it in this project's folder where it could get
committed):

1. **Where's the main backup going?** A dedicated external hard drive you
   plug in, or an online storage service you already pay for? Either is
   fine — pick one you actually have access to.
2. **Where's the second copy?** Backups should exist in two places. If your
   main copy is a drive at your desk, the second should be somewhere else —
   a different physical location, or a different online service.
3. **Who remembers the password?** The backup tool encrypts everything with
   a password. If you forget it, the backup is unrecoverable — that's by
   design, for privacy. Decide now: a password manager you already use, plus
   a written copy stored somewhere physical (like a safe), is a solid
   answer.
4. **When will you actually test restoring a file?** Pick an actual date —
   "someday" means it never happens, and an untested backup might not work
   when you need it.

Once you've actually decided all four of those, `docs/ENCRYPTED_ARCHIVAL_RUNBOOK.md`
in this project has the exact command sequence to run — it was intentionally
left waiting on these decisions rather than guessing at them for you.
