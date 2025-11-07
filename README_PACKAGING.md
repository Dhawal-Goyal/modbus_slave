# Packaging & Deployment (No Python on target machines)

This bundle helps you build **one-file EXEs** (GUI and/or CLI) and an **installer** for easy deployment to Windows PCs that do **not** have Python installed.

## What you need on the build machine
- Windows 10/11
- Python 3.10+
- PowerShell
- (Optional) Inno Setup 6.x for making a .exe installer

## Files in this folder
- `requirements.txt` – pinned versions (`pymodbus==3.6.8`, `pyserial==3.5`)
- `build_gui.ps1` – builds `dist\modbus-sim-gui.exe` (one-file GUI)
- `build_cli.ps1` – builds `dist\modbus-sim.exe` (one-file CLI)
- `installer.iss` – Inno Setup script (bundles GUI + optional CLI + sample CSV + Readme)
- `sample_map.csv` – starter CSV
- `README_DEPLOY.txt` – short user guide to run the EXE on target machines

Also place **these files** next to the scripts before building:
- `modbus_sim_gui.py` (the GUI app)
- `modbus_sim.py` (your CLI app) – optional if you don’t need CLI

## Build the GUI EXE (no Python on target)
Open PowerShell in this folder and run:
```powershell
.\build_gui.ps1
```
The EXE will appear at: `dist\modbus-sim-gui.exe`

## Build the CLI EXE (optional)
```powershell
.\build_cli.ps1
```
Output: `dist\modbus-sim.exe`

## Make a Windows installer (optional)
1. Install **Inno Setup** 6.x (if not already).
2. Ensure `dist\modbus-sim-gui.exe` (and optionally `dist\modbus-sim.exe`) exist.
3. Open `installer.iss` in Inno Setup → Build.
4. Output: `Output\ModbusSlaveSetup.exe`

## What the installer includes
- GUI EXE (mandatory)
- CLI EXE (if you check the “Also install the CLI” component)
- `sample_map.csv`
- End-user quick guide (`README_DEPLOY.txt`)

## Version pinning / reproducibility
- `requirements.txt` pins `pymodbus==3.6.8` and `pyserial==3.5`, tested with your scripts.
- PyInstaller bundles the exact Python runtime and libs into the EXE—**no Python required** on target PCs.

## Target PC requirements
- Windows 10/11 (x64)
- RS-485/USB driver for your adapter installed
- No admin rights needed to run the EXE

## Tips
- Use **com0com** to create virtual COM pairs for lab testing.
- If your masters bulk-read large spans, consider disabling “Strict gaps” to avoid exceptions.
