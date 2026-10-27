@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Optional: set the absolute path below if Tera Term uses a nonstandard folder.
set "TT_MACRO="
if defined TT_MACRO goto run
if exist "%ProgramFiles%\teraterm5\ttpmacro.exe" set "TT_MACRO=%ProgramFiles%\teraterm5\ttpmacro.exe"
if defined TT_MACRO goto run
if exist "%ProgramFiles%\teraterm\ttpmacro.exe" set "TT_MACRO=%ProgramFiles%\teraterm\ttpmacro.exe"
if defined TT_MACRO goto run
if exist "%ProgramFiles(x86)%\teraterm5\ttpmacro.exe" set "TT_MACRO=%ProgramFiles(x86)%\teraterm5\ttpmacro.exe"
if defined TT_MACRO goto run
if exist "%ProgramFiles(x86)%\teraterm\ttpmacro.exe" set "TT_MACRO=%ProgramFiles(x86)%\teraterm\ttpmacro.exe"
if defined TT_MACRO goto run
echo Tera Term was not found. Set TT_MACRO in this file to ttpmacro.exe.
echo You can also open collector.ttl with Tera Term Macro directly.
pause
exit /b 2
:run
if not exist "%TT_MACRO%" (
  echo ttpmacro.exe was not found at the configured path.
  pause
  exit /b 2
)
cd /d "%~dp0"
start "" /wait "%TT_MACRO%" "%~dp0collector.ttl"
exit /b %errorlevel%
