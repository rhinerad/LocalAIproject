$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Project 'outputs\equal_shares\runtime'
$Owner = Join-Path $Runtime 'claude_watch_owner.json'
$Log = Join-Path $Runtime 'claude_watch.log'
$PromptPath = Join-Path $Project 'CLAUDE_CODE_OMNI_WATCH_PROMPT.md'
$Claude = 'A:\Users\rhine\AppData\Roaming\npm\claude.cmd'

Set-Location -LiteralPath $Project
@{
    pid = $PID
    claimed_at = (Get-Date -Format o)
    purpose = 'Claude Code Equal Shares continuity watcher'
} | ConvertTo-Json | Set-Content -LiteralPath $Owner -Encoding UTF8

try {
    $Prompt = Get-Content -LiteralPath $PromptPath -Raw -Encoding UTF8
    "[$(Get-Date -Format o)] Claude Code continuity watcher starting" |
        Add-Content -LiteralPath $Log -Encoding UTF8
    & $Claude -p --permission-mode acceptEdits --effort high --setting-sources user,project,local $Prompt 2>&1 |
        Tee-Object -FilePath $Log -Append
    "[$(Get-Date -Format o)] Claude Code exited with code $LASTEXITCODE" |
        Add-Content -LiteralPath $Log -Encoding UTF8
}
finally {
    @{
        pid = 0
        released_at = (Get-Date -Format o)
        purpose = 'released'
    } | ConvertTo-Json | Set-Content -LiteralPath $Owner -Encoding UTF8
}

