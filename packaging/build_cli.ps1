\
# Build CLI one-file EXE with PyInstaller

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
& $venvPython -m PyInstaller --onefile --name modbus-sim modbus_sim.py

Write-Host "CLI build complete. Output: dist\modbus-sim.exe"
