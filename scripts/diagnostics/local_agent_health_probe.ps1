$ErrorActionPreference = 'Continue'
Write-Output '===LISTEN8760==='
$listen8760 = Get-NetTCPConnection -LocalPort 8760 -State Listen -ErrorAction SilentlyContinue
if ($listen8760) {
  $listen8760 | Select-Object LocalAddress,LocalPort,OwningProcess | Format-List | Out-String | Write-Output
  $owning = $listen8760 | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($procId in $owning) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
      Write-Output ("PROC pid={0} name={1} start={2} ws_mb={3} path={4}" -f $procId, $proc.ProcessName, $proc.StartTime.ToString('s'), [math]::Round($proc.WorkingSet64/1MB,1), $proc.Path)
    }
  }
} else {
  Write-Output 'no_listen_8760'
}

Write-Output '===SERVERPY==='
$wmi = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'local_agent[\\/]server\.py') }
if ($wmi) {
  foreach ($row in $wmi) {
    Write-Output ("SERVERPY pid={0} name={1} cmd={2}" -f $row.ProcessId, $row.Name, $row.CommandLine)
  }
} else {
  Write-Output 'no_server_py'
}

Write-Output '===STATUS==='
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
  $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:8760/api/status' -TimeoutSec 25 -UseBasicParsing
  $sw.Stop()
  Write-Output ("status_ms={0} status_code={1}" -f $sw.ElapsedMilliseconds, [int]$resp.StatusCode)
  Write-Output $resp.Content
} catch {
  $sw.Stop()
  Write-Output ("status_ms={0} status_code=0" -f $sw.ElapsedMilliseconds)
  Write-Output ("status_error={0}" -f $_.Exception.Message)
}

Write-Output '===8188==='
$listen8188 = Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue
if ($listen8188) {
  $cpids = @($listen8188 | Select-Object -ExpandProperty OwningProcess -Unique)
  Write-Output ("listen8188=true comfy_pids={0}" -f ($cpids -join ','))
  try {
    $c = Invoke-WebRequest -Uri 'http://127.0.0.1:8188/' -TimeoutSec 5 -UseBasicParsing
    Write-Output ("comfy_http={0}" -f [int]$c.StatusCode)
  } catch {
    Write-Output ("comfy_http=0 err={0}" -f $_.Exception.Message)
  }
} else {
  Write-Output 'listen8188=false'
}

Write-Output '===GPU==='
try {
  $gpu = & nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits 2>$null
  Write-Output ("gpu={0}" -f ($gpu -join '; '))
} catch {
  Write-Output 'gpu=n/a'
}

Write-Output '===OLLAMA==='
try {
  $oll = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 3 -UseBasicParsing
  Write-Output $oll.Content
} catch {
  Write-Output 'ollama_down_or_empty'
}
