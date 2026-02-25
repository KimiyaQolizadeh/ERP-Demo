@echo off
setlocal
powershell.exe -ExecutionPolicy Bypass -File "%~dp0run-dev.ps1" %*
endlocal
