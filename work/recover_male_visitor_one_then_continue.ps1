$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
$Python = 'A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe'
$Log = Join-Path $Project 'outputs\equal_shares\runtime\omni_recovery_supervisor.log'

Set-Location -LiteralPath $Project
"[$(Get-Date -Format o)] Starting Male Visitor One version-2 VOX recovery" |
    Add-Content -LiteralPath $Log -Encoding UTF8

& $Python '.\work\render_vox_references.py' `
    --only 'VOX_MALE_VISITOR_ONE_REF' `
    --prompt-dir '.\outputs\equal_shares\prompts_vox_omni_v2' `
    --prompt-profile 'vox_master_continuous_v2'
if ($LASTEXITCODE -ne 0) {
    "[$(Get-Date -Format o)] Male Visitor One recovery ended with code $LASTEXITCODE" |
        Add-Content -LiteralPath $Log -Encoding UTF8
    exit $LASTEXITCODE
}

"[$(Get-Date -Format o)] Missing VOX recovery passed; resuming Omni coordinator" |
    Add-Content -LiteralPath $Log -Encoding UTF8
& $Python '.\work\continue_omni_voice_lock_pipeline.py'
exit $LASTEXITCODE
