@echo off
setlocal EnableExtensions DisableDelayedExpansion
powershell.exe -NoProfile -File "%~dp0start-collector.ps1"
exit /b %errorlevel%
