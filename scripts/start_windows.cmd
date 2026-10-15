@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap_windows.ps1"
if errorlevel 1 goto fail
exit /b 0
:fail
echo Startup did not finish. Give this folder and the AI setup guide to your AI.
pause
exit /b 1
