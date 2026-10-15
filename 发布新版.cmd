@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "scripts\bootstrap_windows.ps1" -PrepareOnly
if errorlevel 1 goto fail
.venv\Scripts\python.exe scripts\package.py
if errorlevel 1 goto fail
echo Source release and update manifest template are in the releases folder next to this app.
echo Nothing has been published to the internet.
pause
exit /b 0
:fail
echo Packaging failed. Keep the error above and ask your AI to check it.
pause
exit /b 1
