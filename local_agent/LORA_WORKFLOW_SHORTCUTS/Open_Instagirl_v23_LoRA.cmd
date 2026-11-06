@echo off
setlocal
set "COMFY_DESKTOP=A:\Users\rhine\AppData\Local\Programs\Comfy Desktop\Comfy Desktop.exe"
set "WORKFLOW=A:\Users\rhine\ComfyUI-Shared\models\loras\Instagirlv2.3_workflow.json"
if not exist "%COMFY_DESKTOP%" (echo Comfy Desktop was not found: %COMFY_DESKTOP% & pause & exit /b 1)
if not exist "%WORKFLOW%" (echo Workflow was not found: %WORKFLOW% & pause & exit /b 1)
start "Comfy Desktop - Instagirl v2.3 LoRA" "%COMFY_DESKTOP%" "%WORKFLOW%"
