<#
Creates a portable source-and-documentation snapshot for cloud backup.

It intentionally excludes private runtime state, credentials, model weights,
media/generated outputs, virtual environments, and logs. This is not an
evidence/media archival workflow. It does not modify the project source tree.
#>
[CmdletBinding()]
param(
    [string]$DestinationDirectory = (Join-Path $PSScriptRoot '..\artifacts\backups')
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$destination = [IO.Path]::GetFullPath($DestinationDirectory)
New-Item -ItemType Directory -Force -Path $destination | Out-Null

$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$archive = Join-Path $destination "LocalAgent_SourceBackup_$stamp.zip"

$excludedDirectoryNames = @(
    '.git', '.venv', '__pycache__', 'runtime', 'uploads', 'feedback_store',
    'exemplar_staging', 'models', 'outputs', 'artifacts', 'logs', 'archive',
    '.codex-remote-attachments', 'ble_runtime', 'vendor_sideband',
    'vendor_sideband_desktop', 'vendor_tools', 'knowledge', 'node_modules'
)
$excludedFileNames = @('.env', 'paired_identities.json')
$excludedExtensions = @('.log', '.mp4', '.mov', '.mkv', '.avi', '.wav', '.mp3', '.flac', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.safetensors', '.gguf', '.ckpt', '.pt', '.pth', '.zip', '.sqlite', '.db')

function Test-ExcludedPath([IO.FileInfo]$File) {
    if ($excludedFileNames -contains $File.Name) { return $true }
    if ($excludedExtensions -contains $File.Extension.ToLowerInvariant()) { return $true }
    $relative = $File.FullName.Substring($projectRoot.Length).TrimStart('\','/')
    foreach ($part in ($relative -split '[\\/]')) {
        if ($excludedDirectoryNames -contains $part) { return $true }
    }
    return $false
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$files = Get-ChildItem -LiteralPath $projectRoot -File -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { -not (Test-ExcludedPath $_) } |
    Sort-Object FullName
if (-not $files) { throw 'No eligible source/documentation files were found.' }

$zip = [IO.Compression.ZipFile]::Open($archive, [IO.Compression.ZipArchiveMode]::Create)
$included = 0
$skippedUnreadable = 0
try {
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($projectRoot.Length).TrimStart('\','/') -replace '\\','/'
        try {
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $zip, $file.FullName, "COMFYUI_STORY_HANDOFF_2026-08-09/$relative",
                [IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
            $included++
        } catch {
            if ($_.Exception.InnerException -is [UnauthorizedAccessException]) {
                $skippedUnreadable++
                continue
            }
            throw
        }
    }
    $manifest = @(
        'Backup scope: source code and documentation only.',
        "Created UTC: $((Get-Date).ToUniversalTime().ToString('o'))",
        "Included files: $included",
        "Unreadable files skipped: $skippedUnreadable",
        'Excluded: credentials, runtime state, uploads, logs, virtual environments, model weights, media/generated outputs, artifacts, archive evidence.',
        'This snapshot must not be treated as a complete media/evidence archive.'
    ) -join [Environment]::NewLine
    $entry = $zip.CreateEntry('BACKUP_SCOPE.txt', [IO.Compression.CompressionLevel]::Optimal)
    $writer = [IO.StreamWriter]::new($entry.Open())
    try { $writer.WriteLine($manifest) } finally { $writer.Dispose() }
} finally {
    $zip.Dispose()
}

$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
[pscustomobject]@{
    archive = $archive
    sha256 = $hash
    files = $included
    skipped_unreadable = $skippedUnreadable
    bytes = (Get-Item -LiteralPath $archive).Length
    scope = 'source-and-documentation-only'
}
