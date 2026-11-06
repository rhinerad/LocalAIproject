# Start the general local desktop agent. Equal Shares remains an opt-in project mode.
#
# Brings up TWO Ollama servers so the agent can move between them per turn:
#
#   127.0.0.1:11435   CPU-only   CUDA_VISIBLE_DEVICES=-1, OLLAMA_VULKAN=false,
#                                GGML_VK_VISIBLE_DEVICES=-1, 4 threads
#   127.0.0.1:11434   GPU        the default instance, big model
#
# router.py picks one before every reply: the GPU model while the card is idle,
# the CPU model the moment a render claims it. Two servers rather than one
# because a single instance cannot be CPU-locked and GPU-enabled at the same
# time, and "mostly on CPU" is not good enough when a render needs the VRAM.
#
# Thermal: the CPU instance is capped at four of sixteen logical processors,
# matching work/run_open_interpreter_handoff.py and the rule in CLAUDE.md.
# Windows exposes no usable package-temperature sensor here, so that cap is a
# safeguard, not a preference. Do not raise it.

param(
    # Baseline is deliberately the default. `flash_q8` is an opt-in candidate
    # for the guarded benchmark only; it must not become the daily setting
    # until comparable evidence shows it helps this exact workstation.
    [ValidateSet('baseline', 'flash_q8')]
    [string]$GpuKvCache = 'baseline',
    # Opt-in ~9 GB pull. Default startup never fetches the coder model.
    [switch]$EnsureCodingModel,
    # Opt-in CPU-only helper for context compaction and post-turn memory
    # extraction. It is never used as a chat model or placed on the GPU.
    [switch]$EnsureContextModel
)

$ErrorActionPreference = 'Stop'
$Ollama = 'A:\Users\rhine\AppData\Local\Programs\Ollama\ollama.exe'
$Log    = $PSScriptRoot
$AppUrl = 'http://127.0.0.1:8760'
$ExpectedAgentRevision = '2026-09-22i-gvd-video-pipeline-readiness'
$StartupCpuModel = if ($env:EQUAL_SHARES_CPU_CHAT_MODEL) {
    $env:EQUAL_SHARES_CPU_CHAT_MODEL
} else {
    # The agent's configured CPU fallback. It is pulled only if missing, and
    # only by this desktop launcher — never by a chat request.
    'huihui_ai/qwen3-abliterated:8b'
}
$StartupGpuModel = if ($env:EQUAL_SHARES_PRIMARY_REASONING_MODEL) {
    $env:EQUAL_SHARES_PRIMARY_REASONING_MODEL
} else {
    'huihui_ai/qwen3-abliterated:14b'
}
$StartupCodingModel = if ($env:EQUAL_SHARES_CODING_MODEL) {
    $env:EQUAL_SHARES_CODING_MODEL
} else {
    'huihui_ai/qwen2.5-coder-abliterate:14b'
}
$ContextCompactorModel = 'llama3.1:8b'

function Test-AgentReady {
    try {
        $response = Invoke-WebRequest "$AppUrl/api/status" -TimeoutSec 3 -UseBasicParsing
        if ($response.StatusCode -ne 200) { return $false }
        $status = $response.Content | ConvertFrom-Json
        return $status.app_revision -eq $ExpectedAgentRevision
    }
    catch {
        return $false
    }
}

function Test-PidAlive([int]$ProcId) {
    return [bool](Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
}

function Stop-StalePid([int]$ProcId) {
    Write-Host "  replacing stale local-agent instance (PID $ProcId) ..." -ForegroundColor Cyan
    try {
        Stop-Process -Id $ProcId -Force -ErrorAction Stop
        return $true
    } catch {
        Write-Host "  Windows refused to stop PID ${ProcId}: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    $taskkill = Join-Path $env:WINDIR 'System32\taskkill.exe'
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
    $null = & $taskkill /PID $ProcId /T /F 2>$null
        $ErrorActionPreference = $prevEap
    } catch {
        $ErrorActionPreference = $prevEap
    }
    if ($LASTEXITCODE -eq 0 -or -not (Test-PidAlive $ProcId)) {
        Write-Host "  taskkill released PID $ProcId" -ForegroundColor Green
        return $true
    }

    # Repeatable trap: a previous "Run as Administrator" launch left an
    # elevated python.exe on 8760. Unelevated Stop-Process/taskkill cannot
    # touch it. Ask for a one-shot elevated taskkill, then keep THIS
    # launcher unelevated so the replacement server is not admin (running
    # the whole launcher elevated would recreate the same orphan).
    Write-Host "  PID $ProcId looks elevated; requesting a one-time Administrator taskkill (UAC)." -ForegroundColor Yellow
    Write-Host "  The replacement server will still start unelevated." -ForegroundColor Yellow
    try {
        $elev = Start-Process -FilePath $taskkill -ArgumentList @('/PID', "$ProcId", '/T', '/F') -Verb RunAs -Wait -PassThru -WindowStyle Hidden
        if ($elev.ExitCode -eq 0 -or -not (Test-PidAlive $ProcId)) {
            Write-Host "  elevated taskkill released PID $ProcId" -ForegroundColor Green
            return $true
        }
        Write-Host "  elevated taskkill exit $($elev.ExitCode)" -ForegroundColor Yellow
    } catch {
        Write-Host "  elevated taskkill was declined or failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    if (Test-AgentReady) {
        Write-Host "  The existing local-agent instance is already the expected version; reusing it." -ForegroundColor Green
        return $true
    }
    Write-Host "  Port 8760 is still occupied by a process this launcher cannot stop." -ForegroundColor Yellow
    Write-Host "  If the UAC prompt was cancelled, close the old elevated agent window and retry." -ForegroundColor Yellow
    return $false
}

function Stop-StaleAgent {
    # Kill the background media watcher so it restarts with fresh code alongside
    # the new server process. Its PID is in media_queue\watcher_owner.json.
    $watcherJson = Join-Path $PSScriptRoot 'media_queue\watcher_owner.json'
    if (Test-Path $watcherJson) {
        try {
            $wPid = (Get-Content $watcherJson -Raw | ConvertFrom-Json).pid
            if ($wPid) {
                Stop-Process -Id ([int]$wPid) -Force -ErrorAction SilentlyContinue
                Write-Host "  stopped stale media watcher (PID $wPid)" -ForegroundColor Cyan
            }
        } catch {}
    }

    # The only target is a loopback listener on this application's fixed port.
    # This is intentionally a restart, never a render/ComfyUI operation.
    $lines = netstat -ano -p tcp | Select-String '127.0.0.1:8760\s+'
    $pids = @()
    foreach ($line in $lines) {
        $fields = ($line.ToString() -split '\s+') | Where-Object { $_ }
        if ($fields.Count -ge 5 -and $fields[-2] -eq 'LISTENING') {
            $pids += [int]$fields[-1]
        }
    }
    $pids = @($pids | Select-Object -Unique)
    $failed = $false
    foreach ($procId in $pids) {
        if (-not (Stop-StalePid $procId)) { $failed = $true }
    }
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 250
        if (-not (Test-NetConnection '127.0.0.1' -Port 8760 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
            return
        }
    }
    if ($failed) {
        throw 'The stale local-agent instance did not release port 8760 (elevated leftover; UAC taskkill failed or was declined).'
    }
    throw 'The stale local-agent instance did not release port 8760.'
}

function Test-Server([string]$HostPort) {
    # Ollama 0.32 hydrates its local model-list cache immediately after the
    # listener opens. On this workstation that first `/api/tags` response can
    # take a little over five seconds, even though the CPU-only server is fine.
    try { $null = Invoke-WebRequest "http://$HostPort/api/tags" -TimeoutSec 12 -UseBasicParsing; return $true }
    catch { return $false }
}

# Repeated double-clicks must open the existing app, not start another HTTP
# server. Do not return yet: a live web server with a dead CPU/GPU Ollama server
# is the exact "half started" state the launcher must repair.
$agentAlreadyReady = Test-AgentReady
if (-not $agentAlreadyReady -and
    (Test-NetConnection '127.0.0.1' -Port 8760 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    Stop-StaleAgent
}

if (-not (Test-Path $Ollama)) {
    Write-Host "Ollama not found at $Ollama" -ForegroundColor Red
    Write-Host "Install it once on a real connection, then re-run this." -ForegroundColor Yellow
    exit 1
}

function Start-Server([string]$HostPort, [string]$Name, [bool]$CpuOnly,
                      [string]$GpuKvCacheMode = 'baseline') {
    if (Test-Server $HostPort) {
        Write-Host "  $Name already serving on $HostPort" -ForegroundColor Green
        return $true
    }
    Write-Host "  starting $Name on $HostPort ..." -ForegroundColor Cyan
    $envs = @{
        'OLLAMA_HOST'              = $HostPort
        'OLLAMA_NUM_PARALLEL'      = '1'
        'OLLAMA_MAX_LOADED_MODELS' = '1'
        'OLLAMA_KEEP_ALIVE'        = if ($CpuOnly) { '30m' } else { '5m' }
    }
    if ($CpuOnly) {
        # CUDA_VISIBLE_DEVICES=-1 only skips CUDA on Ollama 0.32.15
        # (upstream ollama#16508). Vulkan still enumerates the RTX 5080
        # unless it is also disabled, which is how a "CPU" 11435 advertised
        # the card and chat fell through toward a GPU load on 11434.
        $envs['CUDA_VISIBLE_DEVICES'] = '-1'
        $envs['OLLAMA_VULKAN'] = 'false'
        $envs['GGML_VK_VISIBLE_DEVICES'] = '-1'
    }
    elseif ($GpuKvCacheMode -eq 'flash_q8') {
        # Server-level only. A request cannot change its cache format, so this
        # is explicit at launch and never leaks to the CPU-only Ollama server.
        $envs['OLLAMA_FLASH_ATTENTION'] = '1'
        $envs['OLLAMA_KV_CACHE_TYPE'] = 'q8_0'
    }

    # Child processes inherit these; set, launch, then restore so the two
    # servers do not contaminate each other's environment.
    $saved = @{}
    foreach ($k in $envs.Keys) {
        # A child process inherits the environment-provider values. Using the
        # persistent user setting here made the intended CPU server start with
        # Ollama's default GPU host instead.
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        Set-Item -Path "Env:$k" -Value $envs[$k]
    }
    Start-Process -FilePath $Ollama -ArgumentList 'serve' -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Log "ollama_$Name.log") `
        -RedirectStandardError  (Join-Path $Log "ollama_$Name.err.log")
    foreach ($k in $saved.Keys) {
        if ($null -eq $saved[$k]) { Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue }
        else { Set-Item -Path "Env:$k" -Value $saved[$k] }
    }

    # This only reads the loopback catalogue. It does not load a model or touch
    # the GPU; leave enough room for the first model-list cache hydration.
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 700
        if (Test-Server $HostPort) { Write-Host "  $Name up" -ForegroundColor Green; return $true }
    }
    Write-Host "  $Name did not start — see ollama_$Name.err.log" -ForegroundColor Yellow
    return $false
}

function Get-ServerModels([string]$HostPort) {
    try {
        $body = (Invoke-WebRequest "http://$HostPort/api/tags" -TimeoutSec 8 -UseBasicParsing).Content | ConvertFrom-Json
        return @($body.models | ForEach-Object { [string]$_.name })
    }
    catch { return @() }
}

function Ensure-CpuChatModel([string]$Model) {
    $have = Get-ServerModels '127.0.0.1:11435'
    if ($have -contains $Model) {
        Write-Host "  CPU chat model ready: $Model" -ForegroundColor Green
        return $true
    }
    Write-Host "  CPU chat model is missing: $Model" -ForegroundColor Yellow
    Write-Host '  Pulling the configured CPU model now (this can take a while on the first start) ...' -ForegroundColor Cyan
    $savedHost = [Environment]::GetEnvironmentVariable('OLLAMA_HOST', 'Process')
    $savedCuda = [Environment]::GetEnvironmentVariable('CUDA_VISIBLE_DEVICES', 'Process')
    try {
        Set-Item -Path Env:OLLAMA_HOST -Value '127.0.0.1:11435'
        Set-Item -Path Env:CUDA_VISIBLE_DEVICES -Value '-1'
        & $Ollama pull $Model
        if ($LASTEXITCODE -ne 0) { throw "ollama pull exited with code $LASTEXITCODE" }
    }
    catch {
        Write-Host "  Could not pull $Model : $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host '  Continuing with any compatible model already installed on the CPU server.' -ForegroundColor Yellow
        return $false
    }
    finally {
        if ($null -eq $savedHost) { Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue }
        else { Set-Item -Path Env:OLLAMA_HOST -Value $savedHost }
        if ($null -eq $savedCuda) { Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue }
        else { Set-Item -Path Env:CUDA_VISIBLE_DEVICES -Value $savedCuda }
    }
    $ready = (Get-ServerModels '127.0.0.1:11435') -contains $Model
    if ($ready) { Write-Host "  CPU chat model ready: $Model" -ForegroundColor Green }
    return $ready
}

function Ensure-GpuChatModel([string]$Model) {
    $have = Get-ServerModels '127.0.0.1:11434'
    if ($have -contains $Model) {
        Write-Host "  GPU chat model ready: $Model" -ForegroundColor Green
        return $true
    }
    Write-Host "  GPU chat model is missing: $Model" -ForegroundColor Yellow
    Write-Host '  Pulling the configured GPU model now (this can take a while on the first pull) ...' -ForegroundColor Cyan
    $savedHost = [Environment]::GetEnvironmentVariable('OLLAMA_HOST', 'Process')
    try {
        Set-Item -Path Env:OLLAMA_HOST -Value '127.0.0.1:11434'
        & $Ollama pull $Model
        if ($LASTEXITCODE -ne 0) { throw "ollama pull exited with code $LASTEXITCODE" }
    }
    catch {
        Write-Host "  Could not pull $Model : $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host '  GPU chat model unavailable - agent will route to CPU until it is installed.' -ForegroundColor Yellow
        return $false
    }
    finally {
        if ($null -eq $savedHost) { Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue }
        else { Set-Item -Path Env:OLLAMA_HOST -Value $savedHost }
    }
    $ready = (Get-ServerModels '127.0.0.1:11434') -contains $Model
    if ($ready) { Write-Host "  GPU chat model ready: $Model" -ForegroundColor Green }
    return $ready
}

Write-Host "`nOllama servers" -ForegroundColor White
$cpuOk = Start-Server '127.0.0.1:11435' 'cpu' $true
if ($GpuKvCache -eq 'flash_q8') {
    Write-Host '  GPU cache candidate: Flash Attention + q8_0 KV (explicit opt-in)' -ForegroundColor Yellow
}
$gpuOk = Start-Server '127.0.0.1:11434' 'gpu' $false $GpuKvCache
# Deliberately do not start the Qwen2.5-VL server here.  It is a sensory
# worker, not a chat model.  The media watcher starts it only after it has a
# queued media batch and has verified that no render owns the GPU, then releases
# it after the batch drains.

if (-not $cpuOk -and -not $gpuOk) {
    Write-Host "`nNeither server started. Nothing to talk to." -ForegroundColor Red
    exit 1
}
if (-not $gpuOk) {
    Write-Host "  GPU server unavailable — the agent will stay on CPU." -ForegroundColor Yellow
}
if ($cpuOk) {
    # This makes the desktop shortcut self-contained: the model the CPU route
    # is configured to use exists before the GUI is opened. A pre-existing
    # compatible model still keeps startup usable if an offline pull fails.
    $null = Ensure-CpuChatModel $StartupCpuModel
    if ($EnsureContextModel) {
        Write-Host '  Ensuring CPU context-compaction model (explicit flag; never GPU)' -ForegroundColor Cyan
        $null = Ensure-CpuChatModel $ContextCompactorModel
    }
}
if ($gpuOk) {
    # Same guarantee for the GPU tier. The 14B is pulled only if missing and only
    # by this launcher — never from a chat request. A failed pull is reported but
    # does not abort startup; the agent falls back to CPU until the model is available.
    $null = Ensure-GpuChatModel $StartupGpuModel
    $wantCoding = $EnsureCodingModel -or (
        $env:EQUAL_SHARES_ENSURE_CODING_MODEL -and
        $env:EQUAL_SHARES_ENSURE_CODING_MODEL -match '^(1|true|yes)$'
    )
    if ($wantCoding) {
        Write-Host '  Ensuring coding model (explicit flag/env; not a default pull)' -ForegroundColor Cyan
        $null = Ensure-GpuChatModel $StartupCodingModel
    }
}

if ($agentAlreadyReady) {
    Write-Host "`nLocal Agent is already running; model servers verified/repaired." -ForegroundColor Green
    Write-Host "Opening $AppUrl" -ForegroundColor White
    try {
        Start-Process $AppUrl
    }
    catch {
        Write-Host "The app is ready at $AppUrl" -ForegroundColor Yellow
    }
    exit 0
}

Write-Host "`nRouting check" -ForegroundColor White
python (Join-Path $PSScriptRoot 'router.py')

Write-Host "`nRefreshing knowledge from current project state" -ForegroundColor White
python (Join-Path $PSScriptRoot 'build_knowledge_pack.py')

Write-Host "`nStarting media queue watcher" -ForegroundColor White
Start-Process python -ArgumentList (Join-Path $PSScriptRoot 'media_watcher.py') `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $PSScriptRoot 'media_watcher.log') `
    -RedirectStandardError  (Join-Path $PSScriptRoot 'media_watcher.err.log')

Write-Host "`nStarting the app" -ForegroundColor White
python (Join-Path $PSScriptRoot 'server.py')
