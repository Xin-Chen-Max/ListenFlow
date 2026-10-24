@echo off
setlocal
cd /d "%~dp0"
set "LISTENFLOW_SETUP_FILE=requirements-cpu.txt"
set "LISTENFLOW_SETUP_PAUSE=1"

:args
if "%~1"=="" goto prepare
if /I "%~1"=="gpu" (
  set "LISTENFLOW_SETUP_FILE=requirements.txt"
  shift
  goto args
)
if /I "%~1"=="cpu" (
  shift
  goto args
)
if /I "%~1"=="--no-pause" (
  set "LISTENFLOW_SETUP_PAUSE="
  shift
  goto args
)
echo Usage: setup.bat [cpu^|gpu] [--no-pause]
goto failed

:prepare
if exist ".venv\Scripts\python.exe" goto install
echo Creating a Python 3.12 environment...
if defined LISTENFLOW_PYTHON (
  "%LISTENFLOW_PYTHON%" -m venv .venv
) else (
  py -3.12 -m venv .venv
)
if errorlevel 1 (
  echo Install Python 3.12, including its launcher, or set LISTENFLOW_PYTHON to python.exe.
  goto failed
)

:install
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(sys.version_info[:2] != (3,12))"
if errorlevel 1 (
  echo This setup requires Python 3.12. Preserve your recordings when replacing an environment.
  goto failed
)
echo Installing %LISTENFLOW_SETUP_FILE%...
".venv\Scripts\python.exe" -m pip install --upgrade "pip>=26.2,<27"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r "%LISTENFLOW_SETUP_FILE%"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\check_setup.py
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click run.bat to start ListenFlow.
if defined LISTENFLOW_SETUP_PAUSE pause
exit /b 0

:failed
echo.
echo Setup did not complete. Follow docs\setup.md and the error above.
if defined LISTENFLOW_SETUP_PAUSE pause
exit /b 1
