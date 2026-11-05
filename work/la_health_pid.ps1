$conn = Get-NetTCPConnection -LocalPort 8760 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $conn) { Write-Output "NO_LISTENER"; exit 0 }
$pid8760 = $conn.OwningProcess
Write-Output "LISTEN_PID=$pid8760"
Write-Output "LocalAddress=$($conn.LocalAddress)"
$p = Get-CimInstance Win32_Process -Filter "ProcessId=$pid8760" -ErrorAction SilentlyContinue
if ($p) {
  Write-Output "Name=$($p.Name)"
  Write-Output "CommandLine=$($p.CommandLine)"
  Write-Output "CreationDate=$($p.CreationDate)"
} else { Write-Output "PROCESS_MISSING" }
$proc = Get-Process -Id $pid8760 -ErrorAction SilentlyContinue
if ($proc) {
  Write-Output "StartTime=$($proc.StartTime)"
  Write-Output ("WS_MB={0}" -f [math]::Round($proc.WorkingSet64/1MB,1))
  Write-Output "CPU=$($proc.CPU)"
}
