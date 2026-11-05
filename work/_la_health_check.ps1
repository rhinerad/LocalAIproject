$ErrorActionPreference = 'Continue'
$result = [ordered]@{}
try {
  $c = Get-NetTCPConnection -LocalPort 8760 -State Listen -ErrorAction Stop | Select-Object -First 1
  if ($null -ne $c) {
    $p = Get-Process -Id $c.OwningProcess -ErrorAction Stop
    $result.port = 8760
    $result.pid = $p.Id
    $result.proc = $p.ProcessName
    $result.start = $p.StartTime.ToString('s')
    $result.ws_mb = [math]::Round($p.WorkingSet64 / 1MB, 1)
  } else {
    $result.port = 'none'
  }
} catch {
  $result.port_err = $_.Exception.Message
}
try {
  $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8760/api/status' -TimeoutSec 25 -UseBasicParsing
  $result.status_code = $r.StatusCode
  $result.status_body = $r.Content
} catch {
  $result.status_err = $_.Exception.Message
}
try {
  $c8 = Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  $result.comfy_8188 = if ($null -ne $c8) { 'up' } else { 'down' }
} catch {
  $result.comfy_8188 = 'down'
}
try {
  $n = nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits 2>$null
  if ($n) {
    $parts = $n -split ','
    $result.nvidia_mem_mib = [int]$parts[0].Trim()
    $result.nvidia_util = [int]$parts[1].Trim()
  }
} catch {}
try {
  $ops = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 5 -UseBasicParsing
  $result.ollama_ps = $ops.Content
} catch {
  $result.ollama_ps = '[]'
}
$result | ConvertTo-Json -Compress -Depth 8
