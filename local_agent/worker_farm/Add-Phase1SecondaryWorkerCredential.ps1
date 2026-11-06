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

Secrets never travel on a command line: the ACL SETUSER line is piped to
redis-cli on stdin inside the container and redis-cli authenticates from the
container's own REDIS_PASSWORD environment (REDISCLI_AUTH), so neither the
workstation password nor the new node password shows up in `docker exec`
arguments, the Windows process list, or `ps` inside the container.

Engine: FARM_REDIS_ENGINE=desktop|wsl or -Engine, same as the Restore script.
#>
[CmdletBinding()]
param(
    [string]$Username = 'laptop_worker',
    [string[]]$Queues = @('preprocess', 'research'),
    [string]$TunnelIp = '10.90.90.1',
    [string]$Engine,
    [switch]$LockdownProbe
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
. (Join-Path $here 'Lock-Phase1SecretFile.ps1')
. (Join-Path $here 'Resolve-FarmRedisEngine.ps1')
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
        Write-Output "PASS: Add-Phase1SecondaryWorkerCredential.ps1 wrote a temp .env.<user>.generated with SYSTEM+$($script:Phase1SecretAclOwner) (R,W), inheritance disabled"
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

$resolvedEngine = Get-FarmRedisEngine -Engine $Engine
$env:FARM_REDIS_ENGINE = $resolvedEngine
$spec = Get-FarmDockerSpec -Engine $resolvedEngine -WindowsWorkDir $here
$psResult = Invoke-FarmDocker -Spec $spec -DockerArgs @('ps', '--filter', "name=$containerName", '--format', '{{.Status}}') -PassThru
if ($psResult.ExitCode -ne 0 -or $psResult.Text -notmatch '(?m)^Up') {
    throw "Redis container '$containerName' is not running on engine '$($spec.Engine)'. Start it with START_PHASE1_BROKER.ps1 first."
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
# be enumerated. The secondary node shares the workstation's logical db 0
# (SELECT is denied below, so it cannot move elsewhere), which is why the
# command set -- not the key pattern -- is the isolation boundary. The private
# `distill` queue (historical exports) also lives on db 0 today; the queue-name
# guard above keeps a secondary credential off it, but the durable fix is to
# move `distill` to a Redis instance that is not reachable over the tunnel at
# all (tracked in the audit notes; not an ACL change).
$keyPatterns = @('~*')

# Command set: explicit category grants instead of +@all (audit 2026-11-02 #5).
# Celery/Kombu + redis-py need @read/@write data commands (lists, hashes,
# strings, sets, sorted sets for unacked_index, streams), pub/sub for the
# result backend and pidbox, Lua scripting (EVALSHA/SCRIPT LOAD), MULTI/EXEC,
# and @connection (PING/AUTH/CLIENT SETNAME/HELLO). Everything in @dangerous
# (KEYS, INFO, CLIENT KILL, MONITOR, SAVE/BGSAVE, SWAPDB, SORT, ...) plus the
# replication/module/admin verbs are denied explicitly, including the SLAVEOF
# alias that the old list missed. SELECT is denied so the user is pinned to
# the db named in its URL (db 0) and cannot browse other logical dbs.
# Live Celery verification against this narrower grant is still required
# before trusting it for anything beyond a test worker.
$aclGrant = @('+@read', '+@write', '+@list', '+@hash', '+@string', '+@set',
              '+@sortedset', '+@stream', '+@pubsub', '+@scripting',
              '+@transaction', '+@connection')
$aclDeny = @('-@dangerous', '-slaveof', '-replicaof', '-module', '-keys', '-select',
             '-flushall', '-flushdb', '-config', '-shutdown', '-acl', '-debug', '-cluster')
$aclLine = (@('ACL', 'SETUSER', $Username, 'on', ">$laptopPassword") + $keyPatterns +
            @('&*', 'nocommands') + $aclGrant + $aclDeny) -join ' '

# The ACL line (which carries the new password) goes to redis-cli on stdin;
# redis-cli authenticates from the container's REDIS_PASSWORD via REDISCLI_AUTH.
# No password appears in docker/wsl arguments. tr strips the CR that Windows
# PowerShell appends when piping into a native process.
$inContainer = "tr -d '\r' | REDISCLI_AUTH=`$REDIS_PASSWORD redis-cli --no-auth-warning"
$aclArgs = @('exec', '-i', $containerName, 'sh', '-c', $inContainer)

Write-Host "Applying ACL user '$Username' scoped to queues: $($Queues -join ', ')" -ForegroundColor Cyan
$aclResult = Invoke-FarmDocker -Spec $spec -DockerArgs $aclArgs -StdinLines @($aclLine) -PassThru
if ($aclResult.ExitCode -ne 0 -or $aclResult.Text -notmatch 'OK') {
    throw "ACL SETUSER did not report OK (password not printed). Output: $($aclResult.Text -replace [regex]::Escape($laptopPassword), '<redacted>')"
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
    "# Database 0, shared with the workstation: the ACL user is denied SELECT,"
    "# so redis-py must not need to switch db after AUTH (it only sends SELECT"
    "# for a non-zero db). Isolation comes from the scoped command set, not the"
    "# db index. Do not change /0 here without also lifting -select in the ACL."
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
