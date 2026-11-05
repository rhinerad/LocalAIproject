$ErrorActionPreference = 'Continue'
Write-Output '=== PORT 8760 ==='
$listeners = Get-NetTCPConnection -LocalPort 8760 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 5
if (-not $listeners) {
  Write-Output 'NO_LISTENER'
} else {
  foreach ($conn in @($listeners)) {
    $procId = $conn.OwningProcess
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    Write-Output ("PID={0} Local={1}:{2} State={3}" -f $procId, $conn.LocalAddress, $conn.LocalPort, $conn.State)
    if ($p) {
      Write-Output ("PROC Name={0} Start={1} WS_MB={2:N1} Path={3}" -f $p.ProcessName, $p.StartTime.ToString('s'), ($p.WorkingSet64/1MB), $p.Path)
    }
  }
}
Write-Output '=== STATUS ==='
try {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8760/api/status' -UseBasicParsing -TimeoutSec 25
  $sw.Stop()
  Write-Output ("HTTP={0} ELAPSED_MS={1}" -f [int]$r.StatusCode, $sw.ElapsedMilliseconds)
  Write-Output $r.Content
} catch {
  Write-Output ("STATUS_ERROR: " + $_.Exception.Message)
}
Write-Output '=== PORT 8188 ==='
$c8188 = Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 3
if (-not $c8188) { Write-Output '8188_NO_LISTENER' } else {
  foreach ($conn in @($c8188)) {
    Write-Output ("8188 PID={0} Local={1}:{2}" -f $conn.OwningProcess, $conn.LocalAddress, $conn.LocalPort)
  }
}
Write-Output '=== NVIDIA ==='
try { & nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader } catch { Write-Output 'nvidia-smi unavailable' }
Write-Output '=== OLLAMA PS ==='
try {
  $o = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/ps' -UseBasicParsing -TimeoutSec 5
  Write-Output $o.Content
} catch { Write-Output ("OLLAMA_ERROR: " + $_.Exception.Message) }
