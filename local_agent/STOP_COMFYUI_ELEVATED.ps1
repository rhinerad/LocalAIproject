# Fixed UAC helper for the local agent's emergency ComfyUI stop.
#
# It accepts no arguments, never touches Ollama/the agent/browser, and never
# deletes, moves, or edits prompts, uploads, sources, or rendered output.

$ErrorActionPreference = 'SilentlyContinue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OwnerPath = Join-Path $ProjectRoot 'batch_render_queue_owner.json'
$Targets = New-Object 'System.Collections.Generic.HashSet[int]'

# The actual listening backend is always a safe target.
foreach ($line in (netstat -ano -p TCP)) {
    if ($line -match '127\.0\.0\.1:8188\s+.*LISTENING\s+(\d+)\s*$') {
        [void]$Targets.Add([int]$matches[1])
    }
}

# Also catch a crashed/non-listening ComfyUI launcher, but only under a path
# containing a literal ComfyUI directory. No generic Python process is targeted.
Get-Process -Name 'python*' | ForEach-Object {
    if ($_.Path -like '*\ComfyUI\*') { [void]$Targets.Add([int]$_.Id) }
}

# The batch lock may name the ordinary Python runner. Trust it only when its
# declared purpose is this fixed batch renderer.
if (Test-Path -LiteralPath $OwnerPath) {
    try {
        $owner = Get-Content -LiteralPath $OwnerPath -Raw | ConvertFrom-Json
        if ($owner.purpose -like 'batch render*' -and [int]$owner.pid -gt 0 -and
            (Get-Process -Id ([int]$owner.pid) -ErrorAction SilentlyContinue)) {
            [void]$Targets.Add([int]$owner.pid)
        }
    } catch {}
}

# Tell a live backend to interrupt before force-stopping its process tree.
try {
    Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8188/interrupt' `
        -Method Post -ContentType 'application/json' -Body '{}' -TimeoutSec 4 | Out-Null
} catch {}

$Stopped = @()
foreach ($pid in $Targets) {
    & taskkill.exe /PID $pid /T /F | Out-Null
    if (-not (Get-Process -Id $pid -ErrorAction SilentlyContinue)) { $Stopped += $pid }
}

# A forced runner cannot run its own cleanup. This resets only a dead queue lock.
if (Test-Path -LiteralPath $OwnerPath) {
    try {
        $owner = Get-Content -LiteralPath $OwnerPath -Raw | ConvertFrom-Json
        if ([int]$owner.pid -gt 0 -and -not (Get-Process -Id ([int]$owner.pid) -ErrorAction SilentlyContinue)) {
            @{ pid = 0; released_at = (Get-Date).ToString('s'); purpose = 'elevated emergency ComfyUI stop' } |
                ConvertTo-Json | Set-Content -LiteralPath $OwnerPath -Encoding utf8
        }
    } catch {}
}

$Runtime = Join-Path $PSScriptRoot 'runtime'
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
@{ stopped_pids = @($Stopped); completed_at = (Get-Date).ToString('s'); preserved = 'prompts, uploads, sources, and renders unchanged' } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Runtime 'comfyui_stop_last.json') -Encoding utf8
