$ErrorActionPreference = 'Continue'
Write-Output '=== PORT 8760 ==='
$listen = @(Get-NetTCPConnection -LocalPort 8760 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 5)
if ($listen.Count -gt 0) {
  $listen | Select-Object LocalAddress,LocalPort,OwningProcess,State | Format-List | Out-String | Write-Output
} else {
  Write-Output 'NO_LISTENER'
}
Write-Output '=== PROCESS ==='
$pids = @($listen | ForEach-Object { $_.OwningProcess } | Select-Object -Unique)
foreach ($procId in $pids) {
  Get-CimInstance Win32_Process -Filter ("ProcessId=" + $procId) | Select-Object ProcessId,Name,CommandLine,CreationDate,WorkingSetSize | Format-List | Out-String | Write-Output
}
Write-Output '=== SERVER.PY MATCH ==='
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match 'local_agent.+server\.py' } | Select-Object ProcessId,Name,CommandLine,CreationDate,WorkingSetSize | Format-List | Out-String | Write-Output

Write-Output '=== STATUS ==='
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
  $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:8760/api/status' -UseBasicParsing -TimeoutSec 25
  $sw.Stop()
  Write-Output ('HTTP_CODE=' + [int]$resp.StatusCode)
  Write-Output ('ELAPSED_MS=' + $sw.ElapsedMilliseconds)
  Write-Output $resp.Content
} catch {
  $sw.Stop()
  Write-Output ('HTTP_ERROR=' + $_.Exception.Message)
  Write-Output ('ELAPSED_MS=' + $sw.ElapsedMilliseconds)
}

Write-Output '=== COMFY 8188 ==='
$c8188 = @(Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 3)
if ($c8188.Count -gt 0) {
  $c8188 | Select-Object LocalAddress,LocalPort,OwningProcess,State | Format-List | Out-String | Write-Output
} else {
  Write-Output 'COMFY_DOWN'
}

Write-Output '=== NVIDIA ==='
try {
  & nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader 2>$null
} catch {
  Write-Output 'nvidia-smi unavailable'
}

Write-Output '=== OLLAMA PS ==='
try {
  $ops = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/ps' -UseBasicParsing -TimeoutSec 5
  Write-Output $ops.Content
} catch {
  Write-Output ('OLLAMA_ERROR=' + $_.Exception.Message)
}
