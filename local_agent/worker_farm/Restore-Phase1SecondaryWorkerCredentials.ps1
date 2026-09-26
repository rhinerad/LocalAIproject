<#
Reapplies already-generated secondary Redis ACL users without rotating their
passwords. Add-Phase1SecondaryWorkerCredential.ps1 generates a NEW password
every run; this script is the restore path.

Default: copy each local_agent/worker_farm/.env.<username>.generated file into
runtime/redis-acl (the bind mount the Redis wrapper reads) and ACL SETUSER
against the running container using the current grant set. -SyncOnly only
stages the files, which is what START_PHASE1_BROKER.ps1 needs before compose
up so a later `docker restart` still has credentials to restore.

Never prints passwords. Never touches the default user.

Engine: FARM_REDIS_ENGINE=desktop|wsl or -Engine. Default desktop. SyncOnly
does not talk to Docker; the engine is used only for docker exec ACL SETUSER.
#>
[CmdletBinding()]
param(
    [switch]$SyncOnly,
    [string]$Engine
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
. (Join-Path $here 'Lock-Phase1SecretFile.ps1')
. (Join-Path $here 'Resolve-FarmRedisEngine.ps1')
$resolvedEngine = Get-FarmRedisEngine -Engine $Engine
$env:FARM_REDIS_ENGINE = $resolvedEngine
$envFile = Join-Path $here '.env'
$aclDir = Join-Path $here 'runtime\redis-acl'
$containerName = 'local-agent-phase1-redis'

if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Missing local_agent/worker_farm/.env. Run Initialize-Phase1Secrets.ps1 and start the broker first.'
}
$envRaw = Get-Content -LiteralPath $envFile -Raw
if ($envRaw -match 'replace-with-') {
    throw '.env still contains example placeholders.'
}

New-Item -ItemType Directory -Path $aclDir -Force | Out-Null

$generated = @(Get-ChildItem -LiteralPath $here -Force -File -Filter '.env.*.generated' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^\.env\.[A-Za-z0-9_-]+\.generated$' })

if ($generated.Count -eq 0) {
    Write-Host 'No .env.<username>.generated files found; nothing to restore.' -ForegroundColor Yellow
    return
}

$staged = @()
foreach ($file in $generated) {
    $dest = Join-Path $aclDir $file.Name
    Copy-Item -LiteralPath $file.FullName -Destination $dest -Force
    Lock-Phase1SecretFile -LiteralPath $dest
    if (-not (Test-Phase1SecretFileAcl -LiteralPath $dest)) {
        throw "Staged $dest but ACL lockdown failed; inspect icacls before starting Redis."
    }
    $staged += $file.Name
}
Write-Host ("Staged {0} secondary credential file(s) into runtime/redis-acl." -f $staged.Count) -ForegroundColor Cyan

if ($SyncOnly) {
    return
}

$envValues = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { $envValues[$matches[1].Trim()] = $matches[2].Trim() }
}
$redisPassword = $envValues['REDIS_PASSWORD']
if ([string]::IsNullOrWhiteSpace($redisPassword)) {
    throw 'REDIS_PASSWORD not found in .env.'
}

$spec = Get-FarmDockerSpec -Engine $resolvedEngine -WindowsWorkDir $here
$psResult = Invoke-FarmDocker -Spec $spec -DockerArgs @('ps', '--filter', "name=$containerName", '--format', '{{.Status}}') -PassThru
if ($psResult.ExitCode -ne 0 -or $psResult.Text -notmatch '(?m)^Up') {
    throw "Redis container '$containerName' is not running on engine '$($spec.Engine)'. Start it with START_PHASE1_BROKER.ps1 first."
}

foreach ($file in $generated) {
    $values = @{}
    Get-Content -LiteralPath $file.FullName | ForEach-Object {
        if ($_ -match '^([^#=]+)=(.*)$') { $values[$matches[1].Trim()] = $matches[2].Trim() }
    }
    $url = $values['FARM_BROKER_URL']
    if ($url -notmatch '^redis://([^:/]+):([^@]+)@') {
        throw "Could not parse FARM_BROKER_URL in $($file.Name); refusing to invent a password."
    }
    $username = $matches[1]
    $userPassword = $matches[2]
    if ($username -eq 'default' -or [string]::IsNullOrWhiteSpace($username)) {
        throw "Refusing to touch the 'default' user (file $($file.Name))."
    }
    if ($username -notmatch '^[A-Za-z0-9_-]+$') {
        throw "Refusing unsafe username parsed from $($file.Name)."
    }
    if ([string]::IsNullOrWhiteSpace($userPassword)) {
        throw "Empty password in $($file.Name); refusing to generate a replacement."
    }

    $aclArgs = @('exec', $containerName, 'redis-cli', '-a', $redisPassword, '--no-auth-warning',
                 'ACL', 'SETUSER', $username, 'on', ">$userPassword",
                 '~*', '&*', 'nocommands', '+@all',
                 '-flushall', '-flushdb', '-config', '-shutdown', '-acl', '-debug', '-cluster', '-replicaof')
    Write-Host "Reapplying ACL user '$username' from $($file.Name) (password not printed)." -ForegroundColor Cyan
    $aclResult = Invoke-FarmDocker -Spec $spec -DockerArgs $aclArgs -PassThru
    if ($aclResult.ExitCode -ne 0 -or $aclResult.Text -notmatch 'OK') {
        throw "ACL SETUSER did not report OK for '$username'."
    }
    Write-Host "ACL user '$username' restored." -ForegroundColor Cyan
}
