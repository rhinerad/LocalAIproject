$ErrorActionPreference = 'Continue'
Write-Output '=== LISTENERS 8760 ==='
$conns = @(Get-NetTCPConnection -LocalPort 8760 -State Listen -ErrorAction SilentlyContinue)
$conns | ForEach-Object { Write-Output ("LocalAddress={0} LocalPort={1} OwningProcess={2} State={3}" -f $_.LocalAddress, $_.LocalPort, $_.OwningProcess, $_.State) }
if ($conns.Count -gt 0) {
  $pid8760 = $conns[0].OwningProcess
  Write-Output '=== PROCESS ==='
  $p = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $pid8760)
  if ($p) {
    Write-Output ("ProcessId={0}" -f $p.ProcessId)
    Write-Output ("Name={0}" -f $p.Name)
    Write-Output ("CommandLine={0}" -f $p.CommandLine)
    Write-Output ("CreationDate={0}" -f $p.CreationDate)
    Write-Output ("WorkingSetSize={0}" -f $p.WorkingSetSize)
  }
} else {
  Write-Output 'NO_LISTENER'
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -like '*local_agent*server.py*') } | ForEach-Object {
    Write-Output ("ORPHAN ProcessId={0} Name={1} CreationDate={2} WS={3}" -f $_.ProcessId, $_.Name, $_.CreationDate, $_.WorkingSetSize)
    Write-Output ("ORPHAN CommandLine={0}" -f $_.CommandLine)
  }
}

Write-Output '=== STATUS ==='
$sw = [Diagnostics.Stopwatch]::StartNew()
try {
  $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:8760/api/status' -UseBasicParsing -TimeoutSec 25
  $sw.Stop()
  Write-Output ("HTTP_CODE={0}" -f [int]$resp.StatusCode)
  Write-Output ("ELAPSED_MS={0}" -f $sw.ElapsedMilliseconds)
  Write-Output $resp.Content
} catch {
  $sw.Stop()
  Write-Output ("HTTP_ERROR={0}" -f $_.Exception.Message)
  Write-Output ("ELAPSED_MS={0}" -f $sw.ElapsedMilliseconds)
  if ($_.Exception.InnerException) { Write-Output ("INNER={0}" -f $_.Exception.InnerException.Message) }
}

Write-Output '=== COMFY 8188 ==='
try {
  $c = Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue
  if ($c) { Write-Output 'COMFY_UP' } else { Write-Output 'COMFY_DOWN' }
} catch { Write-Output 'COMFY_CHECK_ERR' }

Write-Output '=== NVIDIA ==='
try {
  & nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits 2>$null
} catch { Write-Output 'NVIDIA_NA' }

Write-Output '=== OLLAMA PS ==='
try {
  $o = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/ps' -UseBasicParsing -TimeoutSec 5
  Write-Output $o.Content
} catch { Write-Output 'OLLAMA_PS_FAIL' }
