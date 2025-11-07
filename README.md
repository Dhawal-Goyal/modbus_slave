# Modbus RTU Holding Register Slave Simulator (Windows)

A lightweight, **read-only** Modbus **RTU** slave for **Windows COM ports**, publishing **Holding Registers** from a **CSV** map.

- Protocol: **RTU** (over `COMx`)
- Tables: **Holding Registers** only (FC3)
- Access: **Read-only** (write requests are ignored & logged)
- Input: **CSV** with addresses, types, values
- Types: `int16`, `uint16`, `int32`, `uint32`, `ascii`
- Endianness for 32-bit: global defaults + per-row overrides via `order_code` (`ABCD|BADC|CDAB|DCBA`) or `byte_order`+`word_order`
- Address formats: `4xxxx` (subtracts base), hex like `0x0064`, or zero-based integer
- Unmapped reads → 0 (or `--strict-gaps` to raise ILLEGAL DATA ADDRESS)

> Requires: `pymodbus>=3`, `pyserial`

---

## 1) Install (for testing)
```powershell
python -m pip install --upgrade pip
pip install pymodbus pyserial
```

## 2) Prepare CSV
Edit **map.csv**. Example rows included.

## 3) Run
```powershell
python modbus_sim.py --port COM3 --baud 9600 --slave 1 --csv map.csv --order CDAB
```
Common options:
- `--bytesize 8 --parity N --stopbits 1 --timeout 1.0`
- `--four-base 40001` (or `40000` if you prefer 1-based)
- `--byte-order big --word-order big` (if not using `--order`)
- `--strict-gaps` (makes gaps raise ILLEGAL DATA ADDRESS)

### Addressing rules
- `40001` (4xxxx) → subtracts `--four-base` to get zero-based index.
- `0x0064` → hex parsed as zero-based index.
- `120` → already zero-based index.

### Data types
- `int16` / `uint16` → 1 register
- `int32` / `uint32` → 2 registers (32-bit, uses selected endianness)
- `ascii` → 2 chars per register. Use `len` and `pad` (`space`/`null`).

### Read-only behavior
- Reads (FC3) supported.
- Writes (FC6/16) are **ignored** and logged. (Strict exception responses for writes would require deeper function-handler customization.)

### Gaps
- By default, reads spanning unmapped addresses return zeros for those cells.
- To make unmapped addresses fail, use `--strict-gaps`.

---

## 4) Quick test (no hardware)
Create a virtual COM pair (e.g., [com0com]), run this simulator on one COM, and a Modbus master (QModMaster/Modbus Poll/pymodbus client) on the other.

---

## 5) Packaging to a single EXE (Windows)
See **build_windows.txt** for PyInstaller steps. Result: one-file `.exe` you can distribute; no Python needed on target machines.

---

## 6) CSV Columns
| Column       | Required | Example            | Notes |
|--------------|----------|--------------------|-------|
| address      | ✔        | `40001` / `0x0064` / `100` | Address in 4xxxx, hex, or zero-based. |
| type         | ✔        | `int16` / `uint16` / `int32` / `uint32` / `ascii` | Data type. |
| value        | ✔        | `1234` / `-10` / `HELLO`   | For `ascii`, the string. |
| len          | ascii    | `10`               | Char length to publish (optional). |
| byte_order   | 32-bit   | `big` / `little`   | Optional per-row override. |
| word_order   | 32-bit   | `big` / `little`   | Optional per-row override. |
| order_code   | 32-bit   | `ABCD` `BADC` `CDAB` `DCBA` | Overrides byte/word if present. |
| pad          | ascii    | `space` / `null`   | Padding for odd/short strings. |
| comment      | –        | `Room temp`        | Ignored by simulator. |

---

## 7) Notes
- 32-bit values use `pymodbus.payload.BinaryPayloadBuilder` honoring byte/word order.
- Overlaps are detected; startup fails with helpful message.
- Out-of-range values are validated for each type.
- `--strict-gaps` can help detect map holes during master bulk reads.
