@echo off
setlocal
cd /d "%~dp0"
set "LISTENFLOW_RUN_PAUSE=1"
for %%A in (%*) do if /I "%%~A"=="--no-pause" set "LISTENFLOW_RUN_PAUSE="
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first. See docs\setup.md for instructions.
  if defined LISTENFLOW_RUN_PAUSE pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\start.py %*
set "LISTENFLOW_RUN_RESULT=%ERRORLEVEL%"
if defined LISTENFLOW_RUN_PAUSE pause
exit /b %LISTENFLOW_RUN_RESULT%
