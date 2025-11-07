#!/usr/bin/env python3
"""
Modbus RTU Slave Simulator (pymodbus 3.6.8 compatible)
- RTU over COMx
- Holding Registers (FC3) only
- Read-only (write requests ignored & logged)
- CSV map input; supports 4xxxx, hex, or zero-based addressing
- int16/uint16 (1 reg), int32/uint32 (2 regs with selectable byte/word order), ascii (2 chars/reg)
"""

import argparse
import csv
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from pymodbus.server import ModbusSerialServer, StartSerialServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext, ModbusSparseDataBlock
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.constants import Endian
from pymodbus.exceptions import ModbusException
import csv, io, re
from typing import Dict, List, Tuple

LOG = logging.getLogger("modbus_sim")

# -------------------------------
# Helpers: endianness / order map
# -------------------------------

ORDER_CODE_MAP = {
    # (byte_order, word_order)
    "ABCD": (Endian.BIG, Endian.BIG),
    "BADC": (Endian.LITTLE, Endian.BIG),
    "CDAB": (Endian.BIG, Endian.LITTLE),
    "DCBA": (Endian.LITTLE, Endian.LITTLE),
}

BYTE_ORDER_MAP = {"big": Endian.BIG, "little": Endian.LITTLE}
WORD_ORDER_MAP = {"big": Endian.BIG, "little": Endian.LITTLE}

# --------------------
# Address normalization
# --------------------

def parse_address(addr_str: str, four_base: int) -> int:
    """
    Convert a user-provided address string to zero-based register index.
    Accepts 4xxxx (subtract base), hex 0x..., or zero-based integer.
    """
    s = str(addr_str).strip()
    if re.fullmatch(r"4\d{4,}", s):
        base = int(s)
        if base < four_base:
            raise ValueError(f"4xxxx address {s} < configured base {four_base}")
        return base - four_base
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s, 10)

# -------------------------------
# CSV row → register serialization
# -------------------------------

@dataclass
class MapRow:
    address: int
    dtype: str
    value: str
    length_chars: Optional[int]
    byte_order: Optional[str]
    word_order: Optional[str]
    order_code: Optional[str]
    pad: Optional[str]
    comment: Optional[str]

def coerce_int(val: str) -> int:
    try:
        return int(str(val), 10)
    except ValueError:
        if str(val).lower().startswith("0x"):
            return int(str(val), 16)
        raise

def pack_row_to_registers(row: MapRow, defaults) -> List[int]:
    dtype = row.dtype.lower().strip()

    # Resolve endianness for 32-bit via order_code or byte/word order
    byte_order = BYTE_ORDER_MAP.get((row.byte_order or defaults['byte']).lower(), Endian.BIG)
    word_order = WORD_ORDER_MAP.get((row.word_order or defaults['word']).lower(), Endian.BIG)
    if row.order_code:
        code = row.order_code.strip().upper()
        if code not in ORDER_CODE_MAP:
            raise ValueError(f"Unknown order_code '{row.order_code}'")
        byte_order, word_order = ORDER_CODE_MAP[code]

    if dtype in ("int16", "uint16"):
        v = coerce_int(row.value)
        if dtype == "uint16" and not (0 <= v <= 0xFFFF):
            raise ValueError(f"uint16 out of range: {v}")
        if dtype == "int16" and not (-0x8000 <= v <= 0x7FFF):
            raise ValueError(f"int16 out of range: {v}")
        return [v & 0xFFFF]

    elif dtype in ("int32", "uint32"):
        v = coerce_int(row.value)
        if dtype == "uint32" and not (0 <= v <= 0xFFFFFFFF):
            raise ValueError(f"uint32 out of range: {v}")
        if dtype == "int32" and not (-0x80000000 <= v <= 0x7FFFFFFF):
            raise ValueError(f"int32 out of range: {v}")
        builder = BinaryPayloadBuilder(byteorder=byte_order, wordorder=word_order)
        if dtype == "int32":
            builder.add_32bit_int(v)
        else:
            builder.add_32bit_uint(v)
        regs = list(builder.to_registers())
        if len(regs) != 2:
            raise RuntimeError("pack int32/uint32 did not produce 2 registers")
        return regs

    elif dtype == "ascii":
        s = str(row.value)
        target_len = row.length_chars if row.length_chars is not None else len(s)
        pad_char = ' ' if (row.pad or '').lower() != 'null' else '\x00'
        if len(s) < target_len:
            s = s + pad_char * (target_len - len(s))
        elif len(s) > target_len:
            s = s[:target_len]
        b = s.encode("ascii", errors="ignore")
        if len(b) % 2 == 1:
            b += pad_char.encode("ascii")
        regs = []
        for i in range(0, len(b), 2):
            regs.append((b[i] << 8) | b[i+1])
        return regs

    else:
        raise ValueError(f"Unsupported dtype '{row.dtype}'")
    
# -------- CSV tolerant helpers --------
POSSIBLE_ENCODINGS = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]

def _open_text_any(path: str):
    """Open a text file trying multiple encodings, returning a file object."""
    last_err = None
    for enc in POSSIBLE_ENCODINGS:
        try:
            return open(path, "r", encoding=enc, newline="")
        except UnicodeDecodeError as e:
            last_err = e
    if last_err:
        raise last_err
    # If we get here for some reason, fall back to binary + latin-1 decode
    return io.TextIOWrapper(open(path, "rb"), encoding="latin-1", newline="")

def _norm(s: str) -> str:
    """Normalize header/field names: strip spaces, strip BOM, lowercase."""
    if s is None:
        return ""
    return s.strip().lstrip("\ufeff").lower()

def _parse_int(s: str) -> int:
    """Parse decimal or 0xHEX."""
    s = s.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s, 10)

def _parse_address(raw: str, four_base: int) -> int:
    """
    Accept 0xHEX, decimal, or 4xxxx family.
    If 4xxxx (e.g., 40100), convert to zero-based by subtracting four_base.
    """
    raw = raw.strip()
    if raw.lower().startswith("0x"):
        return int(raw, 16)
    n = int(raw, 10)
    # Treat 4xxxx family specially
    if n >= 40000:
        return n - four_base
    return n
# --------------------------------------

# -----------------------
# Read-only Sparse Memory
# -----------------------

class ReadOnlySparseHR(ModbusSparseDataBlock):
    """
    Sparse, read-only holding register block.
    - getValues: returns mapped values; unmapped -> zero (or exception if strict)
    - setValues: ignored (logged)
    - validate: honors strict gaps if enabled
    """
    def __init__(self, mapping: Dict[int, int], strict_gaps: bool = False):
        super().__init__(dict(mapping))
        self.strict_gaps = strict_gaps

    def getValues(self, address: int, count: int = 1) -> List[int]:
        result = []
        for a in range(address, address + count):
            if a in self.values:
                result.append(self.values[a])
            else:
                if self.strict_gaps:
                    raise ModbusException("Illegal address")
                result.append(0)
        return result

    def setValues(self, address: int, values: List[int]) -> None:
        LOG.warning("Write ignored at HR[%d..%d]: %s", address, address+len(values)-1, values)

    def validate(self, address: int, count: int = 1) -> bool:
        if not self.strict_gaps:
            return True
        for a in range(address, address + count):
            if a not in self.values:
                return False
        return True

# -------------------
# CSV → memory mapping
# -------------------

def load_csv_map(csv_path: str, four_base: int, endian_cfg: Dict[str, str]) -> Tuple[Dict[int, int], Dict]:
    """
    Reads a CSV describing holding registers and returns:
      - mapping: {register_address: 16bit_value}
      - meta:    dict with details (e.g., rows_count)

    CSV tolerated encodings: utf-8, utf-8-sig, cp1252, latin-1
    Header names are normalized (strip/BOM/lowercase).
    Required columns: address, type, value
    Optional columns: len, order_code, byte_order, word_order, pad, comment
    """
    mapping: Dict[int, int] = {}
    meta = {"rows": 0, "errors": []}

    with _open_text_any(csv_path) as f:
        rdr = csv.DictReader(f)
        # Normalize headers (handle BOM, casing, spaces)
        if not rdr.fieldnames:
            raise ValueError("CSV has no header row.")
        rdr.fieldnames = [_norm(h) for h in rdr.fieldnames]

        required = {"address", "type", "value"}
        missing = required.difference(set(rdr.fieldnames))
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")

        # Local helpers for 32-bit ordering
        def _split32(v: int, order: str) -> List[int]:
            """Return two 16-bit words according to ABCD/BADC/CDAB/DCBA."""
            v = v & 0xFFFFFFFF
            hi = (v >> 16) & 0xFFFF
            lo = v & 0xFFFF
            if order == "abcd":   # hi then lo (big-endian)
                return [hi, lo]
            if order == "badc":   # bytes swapped within words
                a = ((hi >> 8) & 0xFF) | ((hi & 0xFF) << 8)
                b = ((lo >> 8) & 0xFF) | ((lo & 0xFF) << 8)
                return [a, b]
            if order == "cdab":   # word swap
                return [lo, hi]
            if order == "dcba":   # word swap + byte swap
                a = ((lo >> 8) & 0xFF) | ((lo & 0xFF) << 8)
                b = ((hi >> 8) & 0xFF) | ((hi & 0xFF) << 8)
                return [a, b]
            # default: ABCD
            return [hi, lo]

        for row in rdr:
            meta["rows"] += 1
            row = { _norm(k): (v.strip() if isinstance(v, str) else v) for k, v in row.items() }

            try:
                addr0 = _parse_address(row["address"], four_base)
                typ   = row.get("type","").lower()
                val_s = row.get("value","")

                # Optional fields
                length = int(row.get("len") or 0) if row.get("len") else 0
                order_code = (row.get("order_code") or "").strip().lower()
                byte_order = (row.get("byte_order") or endian_cfg.get("byte","big")).strip().lower()
                word_order = (row.get("word_order") or endian_cfg.get("word","big")).strip().lower()
                pad = (row.get("pad") or "").strip().lower()

                # Normalize 32-bit ordering shortcut
                if order_code in {"abcd","badc","cdab","dcba"}:
                    order32 = order_code
                else:
                    # Derive from byte/word if no explicit code
                    # Simplified mapping: big/big -> abcd, little/big -> badc, big/little -> cdab, little/little -> dcba
                    bw = (byte_order, word_order)
                    order32 = {"bigbig":"abcd","littlebig":"badc","biglittle":"cdab","littlelittle":"dcba"}.get(
                        f"{bw[0]}{bw[1]}", "abcd"
                    )

                # Expand types
                if typ in ("uint16","int16"):
                    v = int(val_s, 10)
                    if typ == "int16" and v < 0:
                        v = (v + (1 << 16)) & 0xFFFF
                    mapping[addr0] = v & 0xFFFF

                elif typ in ("uint32","int32"):
                    v = int(val_s, 10)
                    if typ == "int32" and v < 0:
                        v = (v + (1 << 32)) & 0xFFFFFFFF
                    w0, w1 = _split32(v, order32)
                    mapping[addr0] = w0 & 0xFFFF
                    mapping[addr0 + 1] = w1 & 0xFFFF

                elif typ == "ascii":
                    # two chars per register
                    s = val_s
                    n_chars = int(row.get("len") or 0) or len(s)
                    if pad == "space":
                        s = s.ljust(n_chars)[:n_chars]
                    elif pad == "null":
                        s = s.ljust(n_chars, "\x00")[:n_chars]
                    else:
                        s = s[:n_chars]
                    # pack into 16-bit words
                    i = 0
                    reg = addr0
                    while i < len(s):
                        c1 = ord(s[i])
                        c2 = ord(s[i+1]) if i+1 < len(s) else 0
                        word = ((c1 & 0xFF) << 8) | (c2 & 0xFF)
                        mapping[reg] = word
                        reg += 1
                        i += 2

                else:
                    raise ValueError(f"Unsupported type '{typ}' at row {meta['rows']}")

            except Exception as e:
                meta["errors"].append(f"Row {meta['rows']}: {e}")

    # Optional: you can decide to raise if there were row errors
    if meta["errors"]:
        # Raise a compact error; or log and continue depending on your philosophy
        raise ValueError("CSV parse errors:\n" + "\n".join(meta["errors"][:10]))

    return mapping, meta


# --------------
# Main entrypoint
# --------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Modbus RTU Holding-Register Slave Simulator (Read-Only)")
    parser.add_argument("--port", default=os.getenv("MODBUS_PORT", "COM3"), help="Serial port (e.g., COM3)")
    parser.add_argument("--baud", type=int, default=int(os.getenv("MODBUS_BAUD", "9600")), help="Baud rate")
    parser.add_argument("--bytesize", type=int, default=8, help="Data bits")
    parser.add_argument("--parity", choices=["N","E","O","M","S"], default="N", help="Parity")
    parser.add_argument("--stopbits", type=int, choices=[1,2], default=1, help="Stop bits")
    parser.add_argument("--timeout", type=float, default=1.0, help="Read timeout (s)")
    parser.add_argument("--slave", type=int, default=1, help="Slave ID")
    parser.add_argument("--csv", dest="csv_path", default="map.csv", help="CSV map path")
    parser.add_argument("--four-base", type=int, default=40001, help="Base for 4xxxx addressing (40001 or 40000)")
    parser.add_argument("--order", choices=["ABCD","BADC","CDAB","DCBA"], help="Global 32-bit order code (overrides byte/word)")
    parser.add_argument("--byte-order", choices=["big","little"], default="big", help="Default byte order for 32-bit types")
    parser.add_argument("--word-order", choices=["big","little"], default="big", help="Default word order for 32-bit types")
    parser.add_argument("--strict-gaps", action="store_true", help="If set, unmapped addresses raise ILLEGAL DATA ADDRESS")
    parser.add_argument("--log", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")

    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    defaults = {
        "byte": (ORDER_CODE_MAP[args.order][0] if args.order else BYTE_ORDER_MAP[args.byte_order]),
        "word": (ORDER_CODE_MAP[args.order][1] if args.order else WORD_ORDER_MAP[args.word_order]),
    }

    LOG.info("Loading CSV map: %s", args.csv_path)
    mapping, lines = load_csv_map(args.csv_path, args.four_base, defaults)
    for line in lines:
        LOG.debug(line)
    LOG.info("Loaded %d registers populated (sparse)", len(mapping))

    block = ReadOnlySparseHR(mapping, strict_gaps=args.strict_gaps)
    store = ModbusSlaveContext(hr=block, di=None, co=None, ir=None, zero_mode=True)

    # Bind to specific unit id
    context = ModbusServerContext(slaves={args.slave: store}, single=False)

    LOG.info("Starting Modbus RTU server on %s (baud=%s, bits=%s, parity=%s, stop=%s), slave=%s",
             args.port, args.baud, args.bytesize, args.parity, args.stopbits, args.slave)

    StartSerialServer(
        context=context,
        framer=ModbusRtuFramer,
        port=args.port,
        timeout=args.timeout,
        baudrate=args.baud,
        bytesize=args.bytesize,
        parity=args.parity,
        stopbits=args.stopbits,
    )

if __name__ == "__main__":
    main()
