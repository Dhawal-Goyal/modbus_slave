\
# Build GUI one-file EXE with PyInstaller
# Usage: right-click > Run with PowerShell (or run from a PS prompt)

param(
    [string]$Python = "python",
    [string]$WorkDir = ".",
    [string]$VenvDir = ".venv"
)

Set-Location $WorkDir

# 1) Create venv
& $Python -m venv $VenvDir
$venvPython = Join-Path $VenvDir "Scripts\python.exe"
$venvPip    = Join-Path $VenvDir "Scripts\pip.exe"

# 2) Upgrade pip and install deps
& $venvPython -m pip install --upgrade pip
& $venvPip install -r requirements.txt
& $venvPip install pyinstaller

# 3) Build
& $venvPython -m PyInstaller --onefile --windowed --name modbus-sim-gui modbus_sim_gui.py

Write-Host "GUI build complete. Output: dist\modbus-sim-gui.exe"
