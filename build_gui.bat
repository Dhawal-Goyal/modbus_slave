@echo off
setlocal

REM === Locate Python (prefer py launcher) ===
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set PYTHON=py -3
) else (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 (
    set PYTHON=python
  ) else (
    echo ERROR: Python not found. Please install Python 3.10+ on the BUILD machine.
    echo Download: https://www.python.org/downloads/windows/
    exit /b 1
  )
)

REM === Create venv if missing ===
if not exist .venv\Scripts\python.exe (
  %PYTHON% -m venv .venv
  if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to create virtual environment.
    exit /b 1
  )
)

set VENV_PY=.venv\Scripts\python.exe
set VENV_PIP=.venv\Scripts\pip.exe

REM === Upgrade pip and install deps ===
%VENV_PY% -m pip install --upgrade pip
if exist requirements.txt (
  %VENV_PIP% install -r requirements.txt
) else (
  echo WARNING: requirements.txt not found, installing pinned defaults...
  %VENV_PIP% install pymodbus==3.6.8 pyserial==3.5
)

REM === Install PyInstaller ===
%VENV_PIP% install pyinstaller

REM === Build GUI ===
if not exist modbus_sim_gui.py (
  echo ERROR: modbus_sim_gui.py not found in current folder.
  exit /b 1
)

%VENV_PY% -m PyInstaller --onefile --windowed --name modbus-sim-gui modbus_sim_gui.py
if %ERRORLEVEL% neq 0 (
  echo ERROR: PyInstaller build failed.
  exit /b 1
)

echo.
echo SUCCESS: GUI build complete.
echo EXE: %CD%\dist\modbus-sim-gui.exe
echo.

endlocal
