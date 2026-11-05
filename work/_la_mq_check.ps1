Write-Output 'PENDING'
Get-ChildItem 'local_agent\media_queue\pending' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }
Write-Output 'PROCESSING'
Get-ChildItem 'local_agent\media_queue\processing' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }
Write-Output ('pending_count=' + (@(Get-ChildItem 'local_agent\media_queue\pending' -ErrorAction SilentlyContinue).Count))
Write-Output ('processing_count=' + (@(Get-ChildItem 'local_agent\media_queue\processing' -ErrorAction SilentlyContinue).Count))
Write-Output ('failed_count=' + (@(Get-ChildItem 'local_agent\media_queue\failed' -ErrorAction SilentlyContinue).Count))
try {
  $p = Get-Process -Id 34476 -ErrorAction Stop
  Write-Output ('watcher_alive pid=' + $p.Id + ' name=' + $p.ProcessName + ' start=' + $p.StartTime.ToString('s'))
} catch {
  Write-Output 'watcher_dead'
}
# image render owner common locations
foreach ($c in @('work\image_render_owner.json','local_agent\image_render_owner.json','local_agent\runtime\image_render_owner.json')) {
  if (Test-Path $c) { Write-Output ('IRO ' + $c); Get-Content $c -Raw }
}
