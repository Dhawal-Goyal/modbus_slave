@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ======== Safety: keep conda separate ========
if defined CONDA_PREFIX (
  echo.
  echo [ERROR] You are inside a Conda environment: %CONDA_PREFIX%
  echo Please open a normal "Command Prompt" (not Anaconda Prompt) and run this script again.
  exit /b 1
)

REM ======== Keep user/site packages from leaking in ========
set PYTHONNOUSERSITE=1

REM ======== Ensure we are in the packaging folder ========
pushd %~dp0

REM ======== Locate a clean Python (prefer py launcher 3.11) ========
for /f "delims=" %%v in ('py -3.11 -c "print(1)" 2^>nul') do set PY_OK=%%v
if not defined PY_OK (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python launcher not found. Install Python 3.11+ from https://www.python.org/downloads/windows/
    exit /b 1
  )
)
set "PYCMD=py -3.11"

REM ======== Create venv (local) ========
if not exist .venv\Scripts\python.exe (
  %PYCMD% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    exit /b 1
  )
)

set "VENV_PY=.venv\Scripts\python.exe"
set "VENV_PIP=.venv\Scripts\pip.exe"

REM ======== Install deps (pinned) ========
"%VENV_PY%" -m pip install --upgrade pip
if exist requirements.txt (
  "%VENV_PIP%" install -r requirements.txt
) else (
  echo [WARN] requirements.txt missing; installing defaults...
  "%VENV_PIP%" install pymodbus==3.6.8 pyserial==3.5
)
"%VENV_PIP%" install pyinstaller

REM ======== Build CLI EXE (onefile, console) ========
if not exist modbus_sim.py (
  echo [ERROR] modbus_sim.py not found in this folder.
  exit /b 1
)

"%VENV_PY%" -m PyInstaller --onefile --name modbus-sim modbus_sim.py
if errorlevel 1 (
  echo [ERROR] PyInstaller failed.
  exit /b 1
)

echo.
echo [OK] CLI build complete.
echo      -> %CD%\dist\modbus-sim.exe
echo.
popd
endlocal
