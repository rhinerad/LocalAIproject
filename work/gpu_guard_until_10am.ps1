$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root 'local_agent/runtime/gpu_guard_until_10am.log'
$cutoff = (Get-Date).Date.AddHours(10)
"$(Get-Date -Format o) guard started; cutoff=$cutoff" | Add-Content -LiteralPath $log
$allow = @(
  'A:\Users\rhine\AppData\Local\Programs\Ollama\ollama.exe',
  'A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe',
  'A:\Users\rhine\ComfyUI-Installs\Rockernow\standalone-env\python.exe',
  'A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\local_agent\'
)
while ((Get-Date) -lt $cutoff) {
  $rows = nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>$null
  foreach ($row in $rows) {
    $pid = 0
    if (-not [int]::TryParse(($row -replace '[^0-9]',''), [ref]$pid) -or $pid -le 0) { continue }
    $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if (-not $p) { "$(Get-Date -Format o) pid=$pid inaccessible; left untouched" | Add-Content -LiteralPath $log; continue }
    $path = [string]$p.Path
    $ok = $false
    foreach ($a in $allow) { if ($path -and $path.StartsWith($a, [StringComparison]::OrdinalIgnoreCase)) { $ok = $true; break } }
    if ($ok) { continue }
    try { Stop-Process -Id $pid -Force -ErrorAction Stop; "$(Get-Date -Format o) stopped non-agent GPU pid=$pid path=$path" | Add-Content -LiteralPath $log }
    catch { "$(Get-Date -Format o) refused pid=$pid path=$path error=$($_.Exception.Message)" | Add-Content -LiteralPath $log }
  }
  Start-Sleep -Seconds 30
}
"$(Get-Date -Format o) guard ended" | Add-Content -LiteralPath $log
