@echo off
setlocal
set "COMFY_DESKTOP=A:\Users\rhine\AppData\Local\Programs\Comfy Desktop\Comfy Desktop.exe"
set "WORKFLOW=A:\Users\rhine\ComfyUI-Shared\models\loras\wan22I2vQUADKsampler12_v10\WAN2.2 QUAD KSAMPLER - WALKING FROM BEHIND ASS JIGGLES.json"
if not exist "%COMFY_DESKTOP%" (echo Comfy Desktop was not found: %COMFY_DESKTOP% & pause & exit /b 1)
if not exist "%WORKFLOW%" (echo Workflow was not found: %WORKFLOW% & pause & exit /b 1)
start "Comfy Desktop - WAN 2.2 I2V Quad LoRA" "%COMFY_DESKTOP%" "%WORKFLOW%"
