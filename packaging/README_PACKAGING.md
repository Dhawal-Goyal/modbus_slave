# Packaging Guide — Modbus RTU Slave Simulator  
This document explains how to build the **Windows EXE** and **Windows Installer** for the Modbus RTU Slave Simulator project.

You **only need Python on the build machine**, not on target machines.

---

# ✅ 1. Folder Structure

Your repo should look like this:

```
modbus-rtu-slave-sim/
├─ src/
│   ├─ modbus_sim_gui.py       # GUI app
│   └─ modbus_sim.py           # CLI app (optional)
│
├─ packaging/
│   ├─ build_gui.bat
│   ├─ build_cli.bat
│   ├─ installer.iss
│   ├─ requirements.txt
│   ├─ README_PACKAGING.md
│   └─ README_DEPLOY.txt
│
├─ sample_map.csv
├─ ModbusSlaveSetup.exe        # (after building installer)
└─ .gitignore
```

---

# ✅ 2. Requirements on the Build Machine

You need:

### ✅ Windows 10/11  
### ✅ Python 3.10+ installed  
Make sure to tick:
- ✅ “Add Python to PATH”
- ✅ “Install py launcher”

### ✅ Internet access (for dependency install)

### ✅ Inno Setup (optional, for installer)
Download:  
https://jrsoftware.org/isinfo.php

---

# ✅ 3. Build a Single-File Windows EXE

We use **PyInstaller**.  
To avoid PowerShell security issues, use the **.BAT** files.

Open **Command Prompt** (NOT PowerShell):

1️⃣ Navigate to packaging folder:

```
cd packaging
```

2️⃣ Build the GUI EXE:

```
build_gui.bat
```

This will:

✅ Create `.venv/`  
✅ Install dependencies (from requirements.txt)  
✅ Install PyInstaller  
✅ Produce:

```
dist\modbus-sim-gui.exe
```

3️⃣ (Optional) Build the CLI EXE:

```
build_cli.bat
```

Produces:

```
dist\modbus-sim.exe
```

---

# ✅ 4. Build the Windows Installer (.exe Setup Wizard)

You need **Inno Setup 6.x** installed.

After PyInstaller builds are ready (in `dist/`):

1️⃣ Open Inno Setup  
2️⃣ File → Open → choose:

```
packaging/installer.iss
```

3️⃣ Click **Build** (top menu)

If successful, you will get:

```
Output/ModbusSlaveSetup.exe
```

This is the **installer** you can distribute to any Windows PC.

---

# ✅ 5. What the Installer Includes

✔ GUI EXE (`modbus-sim-gui.exe`)  
✔ CLI EXE (optional via “Components” step in the installer)  
✔ `sample_map.csv`  
✔ `README_DEPLOY.txt`  
✔ Creates Start Menu shortcuts  
✔ Optionally creates desktop shortcut  
✔ Launches app after installation

---

# ✅ 6. Making a Release Automatically (GitHub Actions)

A workflow file is provided:

```
.github/workflows/build.yml
```

This workflow:

✅ Builds GUI EXE  
✅ Builds CLI EXE  
✅ Builds Installer (Inno Setup)  
✅ Uploads all 3 artifacts  
✅ If triggered by a tag (e.g. v1.0.0), creates a GitHub Release and attaches:

- modbus-sim-gui.exe  
- modbus-sim.exe  
- ModbusSlaveSetup.exe  

### How to trigger a release:

```
git tag v1.0.0
git push origin v1.0.0
```

---

# ✅ 7. Common Build Problems & Fixes

### ❌ “Python not found”
Install Python and ensure PATH is enabled.

### ❌ PowerShell restricts scripts
Use **Command Prompt** and the `.BAT` files.

### ❌ Inno Setup cannot find EXE
Run build_gui.bat before building installer.

### ❌ Missing PyInstaller output folder
Check `dist/` after running build scripts.

---

# ✅ 8. Troubleshooting Installation

### Master does not read
Check:
- COM port available
- Base address (40000 vs 40001)
- CSV mapped correctly
- Strict gaps disabled (if doing long reads)

### EXE closes immediately
Run from command prompt to see error.

---

# ✅ 9. Rebuilding Everything from Scratch  
(Full clean)

```
rmdir /s /q .venv
rmdir /s /q dist
rmdir /s /q build
rmdir /s /q Output
build_gui.bat
```

---

# ✅ 10. Support / Maintenance

This packaging process is stable and repeatable.  
You rarely need to change anything except:

- `installer.iss` (branding)
- `modbus_sim_gui.py` (adding features)
- `requirements.txt` (if updating dependencies)

If GitHub Actions builds fail, open the Actions tab for logs.

---

# ✅ Done

Your packaging process is now complete, tested, and automated.
