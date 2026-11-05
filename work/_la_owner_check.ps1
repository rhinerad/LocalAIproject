Get-ChildItem -Path . -Recurse -Depth 3 -Include '*owner*.json','*media_queue*','*render_owner*' -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Output ("=== " + $_.FullName)
  Get-Content $_.FullName -Raw
}
# also check common runtime paths under local_agent / work
$candidates = @(
  'work\image_render_owner.json',
  'local_agent\image_render_owner.json',
  'work\media_queue.json',
  'local_agent\media_queue.json',
  'local_agent\runtime\image_render_owner.json',
  'local_agent\runtime\media_queue.json'
)
foreach ($c in $candidates) {
  if (Test-Path $c) {
    Write-Output ("=== candidate " + $c)
    Get-Content $c -Raw
  }
}
