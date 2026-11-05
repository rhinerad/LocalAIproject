param(
    [int]$IntervalSeconds = 60,
    [switch]$Once
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HandoffRoot = Join-Path $ProjectRoot 'COMFYUI_STORY_HANDOFF_2026-08-09'
$StatusPath = Join-Path $HandoffRoot 'SYNC_STATUS.json'
$LogPath = Join-Path $HandoffRoot 'SYNC_LOG.txt'
$PidPath = Join-Path $HandoffRoot 'SYNC_WATCHER.pid'

if (-not $Once -and (Test-Path -LiteralPath $PidPath)) {
    $ExistingPid = 0
    [void][int]::TryParse((Get-Content -LiteralPath $PidPath -Raw).Trim(), [ref]$ExistingPid)
    if ($ExistingPid -gt 0 -and (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue)) {
        exit 0
    }
}

if (-not $Once) {
    Set-Content -LiteralPath $PidPath -Value $PID -Encoding ASCII
}

function Invoke-HandoffSync {
    New-Item -ItemType Directory -Path $HandoffRoot -Force | Out-Null

    $Pairs = @(
        @{ Source = (Join-Path $ProjectRoot 'outputs'); Destination = (Join-Path $HandoffRoot 'outputs') },
        @{ Source = (Join-Path $ProjectRoot 'work'); Destination = (Join-Path $HandoffRoot 'work') }
    )

    $Results = @()
    foreach ($Pair in $Pairs) {
        New-Item -ItemType Directory -Path $Pair.Destination -Force | Out-Null
        & robocopy $Pair.Source $Pair.Destination /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
        $Code = $LASTEXITCODE
        if ($Code -ge 8) {
            throw "Robocopy failed for $($Pair.Source) with exit code $Code"
        }
        $Results += [ordered]@{
            source = $Pair.Source
            destination = $Pair.Destination
            robocopy_exit_code = $Code
        }
    }

    $ManifestPath = Join-Path $ProjectRoot 'outputs\equal_shares\manifest.json'
    $ConfigPath = Join-Path $ProjectRoot 'outputs\equal_shares\story_config.json'
    $Configured = $null
    $Valid = $null
    $FirstUnresolved = $null
    if ((Test-Path -LiteralPath $ManifestPath) -and (Test-Path -LiteralPath $ConfigPath)) {
        $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
        $Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
        $Configured = @($Config.clips).Count
        $ValidIds = @(
            $Manifest.clips.PSObject.Properties |
                Where-Object { $_.Value.status -eq 'valid' } |
                ForEach-Object { $_.Name }
        )
        $Valid = $ValidIds.Count
        $FirstUnresolved = @(
            $Config.clips |
                Where-Object { $ValidIds -notcontains $_.id } |
                Select-Object -First 1 -ExpandProperty id
        )[0]
    }

    $Status = [ordered]@{
        last_successful_sync = (Get-Date).ToString('o')
        project_root = $ProjectRoot
        handoff_root = $HandoffRoot
        configured_clips = $Configured
        valid_clips = $Valid
        unresolved_clips = if ($null -ne $Configured -and $null -ne $Valid) { $Configured - $Valid } else { $null }
        first_unresolved_clip = $FirstUnresolved
        interval_seconds = $IntervalSeconds
        copied_roots = $Results
    }
    $Status | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StatusPath -Encoding UTF8
    "[$(Get-Date -Format o)] Sync successful: $Valid/$Configured valid; next=$FirstUnresolved" |
        Add-Content -LiteralPath $LogPath -Encoding UTF8
}

do {
    try {
        Invoke-HandoffSync
    }
    catch {
        "[$(Get-Date -Format o)] Sync failed: $($_.Exception.Message)" |
            Add-Content -LiteralPath $LogPath -Encoding UTF8
    }

    if ($Once) {
        break
    }
    Start-Sleep -Seconds ([Math]::Max(15, $IntervalSeconds))
} while ($true)
