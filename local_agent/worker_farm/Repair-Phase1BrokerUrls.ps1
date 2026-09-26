<#
Repairs only the encoded Redis URLs in an existing local .env. It preserves the
existing Redis password and AES key, so encrypted artifacts remain recoverable.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
$envFile = Join-Path $here '.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Missing .env.' }
$values = [ordered]@{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { $values[$matches[1]] = $matches[2] }
}
if ([string]::IsNullOrWhiteSpace($values['REDIS_PASSWORD'])) {
    throw 'Missing REDIS_PASSWORD; refusing to invent or rotate a credential.'
}
$encodedPassword = [Uri]::EscapeDataString($values['REDIS_PASSWORD'])
$url = "redis://:$encodedPassword@127.0.0.1:6379/0"
$values['FARM_BROKER_URL'] = $url
$values['FARM_RESULT_BACKEND'] = $url
$order = @('REDIS_PASSWORD','FARM_BROKER_URL','FARM_RESULT_BACKEND','FARM_ROOT','FARM_ENCRYPTION_KEY_B64','FARM_QUEUES','FARM_CONCURRENCY')
$content = foreach ($name in $order) { if ($values.Contains($name)) { "$name=$($values[$name])" } }
[System.IO.File]::WriteAllLines($envFile, [string[]]$content, [System.Text.UTF8Encoding]::new($false))
Write-Output 'Repaired broker URL encoding while preserving existing local credentials.'
