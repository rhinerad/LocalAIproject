# Refuse-by-default USB/ADB companion APK install.
# Does not install unless runtime/lxmf/adb_trusted_devices.json has an
# unrevoked row matching serial + ro.build.fingerprint + this file's SHA-256.
# Default is off. No scheduled task. Does not live-install from CI.
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Apk,
    [Parameter(Mandatory = $true)]
    [string] $Serial,
    [switch] $DryRun,
    [string] $Ledger,
    [string] $Adb
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyScript = Join-Path $here 'adb_install.py'
$argv = @($pyScript, $Apk, '--serial', $Serial)
if ($DryRun) { $argv += '--dry-run' }
if ($Ledger) { $argv += @('--ledger', $Ledger) }
if ($Adb) { $argv += @('--adb', $Adb) }
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error 'python not on PATH; cannot run adb_install.py'
    exit 1
}
& $python.Source @argv
exit $LASTEXITCODE
