$ErrorActionPreference = 'SilentlyContinue'

$ProjectRoot = 'A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09'
$Runtime = Join-Path $ProjectRoot 'outputs\equal_shares\runtime'
$Host.UI.RawUI.WindowTitle = 'Equal Shares - Local Agent Live Status'

while ($true) {
    Clear-Host
    Write-Host 'EQUAL SHARES - LOCAL AGENT LIVE STATUS' -ForegroundColor Cyan
    Write-Host ('Updated: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
    Write-Host ''

    $gatePath = Join-Path $Runtime 'human_decision_required.json'
    if (Test-Path -LiteralPath $gatePath) {
        $gate = Get-Content -LiteralPath $gatePath -Raw | ConvertFrom-Json
        Write-Host 'STATUS: WAITING FOR HUMAN LISTENING REVIEW' -ForegroundColor Yellow
        Write-Host ('Gate: ' + $gate.gate)
        Write-Host 'The local agent is intentionally paused; no duplicate renderer will start.'
    } else {
        Write-Host 'STATUS: AUTOMATION MAY PROCEED' -ForegroundColor Green
    }

    Write-Host ''
    Write-Host 'OWNER RECORDS' -ForegroundColor Cyan
    Get-ChildItem -LiteralPath $Runtime -Filter '*owner.json' | ForEach-Object {
        $owner = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
        '{0,-34} PID {1,-7} {2}' -f $_.Name, $owner.pid, $owner.purpose
    }

    Write-Host ''
    Write-Host 'GPU' -ForegroundColor Cyan
    $gpu = & nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,power.draw,memory.used --format=csv,noheader,nounits
    if ($gpu) {
        $parts = $gpu -split ','
        'Temperature: {0} C   Utilization: {1}%   Power: {2} W   VRAM: {3} MiB' -f $parts[0].Trim(), $parts[1].Trim(), $parts[2].Trim(), $parts[3].Trim()
    }

    Write-Host ''
    Write-Host 'LATEST OMNI PIPELINE ACTIVITY' -ForegroundColor Cyan
    Get-Content -LiteralPath (Join-Path $Runtime 'omni_pipeline_supervisor.log') -Tail 10

    Write-Host ''
    Write-Host 'Review files:' -ForegroundColor Yellow
    Write-Host (Join-Path $ProjectRoot 'outputs\equal_shares\audio\audio_pass_candidates\00A_a03_full.wav')
    Write-Host (Join-Path $ProjectRoot 'outputs\equal_shares\audio\audio_pass_candidates\00I_a03_full.wav')
    Write-Host ''
    Write-Host 'Refreshing every 10 seconds. Press Ctrl+C to close.' -ForegroundColor DarkGray
    Start-Sleep -Seconds 10
}
