<#
Creates the local-only broker configuration once. Secrets are generated on this
machine, never printed, and the resulting .env is ignored by source control.
Use -Force and -AcknowledgeExistingArtifactsBecomeUnreadable only to rotate an
intentionally existing configuration after preserving or retiring its artifacts.
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$AcknowledgeExistingArtifactsBecomeUnreadable,
    [string]$EnvFile,
    [switch]$LockdownProbe
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
. (Join-Path $here 'Lock-Phase1SecretFile.ps1')

$probeDir = $null
if ($LockdownProbe) {
    if (-not [string]::IsNullOrWhiteSpace($EnvFile)) {
        throw '-LockdownProbe writes its own temp file; do not also pass -EnvFile.'
    }
    $probeDir = Join-Path ([System.IO.Path]::GetTempPath()) ('phase1-init-probe-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $probeDir | Out-Null
    $EnvFile = Join-Path $probeDir '.env'
}

if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $envFile = Join-Path $here '.env'
} else {
    $envFile = $EnvFile
}
if (Test-Path -LiteralPath $envFile) {
    if (-not $Force) {
        throw '.env already exists. Refusing to overwrite credentials.'
    }
    if (-not $AcknowledgeExistingArtifactsBecomeUnreadable) {
        throw 'Credential rotation would make existing AES-encrypted artifacts unreadable. Re-run only with -Force -AcknowledgeExistingArtifactsBecomeUnreadable after you have handled the old artifacts.'
    }
}

try {
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

$redisPassword = New-RandomBase64 36 -UrlSafe
$key = New-RandomBase64 32
$artifactRoot = Join-Path $env:LOCALAPPDATA 'EqualSharesLocalAgent\worker_farm'
$content = @(
    "REDIS_PASSWORD=$redisPassword"
    "FARM_BROKER_URL=redis://:$redisPassword@127.0.0.1:6379/0"
    "FARM_RESULT_BACKEND=redis://:$redisPassword@127.0.0.1:6379/0"
    "FARM_ROOT=$artifactRoot"
    "FARM_ENCRYPTION_KEY_B64=$key"
    'FARM_QUEUES=distill'
    'FARM_CONCURRENCY=1'
) -join [Environment]::NewLine

New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
[System.IO.File]::WriteAllText($envFile, $content + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
Lock-Phase1SecretFile -LiteralPath $envFile
if (-not (Test-Phase1SecretFileAcl -LiteralPath $envFile)) {
    throw "Created $envFile but ACL lockdown failed; file is present -- inspect icacls before using it."
}
if ($LockdownProbe) {
    Write-Output 'PASS: Initialize-Phase1Secrets.ps1 wrote a temp .env with SYSTEM+rhine (R,W), inheritance disabled'
    return
}
Write-Output "Created local ignored configuration at $envFile"
Write-Output "Encrypted artifacts will be stored at $artifactRoot"
}
finally {
    if ($probeDir) {
        Remove-Item -LiteralPath $probeDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
