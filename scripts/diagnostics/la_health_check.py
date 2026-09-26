import subprocess
ps = r"""
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'local_agent[\\/]+server\.py' } |
  ForEach-Object { "PID=$($_.ProcessId)|WS=$([math]::Round($_.WorkingSetSize/1MB,1))MB|CMD=$($_.CommandLine)" }
Write-Output '---ALL_SERVER_PY---'
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'server\.py' -and $_.Name -match 'python' } |
  ForEach-Object { "PID=$($_.ProcessId)|CMD=$($_.CommandLine.Substring(0,[Math]::Min(220,$_.CommandLine.Length)))" }
"""
r = subprocess.run(["powershell","-NoProfile","-Command", ps], capture_output=True, text=True, errors="replace")
print(r.stdout)
print(r.stderr)
print("RC", r.returncode)
