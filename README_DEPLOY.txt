# Modbus RTU Slave Simulator – Quick Start (No Python Needed)

1) Double-click **Modbus RTU Slave Simulator** (GUI).
2) Choose COM port, CSV file, and serial settings.
3) Click **Start Server**. Status should show **Running**.
4) Use your Modbus master to read Holding Registers.
5) To stop: close the window (same semantics as CLI Ctrl+C).

Notes:
- CSV supports 4xxxx, hex, or zero-based addresses.
- Data types: int16, uint16, int32, uint32, ascii.
- Endianness: ABCD/BADC/CDAB/DCBA or per-row byte/word fields.
