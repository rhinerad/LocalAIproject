# DIAGNOSE_GPU_ROUTING.ps1 — why is the local agent on CPU, not the GPU 14B?
# Safe: only OBSERVES port 8188 / VRAM / the Ollama servers and runs router.py.
# It never starts, stops, or touches a render or ComfyUI. Read the verdict at the end.

$ErrorActionPreference = 'Continue'
$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "`n=== Local agent GPU-routing diagnosis ===`n" -ForegroundColor White

function Test-Port([int]$p) {
  return (Test-NetConnection '127.0.0.1' -Port $p -InformationLevel Quiet -WarningAction SilentlyContinue)
}
function Get-Tags([string]$hp) {
  try { return @(((Invoke-WebRequest "http://$hp/api/tags" -TimeoutSec 5 -UseBasicParsing).Content | ConvertFrom-Json).models | ForEach-Object { $_.name }) }
  catch { return $null }
}

# 1) ComfyUI on 8188?
$comfy = Test-Port 8188
Write-Host ("1. ComfyUI on port 8188 : {0}" -f ($(if($comfy){'LISTENING  <-- this alone forces the agent to CPU'}else{'closed'}))) -ForegroundColor $(if($comfy){'Yellow'}else{'Green'})

# 2) VRAM / GPU processes
Write-Host "`n2. GPU VRAM (nvidia-smi):" -ForegroundColor White
$smi = 'C:\Windows\System32\nvidia-smi.exe'
if (Test-Path $smi) {
  & $smi --query-gpu=memory.used,memory.total --format=csv,noheader
  Write-Host "   compute processes:" -ForegroundColor Gray
  & $smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader
} else { Write-Host "   nvidia-smi not on PATH — router treats unknown GPU as BUSY (=> CPU)." -ForegroundColor Yellow }

# 3) Ollama servers
Write-Host "`n3. Ollama servers:" -ForegroundColor White
$gpuUp = Test-Port 11434; $cpuUp = Test-Port 11435
$gpuTags = if ($gpuUp) { Get-Tags '127.0.0.1:11434' } else { $null }
$cpuTags = if ($cpuUp) { Get-Tags '127.0.0.1:11435' } else { $null }
Write-Host ("   GPU server 11434 : {0}" -f ($(if($gpuUp){'UP'}else{'DOWN  <-- no GPU server to route to'}))) -ForegroundColor $(if($gpuUp){'Green'}else{'Red'})
if ($gpuUp) { Write-Host ("     models: {0}" -f ($(if($gpuTags){$gpuTags -join ', '}else{'(none / unreadable)'}))) -ForegroundColor Gray }
Write-Host ("   CPU server 11435 : {0}" -f ($(if($cpuUp){'UP'}else{'DOWN'}))) -ForegroundColor $(if($cpuUp){'Green'}else{'Yellow'})
if ($cpuUp) { Write-Host ("     models: {0}" -f ($(if($cpuTags){$cpuTags -join ', '}else{'(none)'}))) -ForegroundColor Gray }
$has14b = $gpuTags -and ($gpuTags | Where-Object { $_ -like 'huihui_ai/qwen3-abliterated:14b*' })

# 4) The router's own decision
Write-Host "`n4. router.py decision:" -ForegroundColor White
try { python (Join-Path $AgentDir 'router.py') } catch { Write-Host "   could not run router.py: $($_.Exception.Message)" -ForegroundColor Red }

# Verdict
Write-Host "`n=== VERDICT ===" -ForegroundColor White
if ($comfy) {
  Write-Host "ComfyUI is on port 8188. The agent is CORRECTLY staying on CPU to protect the render." -ForegroundColor Yellow
  Write-Host "FIX: fully close ComfyUI (confirm nothing on 8188), then chat again — it should use the GPU 14B." -ForegroundColor Cyan
} elseif (-not $gpuUp) {
  Write-Host "The GPU Ollama server (11434) is DOWN — nothing for the agent to route to on GPU." -ForegroundColor Red
  Write-Host "FIX: re-run START_LOCAL_AGENT_GUI.ps1 — it restarts the GPU server and ensures the 14B." -ForegroundColor Cyan
} elseif (-not $has14b) {
  Write-Host "GPU server is up but the 14B is NOT in its catalogue." -ForegroundColor Red
  Write-Host "FIX: re-run START_LOCAL_AGENT_GUI.ps1 (it pulls the 14B), or manually:" -ForegroundColor Cyan
  Write-Host "     `$env:OLLAMA_HOST='127.0.0.1:11434'; ollama pull huihui_ai/qwen3-abliterated:14b" -ForegroundColor Cyan
} else {
  Write-Host "8188 clear, GPU server up, 14B present. If router still says CPU:" -ForegroundColor Yellow
  Write-Host " - check the VRAM line above: a leftover process holding >~2.5 GB reads as BUSY. Close it." -ForegroundColor Cyan
  Write-Host " - otherwise re-run START_LOCAL_AGENT_GUI.ps1 to clear any half-started state, then re-run this script." -ForegroundColor Cyan
}
Write-Host ""
