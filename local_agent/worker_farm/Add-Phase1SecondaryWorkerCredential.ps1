<#
WARNING: Do not re-run this script to recover from a Redis restart.
Every run mints a NEW password. That breaks the Mac's stored mac_worker
credential (and any other node still using .env.<username>.generated).
Keep .env.mac_worker.generated on the workstation. Redis already restores
existing secondary users on every container start via
redis-with-acl-restore.sh, including docker restart. Reapply without
rotating: Restore-Phase1SecondaryWorkerCredentials.ps1.

Applies a scoped Redis ACL user for one additional trusted worker node (the
laptop, by default) and writes that node's own .env fragment locally. It
never prints the generated password, matching Initialize-Phase1Secrets.ps1.

This does not start a tunnel, does not touch compose.yaml, and does not copy
anything to another machine -- the operator moves the generated file
themselves, over a channel they control. See
docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md for the full plan
this script is one step of.

Use this script only when creating a NEW secondary user, or when you are
intentionally rotating one and will copy the new generated file to that node.
--aclfile is still not used, so requirepass / default-user handling stays
unchanged.
#>
[CmdletBinding()]
param(
    [string]$Username = 'laptop_worker',
    [string[]]$Queues = @('preprocess', 'research'),
    [string]$TunnelIp = '10.90.90.1',
    [switch]$LockdownProbe
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
. (Join-Path $here 'Lock-Phase1SecretFile.ps1')
$envFile = Join-Path $here '.env'
$containerName = 'local-agent-phase1-redis'

if ($LockdownProbe) {
    $probeDir = Join-Path ([System.IO.Path]::GetTempPath()) ('phase1-secondary-probe-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $probeDir | Out-Null
    try {
        $outFile = Join-Path $probeDir '.env.probe_worker.generated'
        $fragment = @(
            "# LockdownProbe dummy fragment -- not a live credential"
            "FARM_BROKER_URL=redis://probe_worker:probe-password-not-used@127.0.0.1:6379/0"
            "FARM_RESULT_BACKEND=redis://probe_worker:probe-password-not-used@127.0.0.1:6379/0"
            "FARM_QUEUES=preprocess,research"
            "FARM_CONCURRENCY=1"
        ) -join [Environment]::NewLine
        [System.IO.File]::WriteAllText($outFile, $fragment + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
        Lock-Phase1SecretFile -LiteralPath $outFile
        if (-not (Test-Phase1SecretFileAcl -LiteralPath $outFile)) {
            throw "LockdownProbe ACL mismatch for $outFile"
        }
        Write-Output 'PASS: Add-Phase1SecondaryWorkerCredential.ps1 wrote a temp .env.<user>.generated with SYSTEM+rhine (R,W), inheritance disabled'
    }
    finally {
        Remove-Item -LiteralPath $probeDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    return
}

if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Missing local_agent/worker_farm/.env. Run Initialize-Phase1Secrets.ps1 and start the broker first.'
}
$envRaw = Get-Content -LiteralPath $envFile -Raw
if ($envRaw -match 'replace-with-') {
    throw '.env still contains example placeholders.'
}
if ($Username -eq 'default' -or [string]::IsNullOrWhiteSpace($Username)) {
    throw "Refusing to touch the 'default' user or an empty username."
}
foreach ($q in $Queues) {
    if ($q -notmatch '^[a-zA-Z0-9_-]+$') { throw "Queue name '$q' has characters outside [a-zA-Z0-9_-]." }
}
if ($Queues -contains 'distill') {
    throw "Refusing to grant a secondary node access to the 'distill' queue -- that carries private historical-export jobs."
}

$envValues = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { $envValues[$matches[1].Trim()] = $matches[2].Trim() }
}
$redisPassword = $envValues['REDIS_PASSWORD']
if ([string]::IsNullOrWhiteSpace($redisPassword)) {
    throw 'REDIS_PASSWORD not found in .env.'
}

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$docker = if ($dockerCommand) { $dockerCommand.Source } else { 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' }
if (-not (Test-Path -LiteralPath $docker)) {
    throw 'Docker Desktop is not available.'
}
$status = & $docker ps --filter "name=$containerName" --format '{{.Status}}' 2>$null
if (-not $status -or $status -notmatch '^Up') {
    throw "Redis container '$containerName' is not running. Start it with START_PHASE1_BROKER.ps1 first."
}

function New-RandomBase64([int]$Bytes, [switch]$UrlSafe) {
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buffer)
    $rng.Dispose()
    $encoded = [Convert]::ToBase64String($buffer)
    if ($UrlSafe) {
        return $encoded.TrimEnd('=').Replace('+', '-').Replace('/', '_')
    }
    return $encoded
}

$laptopPassword = New-RandomBase64 36 -UrlSafe

# Key patterns: ~* (all keys) because Celery/Kombu generates unpredictable
# internal keys (UUID pidbox, reply queues, unacked mutex, etc.) that cannot
# be enumerated. The real distill-queue isolation is the credential itself
# (separate password, separate DB) and the queue-name guard above -- key
# patterns are redundant when the node has its own dedicated DB.
# Verified against a real Celery 5.6.3 + redis-py worker session 2026-09-01.
$keyPatterns = @('~*')

# Command set: grant all commands then block only truly destructive admin ops.
# Narrower category-based grants caused whack-a-mole failures against Celery
# 5.6.3 + redis-py (EVALSHA, SCRIPT LOAD, MULTI/EXEC, BLPOP, pidbox keys, etc.)
# The real isolation is the scoped credential + dedicated DB; blocking individual
# Celery internals adds friction without security value.
# Verified against a real Celery 5.6.3 + redis-py worker session 2026-09-01.
$aclArgs = @('exec', $containerName, 'redis-cli', '-a', $redisPassword, '--no-auth-warning',
             'ACL', 'SETUSER', $Username, 'on', ">$laptopPassword") + $keyPatterns + @(
             '&*', 'nocommands', '+@all',
             '-flushall', '-flushdb', '-config', '-shutdown', '-acl', '-debug', '-cluster', '-replicaof')

Write-Host "Applying ACL user '$Username' scoped to queues: $($Queues -join ', ')" -ForegroundColor Cyan
$result = & $docker @aclArgs 2>&1
if ($LASTEXITCODE -ne 0 -or $result -notmatch 'OK') {
    throw "ACL SETUSER did not report OK. Output: $result"
}
Write-Host "ACL user created. Password stored in the generated file; redis-with-acl-restore.sh reapplies it on container start." -ForegroundColor Cyan

$outFile = Join-Path $here ".env.$Username.generated"
$fragment = @(
    "# Generated $(Get-Date -Format o) by Add-Phase1SecondaryWorkerCredential.ps1"
    "# Copy this file to the $Username node's local_agent/worker_farm/.env yourself,"
    "# over a channel you control. Keep this workstation copy; redis-with-acl-restore.sh"
    "# reads it (via runtime/redis-acl) after every Redis container start."
    "# Requires celery_app.py's loopback check to also accept the tunnel address"
    "# before this URL will actually be accepted -- see the Phase 1.5 plan doc."
    "# Database 1, not 0: _is_authenticated_loopback_redis_url already allows"
    "# either, and keeping the secondary node on its own logical db is a free"
    "# extra separation from the workstation's own db 0 traffic."
    "FARM_BROKER_URL=redis://$Username`:$laptopPassword@$TunnelIp`:6379/0"
    "FARM_RESULT_BACKEND=redis://$Username`:$laptopPassword@$TunnelIp`:6379/0"
    "FARM_QUEUES=$($Queues -join ',')"
    'FARM_CONCURRENCY=1'
) -join [Environment]::NewLine
[System.IO.File]::WriteAllText($outFile, $fragment + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
Lock-Phase1SecretFile -LiteralPath $outFile
if (-not (Test-Phase1SecretFileAcl -LiteralPath $outFile)) {
    throw "Wrote $outFile but ACL lockdown failed; file is present -- inspect icacls before copying it."
}

Write-Host "Wrote $outFile (not printed here; open the file locally if you need to inspect it)." -ForegroundColor Cyan
& (Join-Path $here 'Restore-Phase1SecondaryWorkerCredentials.ps1') -SyncOnly
Write-Host "Next: verify with an ACL DENY probe against a non-owned key before trusting this for anything beyond a test worker." -ForegroundColor Cyan
