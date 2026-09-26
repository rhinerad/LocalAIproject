# gvd_watcher_keepalive.ps1 — restart gvd_watcher.py if dead while batch incomplete
$ErrorActionPreference = 'Continue'
$root = 'A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09'
$py = 'A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe'
$logDir = Join-Path $root 'local_agent\runtime\logs'
$progress = Join-Path $root 'local_agent\runtime\gvd_backrooms_batch\progress.json'
$pidFile = Join-Path $logDir 'gvd_watcher_launcher.pid'
$outLog = Join-Path $logDir 'watcher_launch.out.log'
$errLog = Join-Path $logDir 'watcher_launch.err.log'
$keepLog = Join-Path $logDir 'keepalive.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Keep([string]$m) {
  $line = "$(Get-Date -Format o) $m"
  Add-Content -Path $keepLog -Value $line
}

function Watcher-Alive {
  $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue |
    Where-Object { $_.CommandLine -match 'gvd_watcher\.py' }
  return [bool]$procs
}

function Batch-Complete {
  if (-not (Test-Path $progress)) { return $false }
  try {
    $d = Get-Content $progress -Raw | ConvertFrom-Json
    $done = 0
    foreach ($p in $d.clips.PSObject.Properties) {
      if ($p.Value.status -eq 'done') { $done++ }
    }
    return ($done -ge 102)
  } catch { return $false }
}

Write-Keep "keepalive_start pid=$PID"
while ($true) {
  if (Batch-Complete) {
    Write-Keep "batch_complete exiting"
    break
  }
  if (-not (Watcher-Alive)) {
    Write-Keep "watcher_dead relaunching"
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:GVD_F5_TTS = '0'
    # rotate oversized logs lightly
    if ((Test-Path $outLog) -and ((Get-Item $outLog).Length -gt 50MB)) {
      Move-Item $outLog ($outLog + '.' + (Get-Date -Format 'yyyyMMddHHmmss')) -Force
    }
    $p = Start-Process -FilePath $py -ArgumentList @('-u','gvd_watcher.py') -WorkingDirectory $root `
      -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru -WindowStyle Hidden
    Set-Content $pidFile -Value $p.Id
    Write-Keep "relaunched pid=$($p.Id)"
  }
  Start-Sleep -Seconds 300
}