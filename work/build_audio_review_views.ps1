param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'

$manifestPath = Join-Path $ProjectRoot 'outputs\equal_shares\audio_pass_manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Audio manifest not found: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$reviewRoot = Join-Path $ProjectRoot "outputs\equal_shares\audio_review_views\review_$stamp"
$earDir = Join-Path $reviewRoot '01_NEEDS_EAR_REVIEW'
$mechanicalDir = Join-Path $reviewRoot '02_MECHANICAL_PASS_STILL_NEEDS_LISTENING'
$acceptedDir = Join-Path $reviewRoot '03_FULLY_ACCEPTED'

foreach ($dir in @($reviewRoot, $earDir, $mechanicalDir, $acceptedDir)) {
    New-Item -ItemType Directory -Path $dir | Out-Null
}

$shell = New-Object -ComObject WScript.Shell
$rows = [System.Collections.Generic.List[object]]::new()

foreach ($property in $manifest.clips.PSObject.Properties) {
    $clipId = $property.Name
    $clip = $property.Value
    $attempts = @($clip.attempts)
    $latest = $attempts | Where-Object { [int]$_.attempt -eq [int]$clip.latest_attempt } | Select-Object -Last 1
    if (-not $latest) {
        $latest = $attempts | Select-Object -Last 1
    }
    if (-not $latest) {
        continue
    }

    $target = [string]$latest.candidate_full_wav
    $status = [string]$clip.status
    $destination = switch ($status) {
        'needs_ear_review' { $earDir }
        'auto_pass_pending_continuity_review' { $mechanicalDir }
        'accepted' { $acceptedDir }
        default { $earDir }
    }

    $exists = Test-Path -LiteralPath $target
    if ($exists) {
        $shortcutName = '{0}--{1}.lnk' -f $clipId, ([IO.Path]::GetFileNameWithoutExtension($target))
        $shortcutPath = Join-Path $destination $shortcutName
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $target
        $shortcut.WorkingDirectory = [IO.Path]::GetDirectoryName($target)
        $shortcut.Description = "Equal Shares $clipId - $status"
        $shortcut.Save()
    }

    $rows.Add([pscustomobject]@{
        clip_id = $clipId
        status = $status
        latest_attempt = [int]$latest.attempt
        audio_file = $target
        exists = $exists
        validation_reasons = (@($latest.validation_reasons) -join ' | ')
    })
}

$indexPath = Join-Path $reviewRoot 'review_index.csv'
$rows | Sort-Object clip_id | Export-Csv -LiteralPath $indexPath -NoTypeInformation -Encoding UTF8

$counts = $rows | Group-Object status | Sort-Object Name
$summaryLines = [System.Collections.Generic.List[string]]::new()
$summaryLines.Add('EQUAL SHARES - STAGE 1 AUDIO REVIEW')
$summaryLines.Add('')
$summaryLines.Add('Shortcuts point to the preserved original WAV files. No audio was copied, moved, deleted, or accepted by this view builder.')
$summaryLines.Add('')
foreach ($count in $counts) {
    $summaryLines.Add(('{0}: {1}' -f $count.Name, $count.Count))
}
$summaryLines.Add('')
$summaryLines.Add('01_NEEDS_EAR_REVIEW: speech recognition was blank/unknown or another audio check requires listening.')
$summaryLines.Add('02_MECHANICAL_PASS_STILL_NEEDS_LISTENING: mechanical checks passed, but continuity and human listening are still required.')
$summaryLines.Add('03_FULLY_ACCEPTED: only tracks explicitly approved by review appear here.')
$summaryLines.Add('')
$summaryLines.Add('Open a shortcut to play the latest candidate for that clip. See review_index.csv for original paths and validator reasons.')
[IO.File]::WriteAllLines((Join-Path $reviewRoot 'READ_ME_FIRST.txt'), $summaryLines, [Text.UTF8Encoding]::new($false))

[pscustomobject]@{
    review_root = $reviewRoot
    needs_ear_review = @($rows | Where-Object status -eq 'needs_ear_review').Count
    mechanical_pass_pending_listening = @($rows | Where-Object status -eq 'auto_pass_pending_continuity_review').Count
    fully_accepted = @($rows | Where-Object status -eq 'accepted').Count
    missing_files = @($rows | Where-Object exists -eq $false).Count
    index = $indexPath
} | ConvertTo-Json -Compress
