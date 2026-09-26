<#
Starts only the local Redis broker after explicit configuration. It does not
start a worker, submit a job, load a model, or open a network port beyond
127.0.0.1.

Engine: FARM_REDIS_ENGINE=desktop|wsl or -Engine. Default desktop (Docker
Desktop). wsl is Ubuntu-24.04 Docker CE — do not set that until Phase C.
#>
[CmdletBinding()]
param(
    [string]$Engine
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
. (Join-Path $here 'Resolve-FarmRedisEngine.ps1')
$resolvedEngine = Get-FarmRedisEngine -Engine $Engine
$env:FARM_REDIS_ENGINE = $resolvedEngine
$spec = Get-FarmDockerSpec -Engine $resolvedEngine -WindowsWorkDir $here
$envFile = Join-Path $here '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Missing local_agent/worker_farm/.env. Copy .env.example and replace every placeholder first.'
}
if ((Get-Content -LiteralPath $envFile -Raw) -match 'replace-with-') {
    throw '.env still contains example placeholders. Replace them before starting the broker.'
}
Write-Host ("Checking Redis engine ({0})..." -f $spec.Engine) -ForegroundColor Cyan
$probeArgs = @($spec.PrefixArgs) + @('version', '--format', '{{.Server.Version}}')
$probe = Start-Process -FilePath $spec.FilePath -ArgumentList $probeArgs -PassThru -WindowStyle Hidden
if (-not $probe.WaitForExit(15000)) {
    Stop-Process -Id $probe.Id -Force
    if ($spec.Engine -eq 'wsl') {
        throw 'Ubuntu-24.04 Docker CE did not answer within 15 seconds. Confirm wsl -d Ubuntu-24.04 -- docker info, then rerun.'
    }
    throw 'Docker Desktop did not answer its engine check within 15 seconds. Open Docker Desktop, wait for it to say Engine running, then rerun this script.'
}
if ($probe.ExitCode -ne 0) {
    if ($spec.Engine -eq 'wsl') {
        throw 'Ubuntu-24.04 Docker CE is not ready (FARM_REDIS_ENGINE=wsl). Confirm the distro and dockerd, then rerun.'
    }
    throw 'Docker Desktop is installed but its engine is not ready for this Windows account. Open Docker Desktop, wait for it to say Engine running, then rerun this script.'
}
Write-Host 'Staging secondary Redis ACL credentials for container restore...' -ForegroundColor Cyan
& (Join-Path $here 'Restore-Phase1SecondaryWorkerCredentials.ps1') -SyncOnly
$composeArgs = @('compose', '--env-file', '.env', 'up', '-d', 'redis')
$psArgs = @('compose', '--env-file', '.env', 'ps')
if ($spec.Engine -eq 'desktop') {
    Push-Location $here
    try {
        Write-Host 'Starting loopback-only Redis on 127.0.0.1:6379...' -ForegroundColor Cyan
        $code = Invoke-FarmDocker -Spec $spec -DockerArgs $composeArgs
        if ($code -ne 0) { throw 'Docker Compose could not start the Redis container; see the output above.' }
        Write-Host 'Checking Redis container status...' -ForegroundColor Cyan
        Invoke-FarmDocker -Spec $spec -DockerArgs $psArgs | Out-Null
    } finally {
        Pop-Location
    }
} else {
    Write-Host 'Starting loopback-only Redis on 127.0.0.1:6379 via Ubuntu-24.04 Docker CE...' -ForegroundColor Cyan
    $code = Invoke-FarmDocker -Spec $spec -DockerArgs $composeArgs
    if ($code -ne 0) { throw 'Docker Compose could not start the Redis container; see the output above.' }
    Write-Host 'Checking Redis container status...' -ForegroundColor Cyan
    Invoke-FarmDocker -Spec $spec -DockerArgs $psArgs | Out-Null
}
