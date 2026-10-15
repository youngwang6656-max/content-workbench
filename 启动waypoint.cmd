@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 goto fail
"%ComSpec%" /d /k scripts\start_windows.cmd
popd
exit /b
:fail
echo Cannot open the app folder. Extract the entire ZIP before starting.
pause
exit /b 1
