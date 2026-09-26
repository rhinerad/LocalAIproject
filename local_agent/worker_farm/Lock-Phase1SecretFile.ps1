<#
Windows chmod-600 equivalent for farm secret files (CHANGELOG 2026-09-03aj).

Disables NTFS inheritance and grants only:
  NT AUTHORITY\SYSTEM:(R,W)
  DURANGAMINGPC\rhine:(R,W)

Administrators is intentionally not granted: that group still contains tiffa.

Dot-source this file to get Lock-Phase1SecretFile / Test-Phase1SecretFileAcl.
Run directly with -Probe to write a dummy file under $env:TEMP, lock it, assert
the ACL, and delete it. -Probe does not touch live .env files.

The worker_farm/ directory ACL is left alone on purpose: that folder is the
source tree (Python, tests, dashboard, logs). Tightening its default DACL
would break CodexSandboxUsers / other agents and anything else that creates
files there. Secret writers must lock each secret file after write instead.
#>
[CmdletBinding()]
param(
    [switch]$Probe,
    [string]$LiteralPath
)

$ErrorActionPreference = 'Stop'

$script:Phase1SecretAclSystem = 'NT AUTHORITY\SYSTEM'
$script:Phase1SecretAclOwner = 'DURANGAMINGPC\rhine'

function Get-Phase1SecretIcacls {
    return (Join-Path $env:SystemRoot 'System32\icacls.exe')
}

function Lock-Phase1SecretFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$LiteralPath
    )
    if (-not (Test-Path -LiteralPath $LiteralPath)) {
        throw "Lock-Phase1SecretFile: missing $LiteralPath"
    }
    $icacls = Get-Phase1SecretIcacls
    $inherit = & $icacls $LiteralPath /inheritance:r 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "icacls /inheritance:r failed for $LiteralPath : $inherit"
    }
    $grantSystem = & $icacls $LiteralPath /grant:r "$($script:Phase1SecretAclSystem):(R,W)" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "icacls grant SYSTEM failed for $LiteralPath : $grantSystem"
    }
    $grantOwner = & $icacls $LiteralPath /grant:r "$($script:Phase1SecretAclOwner):(R,W)" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "icacls grant $($script:Phase1SecretAclOwner) failed for $LiteralPath : $grantOwner"
    }
}

function Test-Phase1SecretFileAcl {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$LiteralPath
    )
    if (-not (Test-Path -LiteralPath $LiteralPath)) {
        return $false
    }
    $acl = Get-Acl -LiteralPath $LiteralPath
    if (-not $acl.AreAccessRulesProtected) {
        return $false
    }
    $ids = @(
        $acl.Access |
            ForEach-Object { $_.IdentityReference.Value.ToLowerInvariant() } |
            Sort-Object -Unique
    )
    $expected = @(
        $script:Phase1SecretAclSystem.ToLowerInvariant(),
        $script:Phase1SecretAclOwner.ToLowerInvariant()
    ) | Sort-Object
    if ($ids.Count -ne $expected.Count) {
        return $false
    }
    foreach ($name in $expected) {
        if ($ids -notcontains $name) {
            return $false
        }
    }
    foreach ($ace in $acl.Access) {
        $rights = [string]$ace.FileSystemRights
        if ($rights -match 'FullControl') {
            return $false
        }
        if ($rights -notmatch 'Read' -or $rights -notmatch 'Write') {
            return $false
        }
        if ($ace.IsInherited) {
            return $false
        }
    }
    return $true
}

function Invoke-Phase1SecretAclProbe {
    $probeDir = Join-Path ([System.IO.Path]::GetTempPath()) ('phase1-acl-probe-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $probeDir | Out-Null
    try {
        $icacls = Get-Phase1SecretIcacls
        $null = & $icacls $probeDir /grant 'BUILTIN\Users:(OI)(CI)(R)' 2>&1
        $probeFile = Join-Path $probeDir '.env'
        [System.IO.File]::WriteAllText($probeFile, "PROBE=1$([Environment]::NewLine)", [System.Text.UTF8Encoding]::new($false))
        $before = Get-Acl -LiteralPath $probeFile
        $beforeIds = @($before.Access | ForEach-Object { $_.IdentityReference.Value })
        $inheritedOpen = $before.AreAccessRulesProtected -eq $false -or
            ($beforeIds | Where-Object { $_ -match 'Users|tiffa|CodexSandboxUsers' })
        if (-not $inheritedOpen) {
            throw "Probe setup failed: dummy file did not inherit a wide DACL (aces: $($beforeIds -join ', '))"
        }
        Lock-Phase1SecretFile -LiteralPath $probeFile
        if (-not (Test-Phase1SecretFileAcl -LiteralPath $probeFile)) {
            $after = (icacls $probeFile 2>&1 | Out-String)
            throw "Probe ACL mismatch after lock:`n$after"
        }
        Write-Output 'PASS: probe file ACL is SYSTEM+rhine (R,W), inheritance disabled'
    }
    finally {
        Remove-Item -LiteralPath $probeDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$script:Phase1SecretAclDotSourced = (
    $MyInvocation.InvocationName -eq '.' -or
    $MyInvocation.Line -match '^\s*\.\s+'
)

if (-not $script:Phase1SecretAclDotSourced) {
    if ($Probe) {
        Invoke-Phase1SecretAclProbe
        exit 0
    }
    if ([string]::IsNullOrWhiteSpace($LiteralPath)) {
        throw 'Lock-Phase1SecretFile.ps1: pass -LiteralPath <file> or -Probe'
    }
    Lock-Phase1SecretFile -LiteralPath $LiteralPath
    if (-not (Test-Phase1SecretFileAcl -LiteralPath $LiteralPath)) {
        throw "ACL verify failed after lock: $LiteralPath"
    }
}
