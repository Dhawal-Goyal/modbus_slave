# Modbus RTU Slave Simulator — Deployment Guide

This guide is for **end users** who will install and run the Modbus RTU Slave Simulator on Windows.
No Python is required. Only the installer (.exe) is needed.

---

## ✅ 1. System Requirements

- Windows 10 or Windows 11 (64‑bit)
- USB/RS‑485 driver installed (for your adapter)
- COM port available
- No administrator rights required (only for installation step)

---

## ✅ 2. Installation

1. Run **ModbusSlaveSetup.exe**
2. Follow the setup wizard
3. (Optional) Check “Install CLI tool” if you want command‑line mode
4. (Optional) Check “Create desktop shortcut”
5. Click **Finish**  
   The simulator starts automatically.

You can always open it from:
```
Start Menu → Modbus RTU Slave Simulator
```

---

## ✅ 3. Running the Simulator

1. Open **Modbus RTU Slave Simulator (GUI)**
2. Choose:
   - COM Port (example: COM3, COM5)
   - Baud Rate (default: 9600)
   - Data bits, parity, stopbits
   - Slave ID (default: 1)
3. Select a CSV file  
   → `sample_map.csv` is included
4. Choose address base:
   - **40001** (most devices)
   - **40000** (some devices)
5. Click **Start Server**

If successful:
- Status bar turns **green (Running)**
- Your Modbus master can now read registers from the simulator.

---

## ✅ 4. CSV Formatting (Basics)

Each row defines registers:

```
address,type,value
40001,uint16,1234
120,ascii,INVERTER-A
40100,uint32,305419896
```

Supported types:
- uint16, int16
- uint32, int32 (2 registers)
- ascii (2 chars per register)

The simulator automatically:
- converts 4xxxx addresses
- expands multi‑register values
- applies byte/word endianness

---

## ✅ 5. Troubleshooting

### ⚠ Master cannot read registers
Check:
- Correct COM port selected
- No other software using the port
- Serial parameters match master
- CSV addresses are correct
- 4xxxx base matches your CSV

### ⚠ Long block reads fail
Disable **Strict Gaps** in settings.

### ⚠ Simulator shows Running but master reads zeros
Open **Register Map** tab and verify:
- Values loaded correctly from CSV
- Addresses match what your master reads

### ⚠ Installer fails to run
Right‑click → Run as Administrator  
*(Only required first time)*

---

## ✅ 6. CLI Usage (Optional)

If installed, run:

```
modbus-sim.exe --port COM5 --slave 1 --csv sample_map.csv
```

---

## ✅ 7. Uninstall

From Windows:

```
Settings → Apps → Modbus RTU Slave Simulator → Uninstall
```

or:

```
Start Menu → Uninstall Modbus RTU Slave Simulator
```

---

## ✅ Need Help?

Contact the project maintainer or open a GitHub issue.

Enjoy using the Modbus RTU Slave Simulator!
