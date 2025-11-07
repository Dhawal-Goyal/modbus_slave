#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modbus RTU Slave Simulator - Windows GUI
- Tkinter GUI around a read-only Holding Register slave
- Uses pymodbus 3.x + pyserial
- CSV map input (addresses, types, values)
- Start/Stop server from GUI; live logs; COM port scan

This GUI embeds the core logic (CSV parsing, data block) so it can run standalone.
"""
import threading
import queue
import time
import os
import re
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from typing import Dict, List, Tuple, Optional

# Serial tools
try:
    import serial
    from serial.tools import list_ports
except Exception:
    serial = None
    list_ports = None

# Pymodbus imports
from pymodbus.server import StartSerialServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext, ModbusSparseDataBlock
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.constants import Endian
from pymodbus.exceptions import ModbusException

# -------------------------------
# Logging setup
# -------------------------------
LOG = logging.getLogger("modbus_gui")
LOG.setLevel(logging.INFO)
_log_handler = logging.StreamHandler()
_log_handler.setFormatter(logging.Formatter(fmt="%(asctime)s %(levelname)s: %(message)s"))
LOG.addHandler(_log_handler)

# -------------------------------
# Endianness / order maps
# -------------------------------
ORDER_CODE_MAP = {
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
from dataclasses import dataclass

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

# -----------------------
# Read-only Sparse Memory
# -----------------------
class ReadOnlySparseHR(ModbusSparseDataBlock):
    def __init__(self, mapping: Dict[int, int], strict_gaps: bool = False, on_read=None):
        super().__init__(dict(mapping))
        self.strict_gaps = strict_gaps
        self.on_read = on_read

    def getValues(self, address: int, count: int = 1) -> List[int]:
        if self.on_read:
            try:
                self.on_read(address, count)
            except Exception:
                pass
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
import csv
def load_csv_map(csv_path: str, four_base: int, defaults: Dict[str, str]):
    mapping: Dict[int, int] = {}
    log_lines: List[str] = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = [h.lower() for h in (reader.fieldnames or [])]
        for required in ["address","type","value"]:
            if required not in headers:
                raise ValueError(f"CSV missing required column: {required}")
        rownum = 1
        for raw in reader:
            rownum += 1
            row = {k.lower(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}

            addr = parse_address(row["address"], four_base=four_base)
            dtype = row["type"].lower()
            value = row["value"]
            length_chars = int(row["len"]) if row.get("len") else None
            byte_order = row.get("byte_order") or None
            word_order = row.get("word_order") or None
            order_code = row.get("order_code") or None
            pad = row.get("pad") or None
            comment = row.get("comment") or None

            mr = MapRow(addr, dtype, value, length_chars, byte_order, word_order, order_code, pad, comment)
            regs = pack_row_to_registers(mr, defaults)

            for i, reg in enumerate(regs):
                a = addr + i
                if a in mapping:
                    raise ValueError(f"Overlap at address {a} (row {rownum})")
            for i, reg in enumerate(regs):
                mapping[addr + i] = reg & 0xFFFF
    return mapping, log_lines

# -----------------------
# Server runner (threaded)
# -----------------------
import asyncio



class ServerThread(threading.Thread):
    def __init__(self, params, log_queue: queue.Queue):
        super().__init__(daemon=True)
        self.params = params
        self.log_queue = log_queue

    def run(self):
        try:
            mapping, _ = load_csv_map(self.params['csv_path'], self.params['four_base'], {
                "byte": self.params['byte_order'],
                "word": self.params['word_order'],
            })
            on_read = (lambda addr, cnt: self.log_queue.put(("DEBUG", f"READ HR[{addr}] x{cnt}"))) if self.params.get('log_reads') else None
            block = ReadOnlySparseHR(mapping, strict_gaps=self.params['strict_gaps'], on_read=on_read)
            store = ModbusSlaveContext(hr=block, di=None, co=None, ir=None, zero_mode=True)

            # Match CLI: bind to specific unit id via {slave: store}, single=False
            context = ModbusServerContext(slaves={self.params['slave']: store}, single=False)

            self.log_queue.put(("INFO", f"Starting Modbus RTU server on {self.params['port']} (baud={self.params['baud']}, bits={self.params['bytesize']}, parity={self.params['parity']}, stop={self.params['stopbits']}), slave={self.params['slave']}"))

            # StartSerialServer blocks forever (like CLI). Run inside this thread.
            StartSerialServer(
                context=context,
                framer=ModbusRtuFramer,
                port=self.params['port'],
                timeout=self.params['timeout'],
                baudrate=self.params['baud'],
                bytesize=self.params['bytesize'],
                parity=self.params['parity'],
                stopbits=self.params['stopbits'],
            )
        except Exception as e:
            self.log_queue.put(("ERROR", f"Server error: {e}"))
        finally:
            self.log_queue.put(("INFO", "Server stopped."))

    def stop(self):
        # StartSerialServer doesn't expose a direct stop hook.
        # We keep this for API compatibility; the GUI will explain that stopping
        # requires closing/restarting the app (same as CLI Ctrl+C).
        pass
# -----------------------
# Tkinter GUI
# -----------------------
class ModbusGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Modbus RTU Slave Simulator (GUI)")
        self.geometry("860x640")
        self.minsize(820, 580)

        self.server_thread: Optional[ServerThread] = None
        self.log_queue = queue.Queue()

        self._build_widgets()
        self._poll_log_queue()

    def _build_widgets(self):
        pad = {"padx": 8, "pady": 4}

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        # --- Tab: Settings ---
        self.tab_settings = ttk.Frame(nb)
        nb.add(self.tab_settings, text="Settings")

        frm = ttk.Frame(self.tab_settings)
        frm.pack(fill="x", **pad)

        # Row 1: Port + Refresh, CSV picker
        r1 = ttk.Frame(frm); r1.pack(fill="x", **pad)
        ttk.Label(r1, text="COM Port:").grid(row=0, column=0, sticky="w")
        self.cbo_port = ttk.Combobox(r1, width=12, values=self._list_ports())
        self.cbo_port.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(r1, text="Refresh", command=self._refresh_ports).grid(row=0, column=2, padx=4)
        ttk.Label(r1, text="CSV Map:").grid(row=0, column=3, sticky="e")
        self.ent_csv = ttk.Entry(r1, width=40)
        self.ent_csv.grid(row=0, column=4, sticky="we", padx=4)
        ttk.Button(r1, text="Browse...", command=self._browse_csv).grid(row=0, column=5, padx=4)
        r1.grid_columnconfigure(4, weight=1)

        # Row 2: Serial params
        r2 = ttk.Frame(frm); r2.pack(fill="x", **pad)
        ttk.Label(r2, text="Baud:").grid(row=0, column=0, sticky="w")
        self.cbo_baud = ttk.Combobox(r2, width=10, values=[1200,2400,4800,9600,19200,38400,57600,115200])
        self.cbo_baud.set(9600)
        self.cbo_baud.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(r2, text="Data bits:").grid(row=0, column=2, sticky="w")
        self.cbo_bits = ttk.Combobox(r2, width=5, values=[7,8]); self.cbo_bits.set(8)
        self.cbo_bits.grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(r2, text="Parity:").grid(row=0, column=4, sticky="w")
        self.cbo_parity = ttk.Combobox(r2, width=5, values=["N","E","O","M","S"]); self.cbo_parity.set("N")
        self.cbo_parity.grid(row=0, column=5, sticky="w", padx=4)

        ttk.Label(r2, text="Stop bits:").grid(row=0, column=6, sticky="w")
        self.cbo_stop = ttk.Combobox(r2, width=5, values=[1,2]); self.cbo_stop.set(1)
        self.cbo_stop.grid(row=0, column=7, sticky="w", padx=4)

        ttk.Label(r2, text="Timeout (s):").grid(row=0, column=8, sticky="w")
        self.ent_timeout = ttk.Entry(r2, width=6); self.ent_timeout.insert(0, "1.0")
        self.ent_timeout.grid(row=0, column=9, sticky="w", padx=4)

        # Row 3: Modbus params
        r3 = ttk.Frame(frm); r3.pack(fill="x", **pad)
        ttk.Label(r3, text="Slave ID:").grid(row=0, column=0, sticky="w")
        self.ent_slave = ttk.Entry(r3, width=6); self.ent_slave.insert(0, "1")
        self.ent_slave.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(r3, text="4xxxx Base:").grid(row=0, column=2, sticky="w")
        self.cbo_four = ttk.Combobox(r3, width=8, values=[40000,40001]); self.cbo_four.set(40001)
        self.cbo_four.grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(r3, text="32-bit Order:").grid(row=0, column=4, sticky="w")
        self.cbo_order = ttk.Combobox(r3, width=8, values=["(default)","ABCD","BADC","CDAB","DCBA"]); self.cbo_order.set("(default)")
        self.cbo_order.grid(row=0, column=5, sticky="w", padx=4)

        ttk.Label(r3, text="Byte Order:").grid(row=0, column=6, sticky="w")
        self.cbo_byte = ttk.Combobox(r3, width=8, values=["big","little"]); self.cbo_byte.set("big")
        self.cbo_byte.grid(row=0, column=7, sticky="w", padx=4)

        ttk.Label(r3, text="Word Order:").grid(row=0, column=8, sticky="w")
        self.cbo_word = ttk.Combobox(r3, width=8, values=["big","little"]); self.cbo_word.set("big")
        self.cbo_word.grid(row=0, column=9, sticky="w", padx=4)

        self.var_strict = tk.BooleanVar(value=False)
        ttk.Checkbutton(r3, text="Strict gaps (raise ILLEGAL DATA ADDRESS)", variable=self.var_strict).grid(row=1, column=0, columnspan=3, sticky="w", pady=4)
        self.var_logreads = tk.BooleanVar(value=False)
        ttk.Checkbutton(r3, text="Log reads", variable=self.var_logreads).grid(row=1, column=3, columnspan=2, sticky="w", pady=4)

        # Row 4: Start/Stop + Log level
        r4 = ttk.Frame(frm); r4.pack(fill="x", **pad)
        self.btn_start = ttk.Button(r4, text="Start Server", command=self._start_server)
        self.btn_start.grid(row=0, column=0, padx=4)
        self.btn_stop = ttk.Button(r4, text="Stop Server", command=self._stop_server, state="disabled")
        self.btn_stop.grid(row=0, column=1, padx=4)

        ttk.Label(r4, text="Log Level:").grid(row=0, column=2, sticky="e")
        self.cbo_loglevel = ttk.Combobox(r4, width=10, values=["DEBUG","INFO","WARNING","ERROR"])
        self.cbo_loglevel.set("INFO"); self.cbo_loglevel.grid(row=0, column=3, sticky="w", padx=4)
        ttk.Button(r4, text="Clear Log", command=self._clear_log).grid(row=0, column=4, padx=4)

        
        # --- Tab: Register Map ---
        self.tab_map = ttk.Frame(nb)
        nb.add(self.tab_map, text="Register Map")

        mapfrm = ttk.Frame(self.tab_map)
        mapfrm.pack(fill="both", expand=True, **pad)
        toolbar = ttk.Frame(mapfrm); toolbar.pack(fill="x", pady=4)
        ttk.Button(toolbar, text="Load/Refresh from CSV", command=self._load_map_preview).pack(side="left", padx=4)

        cols = ("address","value_dec","value_hex")
        self.tree_map = ttk.Treeview(mapfrm, columns=cols, show="headings")
        for c, w in zip(cols, (120, 160, 160)):
            self.tree_map.heading(c, text=c.replace("_"," ").title())
            self.tree_map.column(c, width=w, anchor="center")
        self.tree_map.pack(fill="both", expand=True)

# --- Tab: Logs ---
        self.tab_logs = ttk.Frame(nb)
        nb.add(self.tab_logs, text="Logs")

        logfrm = ttk.Frame(self.tab_logs)
        logfrm.pack(fill="both", expand=True, **pad)
        self.txt_log = tk.Text(logfrm, height=22, wrap="none")
        self.txt_log.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(logfrm, orient="vertical", command=self.txt_log.yview)
        sb.pack(fill="y", side="right")
        self.txt_log.configure(yscrollcommand=sb.set)

        # Menu
        menubar = tk.Menu(self)
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About", command=lambda: messagebox.showinfo("About", "Modbus RTU Slave Simulator GUI\npymodbus 3.x • Tkinter"))
        menubar.add_cascade(label="Help", menu=helpmenu)
        
        # Status bar
        self.status_var = tk.StringVar(value="Stopped")
        self.status_lbl = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_lbl.pack(fill="x", side="bottom")

        self.config(menu=menubar)

    # --- Utility ---
    def _list_ports(self):
        if not list_ports:
            return []
        return [p.device for p in list_ports.comports()]

    def _refresh_ports(self):
        ports = self._list_ports()
        self.cbo_port['values'] = ports
        if ports and not self.cbo_port.get():
            self.cbo_port.set(ports[0])

    def _browse_csv(self):
        path = filedialog.askopenfilename(title="Select CSV map", filetypes=[("CSV files","*.csv"),("All files","*.*")])
        if path:
            self.ent_csv.delete(0, tk.END)
            self.ent_csv.insert(0, path)

    def _append_log(self, level, msg):
        self.txt_log.insert(tk.END, f"[{level}] {msg}\n")
        self.txt_log.see(tk.END)

    def _clear_log(self):
        self.txt_log.delete("1.0", tk.END)

    def _poll_log_queue(self):
        try:
            while True:
                level, msg = self.log_queue.get_nowait()
                self._append_log(level, msg)
        except queue.Empty:
            pass
        self.after(150, self._poll_log_queue)

    # --- Server control ---
    
    def _set_status(self, text, color=None):
        self.status_var.set(text)
        try:
            if color:
                self.status_lbl.configure(foreground=color)
            else:
                self.status_lbl.configure(foreground="")
        except Exception:
            pass

    def _gather_params(self):
        order = self.cbo_order.get()
        if order == "(default)":
            byte = self.cbo_byte.get()
            word = self.cbo_word.get()
        else:
            # translate Endian enum to string if needed
            byte_enum, word_enum = ORDER_CODE_MAP[order]
            byte = "big" if byte_enum == Endian.BIG else "little"
            word = "big" if word_enum == Endian.BIG else "little"

        params = {
            "port": self.cbo_port.get() or "COM3",
            "baud": int(self.cbo_baud.get() or 9600),
            "bytesize": int(self.cbo_bits.get() or 8),
            "parity": self.cbo_parity.get() or "N",
            "stopbits": int(self.cbo_stop.get() or 1),
            "timeout": float(self.ent_timeout.get() or 1.0),
            "slave": int(self.ent_slave.get() or 1),
            "csv_path": self.ent_csv.get() or "map.csv",
            "four_base": int(self.cbo_four.get() or 40001),
            "byte_order": byte,
            "word_order": word,
            "strict_gaps": bool(self.var_strict.get()),
            "log_reads": bool(getattr(self, "var_logreads").get()),
        }
        return params

    def _start_server(self):
        # Adjust log level
        try:
            level = getattr(logging, self.cbo_loglevel.get().upper())
            LOG.setLevel(level)
        except Exception:
            pass

        params = self._gather_params()

        # Preflight COM open/close to catch obvious failures early
        if serial is not None:
            try:
                _ser = serial.Serial(
                    port=params['port'],
                    baudrate=params['baud'],
                    bytesize=params['bytesize'],
                    parity=params['parity'],
                    stopbits=params['stopbits'],
                    timeout=params['timeout'],
                )
                _ser.close()
            except Exception as e:
                messagebox.showerror("Serial preflight failed", f"Could not open {params['port']}: {e}")
                return
        if not os.path.exists(params['csv_path']):
            messagebox.showerror("CSV not found", f"CSV file not found: {params['csv_path']}")
            return

        self.server_thread = ServerThread(params, self.log_queue)
        self.server_thread.start()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._append_log("INFO", "Server thread started.")

        self._set_status("Starting...", color="orange")
        # After 1.2s, if thread is alive, assume running (StartSerialServer blocks on success)
        def _post_start_check():
            if self.server_thread and self.server_thread.is_alive():
                self._set_status("Running", color="green")
            else:
                self._set_status("Failed to start", color="red")
        self.after(1200, _post_start_check)


    def _stop_server(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread = None
            self._append_log("INFO", "Stop requested. StartSerialServer cannot be programmatically stopped; close the app to stop (same as CLI Ctrl+C).")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._set_status("Stopped", color="")


    def _load_map_preview(self):
        try:
            params = self._gather_params()
            if not os.path.exists(params['csv_path']):
                messagebox.showerror("CSV not found", f"CSV file not found: {params['csv_path']}")
                return
            mapping, _ = load_csv_map(params['csv_path'], params['four_base'], {
                "byte": params['byte_order'], "word": params['word_order'],
            })
            # clear
            for i in self.tree_map.get_children():
                self.tree_map.delete(i)
            # populate (sorted by address)
            for addr in sorted(mapping.keys()):
                v = mapping[addr] & 0xFFFF
                self.tree_map.insert("", "end", values=(addr, v, f"0x{v:04X}"))
            self._append_log("INFO", f"Preview loaded: {len(mapping)} registers")
        except Exception as e:
            messagebox.showerror("Preview error", str(e))
            self._append_log("ERROR", f"Preview error: {e}")

if __name__ == "__main__":
    app = ModbusGUI()
    app.mainloop()
