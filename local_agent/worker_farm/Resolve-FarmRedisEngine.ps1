# Shared FARM_REDIS_ENGINE=desktop|wsl resolution for farm Redis launchers.
# Dot-source from START_PHASE1_BROKER.ps1 and Restore-Phase1SecondaryWorkerCredentials.ps1.
# Direct: powershell -File Resolve-FarmRedisEngine.ps1 -Probe  (no live Redis).
# Default is desktop (Docker Desktop). wsl is Ubuntu-24.04 Docker CE.
# Does not start, stop, or recreate containers.

$script:FarmWslDistro = 'Ubuntu-24.04'

function Get-FarmRedisEngine {
    param([string]$Engine)
    $raw = $Engine
    if ([string]::IsNullOrWhiteSpace($raw)) {
        $raw = $env:FARM_REDIS_ENGINE
    }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        $raw = 'desktop'
    }
    $raw = $raw.Trim().ToLowerInvariant()
    if ($raw -notin @('desktop', 'wsl')) {
        throw "FARM_REDIS_ENGINE must be 'desktop' or 'wsl' (got '$raw'). Default is desktop."
    }
    return $raw
}

function ConvertTo-FarmWslPath {
    param([Parameter(Mandatory)][string]$LiteralPath)
    $full = $LiteralPath
    if (Test-Path -LiteralPath $LiteralPath) {
        $full = (Resolve-Path -LiteralPath $LiteralPath).Path
    }
    $full = $full.TrimEnd('\')
    if ($full.StartsWith('\\')) {
        throw "UNC paths are not mapped into WSL for farm docker: $full"
    }
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert to a WSL path: $full"
    }
    $drive = $Matches[1].ToLowerInvariant()
    $rest = $Matches[2] -replace '\\', '/'
    return "/mnt/$drive/$rest"
}

function Initialize-FarmDesktopDockerPath {
    $dockerBin = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'
    if ((Test-Path -LiteralPath (Join-Path $dockerBin 'docker-credential-desktop.exe')) -and
        (($env:Path -split ';') -notcontains $dockerBin)) {
        $env:Path = "$dockerBin;$env:Path"
    }
}

function Get-FarmDockerSpec {
    param(
        [string]$Engine,
        [string]$WindowsWorkDir
    )
    $eng = Get-FarmRedisEngine -Engine $Engine
    if ($eng -eq 'desktop') {
        Initialize-FarmDesktopDockerPath
        $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
        $docker = if ($dockerCommand) { $dockerCommand.Source } else {
            'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
        }
        if (-not (Test-Path -LiteralPath $docker)) {
            throw 'Docker Desktop is not available. Install it, then rerun this script.'
        }
        return [pscustomobject]@{
            Engine     = 'desktop'
            FilePath   = $docker
            PrefixArgs = @()
            WorkDir    = $WindowsWorkDir
            WslDistro  = $null
        }
    }
    $wslCmd = Get-Command wsl.exe -ErrorAction SilentlyContinue
    $wslPath = if ($wslCmd) { $wslCmd.Source } else {
        Join-Path $env:SystemRoot 'System32\wsl.exe'
    }
    if (-not (Test-Path -LiteralPath $wslPath)) {
        throw 'wsl.exe is not available; cannot use FARM_REDIS_ENGINE=wsl.'
    }
    $prefix = @('-d', $script:FarmWslDistro)
    if ($WindowsWorkDir) {
        $prefix += @('--cd', (ConvertTo-FarmWslPath -LiteralPath $WindowsWorkDir))
    }
    $prefix += @('-e', '/usr/bin/docker')
    return [pscustomobject]@{
        Engine     = 'wsl'
        FilePath   = $wslPath
        PrefixArgs = $prefix
        WorkDir    = $WindowsWorkDir
        WslDistro  = $script:FarmWslDistro
    }
}

function Invoke-FarmDocker {
    param(
        [Parameter(Mandatory)]$Spec,
        [Parameter(Mandatory)][string[]]$DockerArgs,
        [switch]$PassThru
    )
    $all = @($Spec.PrefixArgs) + @($DockerArgs)
    $savedEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Spec.FilePath @all 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedEap
    }
    $text = @($output | ForEach-Object { "$_" })
    if ($PassThru) {
        return [pscustomobject]@{
            ExitCode = $code
            Output   = $text
            Text     = ($text -join "`n")
        }
    }
    foreach ($line in $text) { Write-Host $line }
    return $code
}

if ($MyInvocation.InvocationName -ne '.' -and ($args -contains '-Probe')) {
    $ErrorActionPreference = 'Stop'
    try {
        $saved = $env:FARM_REDIS_ENGINE
        try {
            Remove-Item Env:FARM_REDIS_ENGINE -ErrorAction SilentlyContinue
            $d = Get-FarmRedisEngine
            if ($d -ne 'desktop') { throw "unset env should default to desktop, got $d" }
            $env:FARM_REDIS_ENGINE = 'WSL'
            if ((Get-FarmRedisEngine) -ne 'wsl') { throw 'env WSL should normalize to wsl' }
            $env:FARM_REDIS_ENGINE = 'desktop-linux'
            try {
                Get-FarmRedisEngine | Out-Null
                throw 'expected invalid engine to throw'
            } catch {
                if ($_.Exception.Message -notmatch "desktop' or 'wsl") { throw }
            }
        } finally {
            if ($null -eq $saved) {
                Remove-Item Env:FARM_REDIS_ENGINE -ErrorAction SilentlyContinue
            } else {
                $env:FARM_REDIS_ENGINE = $saved
            }
        }
        $here = Split-Path -Parent $PSCommandPath
        $wslHere = ConvertTo-FarmWslPath -LiteralPath $here
        if ($wslHere -notmatch '^/mnt/[a-z]/') { throw "bad wsl path $wslHere" }
        $desk = Get-FarmDockerSpec -Engine 'desktop' -WindowsWorkDir $here
        if ($desk.Engine -ne 'desktop' -or $desk.PrefixArgs.Count -ne 0) {
            throw 'desktop spec should call docker.exe with no wsl prefix'
        }
        $wslSpec = Get-FarmDockerSpec -Engine 'wsl' -WindowsWorkDir $here
        if ($wslSpec.Engine -ne 'wsl') { throw 'wsl spec engine' }
        $joined = $wslSpec.PrefixArgs -join ' '
        if ($joined -notmatch 'Ubuntu-24.04') { throw 'wsl spec missing distro' }
        if ($joined -notmatch [regex]::Escape($wslHere)) { throw 'wsl spec missing --cd' }
        if ($joined -notmatch '/usr/bin/docker') { throw 'wsl spec missing docker binary' }
        Write-Host 'PASS: Resolve-FarmRedisEngine default=desktop wsl=Ubuntu-24.04'
        exit 0
    } catch {
        Write-Host ("FAIL: " + $_.Exception.Message)
        exit 1
    }
}
