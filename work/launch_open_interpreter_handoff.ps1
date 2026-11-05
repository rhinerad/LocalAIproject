$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Handoff = Join-Path $Root 'COMFYUI_STORY_HANDOFF_2026-08-09'
$LogPath = Join-Path $Handoff 'OPEN_INTERPRETER_SESSION.log'
$OwnerPath = Join-Path $Handoff 'outputs\equal_shares\runtime\local_agent_owner.json'
$Python = 'A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = Join-Path $PSScriptRoot 'run_open_interpreter_handoff.py'

Set-Location -LiteralPath $Handoff
@{
    pid = $PID
    claimed_at = (Get-Date -Format o)
    purpose = 'Equal Shares offline Open Interpreter soundtrack-first agent'
} | ConvertTo-Json | Set-Content -LiteralPath $OwnerPath -Encoding UTF8

try {
    "[$(Get-Date -Format o)] Starting Open Interpreter with qwen2.5-coder:14b forced to CPU (launcher PID $PID)" |
        Add-Content -LiteralPath $LogPath -Encoding UTF8
    & $Python $Runner 2>&1 | Tee-Object -FilePath $LogPath -Append
    $AgentExitCode = $LASTEXITCODE
    "[$(Get-Date -Format o)] Open Interpreter exited with code $AgentExitCode" |
        Add-Content -LiteralPath $LogPath -Encoding UTF8
}
finally {
    @{
        pid = 0
        released_at = (Get-Date -Format o)
        purpose = 'released'
    } | ConvertTo-Json | Set-Content -LiteralPath $OwnerPath -Encoding UTF8
}
