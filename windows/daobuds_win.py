#!/usr/bin/env python3
"""DAO Buds — Cross-platform Desktop App (Windows & Linux) for Redmagic DAO TWS (BH4010).

Zero external dependencies: uses Python 3 standard library (tkinter + native AF_BLUETOOTH RFCOMM ch 11).
Speaks Qualcomm GAIA v3 (Vendor 0x001D) + Redmagic Custom Feature 0x0E directly to the earbuds.
"""

import platform
import re
import select
import socket
import struct
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Tuple

RFCOMM_CH = 11
VENDOR_QTIL = 0x001D
FEAT_BASIC = 0x00
FEAT_EARBUD = 0x01
FEAT_EQ = 0x05
FEAT_HANDSET = 0x07
FEAT_AC = 0x08
FEAT_BATTERY = 0x0D
FEAT_CUSTOM = 0x0E

TOUCH_LABELS = ["Off", "Play / Pause", "Previous", "Next", "Switch ANC", "Game Mode"]
CODEC_LABELS = ["Empty", "Normal (SBC/AAC/aptX)", "LHDC 5.0", "aptX Lossless"]
LED_LABELS = ["Off", "Static", "Breathing", "Rainbow"]
EQ_FREQS = [31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]


def discover_dao_mac() -> str:
    sysname = platform.system()
    if sysname == "Windows":
        try:
            ps = (
                "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
                "Where-Object { $_.FriendlyName -match 'DAO TWS' } | "
                "Select-Object -ExpandProperty InstanceId"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=4,
            )
            m = re.search(r"DEV_([0-9A-Fa-f]{12})", out)
            if m:
                h = m.group(1).upper()
                return ":".join(h[i : i + 2] for i in range(0, 12, 2))
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(
                ["bluetoothctl", "devices"], text=True, stderr=subprocess.DEVNULL, timeout=3
            )
            for line in out.splitlines():
                if "DAO TWS" in line.upper():
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]
        except Exception:
            pass
    return ""


def detect_dongle_present() -> bool:
    if platform.system() == "Windows":
        try:
            out = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_19D2&PID_0616' }).Count",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            ).strip()
            return int(out or "0") > 0
        except Exception:
            return False
    try:
        out = subprocess.check_output(["lsusb"], text=True, stderr=subprocess.DEVNULL, timeout=2)
        return "19d2:0616" in out.lower()
    except Exception:
        return False


class GaiaClient:
    def __init__(self, mac: str):
        self.mac = mac
        self.sock: Optional[socket.socket] = None

    def __enter__(self):
        self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        self.sock.settimeout(4.0)
        self.sock.connect((self.mac, RFCOMM_CH))
        self._recv(0.35)
        return self

    def __exit__(self, *_):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _recv(self, timeout: float = 0.7) -> bytes:
        assert self.sock is not None
        out = bytearray()
        while True:
            r, _, _ = select.select([self.sock], [], [], timeout)
            if not r:
                break
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            out.extend(chunk)
            timeout = 0.12
        return bytes(out)

    @staticmethod
    def _parse(buf: bytes) -> List[Tuple[int, int, int, int, bytes]]:
        frames = []
        i = 0
        while i < len(buf):
            if buf[i] != 0xFF or i + 8 > len(buf):
                i += 1
                continue
            flags, plen = buf[i + 2], buf[i + 3]
            vendor, pdu = struct.unpack(">HH", buf[i + 4 : i + 8])
            chk = 1 if (flags & 0x01) else 0
            end = i + 8 + plen + chk
            if end > len(buf):
                break
            frames.append((vendor, (pdu >> 9) & 0x7F, (pdu >> 7) & 0x03, pdu & 0x7F, buf[i + 8 : i + 8 + plen]))
            i = end
        return frames

    def cmd(self, feat: int, pid: int, payload: bytes = b"") -> Tuple[bool, bytes]:
        assert self.sock is not None
        pdu = ((feat & 0x7F) << 9) | (pid & 0x7F)
        frame = struct.pack(">BBBBHH", 0xFF, 0x03, 0x00, len(payload), VENDOR_QTIL, pdu) + payload
        self.sock.send(frame)
        for v, rf, pt, rpid, pl in self._parse(self._recv(0.7)):
            if v == VENDOR_QTIL and rf == feat and rpid == pid:
                return (pt == 2), pl
        return False, b""

    def read_all(self) -> Dict[str, object]:
        st: Dict[str, object] = {"eq_gains": [0.0] * 10}
        ok, d = self.cmd(FEAT_BASIC, 0x05)
        st["firmware"] = d.decode("utf-8", errors="replace").replace('"', "") if ok else "?"
        ok, d = self.cmd(FEAT_EARBUD, 0x00)
        st["primary"] = ("Right" if d[0] == 1 else "Left") if ok and d else "?"

        bats = {}
        ok, sup = self.cmd(FEAT_BATTERY, 0x00)
        if ok and sup:
            ok, lv = self.cmd(FEAT_BATTERY, 0x01, sup)
            if ok:
                for i in range(0, len(lv) - 1, 2):
                    bats[lv[i]] = lv[i + 1]
        st["bat_l"] = bats.get(1, -1)
        st["bat_r"] = bats.get(2, -1)
        st["bat_c"] = bats.get(3, -1)

        ok, d = self.cmd(FEAT_CUSTOM, 0x01)
        st["mode"], st["codec"] = (d[0], d[1]) if ok and len(d) >= 2 else (2, 1)
        ok, d = self.cmd(FEAT_CUSTOM, 0x03)
        st["led_mode"], st["rgb"] = (d[0], (d[1], d[2], d[3])) if ok and len(d) >= 4 else (0, (0, 255, 255))
        ok, d = self.cmd(FEAT_CUSTOM, 0x05)
        st["led_hall"] = bool(d[0]) if ok and d else False
        ok, d = self.cmd(FEAT_CUSTOM, 0x10)
        st["inear"] = bool(d[0]) if ok and d else False
        ok, d = self.cmd(FEAT_CUSTOM, 0x12)
        st["touch"] = list(d[:4]) if ok and len(d) >= 4 else [1, 4, 3, 2]

        ok, d = self.cmd(FEAT_AC, 0x00, bytes([0x01]))
        st["anc_on"] = bool(d[1]) if ok and len(d) >= 2 else False
        ok, d = self.cmd(FEAT_AC, 0x03)
        st["anc_mode"] = d[0] if ok and d else 1

        ok, d = self.cmd(FEAT_EQ, 0x02)
        st["eq_preset"] = d[0] if ok and d else 0
        ok, d = self.cmd(FEAT_EQ, 0x05, bytes([0, 9]))
        if ok and len(d) >= 72:
            gains = []
            for idx in range(10):
                off = 2 + idx * 7
                raw = struct.unpack(">h", d[off + 5 : off + 7])[0]
                gains.append(round(raw / 60.0, 1))
            st["eq_gains"] = gains
        return st


class DaoBudsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DAO Buds — Redmagic DAO TWS Controller")
        self.geometry("820x620")
        self.configure(bg="#0e0e10")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#0e0e10", foreground="#f0f0f4", fieldbackground="#1a1a22")
        style.configure("TNotebook", background="#0e0e10", borderwidth=0)
        style.configure("TNotebook.Tab", background="#1a1a22", foreground="#c8c8d4", padding=[12, 6])
        style.map("TNotebook.Tab", background=[("selected", "#00bcd4")], foreground=[("selected", "#000000")])
        style.configure("TButton", background="#23232e", foreground="#f0f0f4", padding=6)
        style.configure("Accent.TButton", background="#00bcd4", foreground="#000000", padding=6)

        self.mac_var = tk.StringVar(value=discover_dao_mac())
        self.status_var = tk.StringVar(value="Ready — click Refresh")
        self.bat_var = tk.StringVar(value="L: --%   |   R: --%   |   Case: --%")
        self.dongle_var = tk.StringVar(value="Dongle USB: checking...")

        self._build_ui()
        self.after(200, self.refresh_async)

    def _build_ui(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="DAO TWS MAC:").pack(side="left")
        ttk.Entry(top, textvariable=self.mac_var, width=20).pack(side="left", padx=6)
        ttk.Button(top, text="Refresh", command=self.refresh_async).pack(side="left", padx=4)
        ttk.Button(top, text="Battery Saver (1-Click)", style="Accent.TButton", command=self.apply_battery_saver).pack(side="right")

        info = ttk.Frame(self, padding=(12, 0, 12, 8))
        info.pack(fill="x")
        ttk.Label(info, textvariable=self.bat_var, font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Label(info, textvariable=self.dongle_var).pack(side="right")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=6)

        # Tab 1: Audio & ANC
        t_audio = ttk.Frame(nb, padding=14)
        nb.add(t_audio, text="Audio & ANC")
        self.mode_var = tk.IntVar(value=2)
        self.codec_var = tk.StringVar(value=CODEC_LABELS[1])
        self.anc_var = tk.BooleanVar(value=False)
        self.anc_mode_var = tk.IntVar(value=1)

        ttk.Label(t_audio, text="Mode:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=6)
        ttk.Radiobutton(t_audio, text="Music Mode", variable=self.mode_var, value=2).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(t_audio, text="Game Mode", variable=self.mode_var, value=1).grid(row=0, column=2, sticky="w")
        ttk.Label(t_audio, text="Codec Profile:").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(t_audio, textvariable=self.codec_var, values=CODEC_LABELS[1:], state="readonly", width=24).grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Button(t_audio, text="Apply Mode & Codec", command=self.apply_mode).grid(row=1, column=3, padx=8)

        ttk.Separator(t_audio, orient="horizontal").grid(row=2, column=0, columnspan=4, sticky="ew", pady=12)
        ttk.Checkbutton(t_audio, text="Active Noise Cancellation (ANC)", variable=self.anc_var, command=self.apply_anc_state).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(t_audio, text="ANC Mode (1-10):").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Spinbox(t_audio, from_=1, to=10, textvariable=self.anc_mode_var, width=6).grid(row=4, column=1, sticky="w")
        ttk.Button(t_audio, text="Set ANC Mode", command=self.apply_anc_mode).grid(row=4, column=2, sticky="w")

        # Tab 2: Touch Controls
        t_touch = ttk.Frame(nb, padding=14)
        nb.add(t_touch, text="Touch Remap")
        self.touch_vars = [tk.StringVar(value=TOUCH_LABELS[1]) for _ in range(4)]
        labels = ["Left Double-Tap", "Left Triple-Tap", "Right Double-Tap", "Right Triple-Tap"]
        for i, lbl in enumerate(labels):
            ttk.Label(t_touch, text=lbl).grid(row=i, column=0, sticky="w", pady=8, padx=6)
            ttk.Combobox(t_touch, textvariable=self.touch_vars[i], values=TOUCH_LABELS, state="readonly", width=22).grid(row=i, column=1, pady=8)
        ttk.Button(t_touch, text="Save Touch Mapping", style="Accent.TButton", command=self.apply_touch).grid(row=4, column=1, pady=14, sticky="e")

        # Tab 3: 10-Band EQ
        t_eq = ttk.Frame(nb, padding=14)
        nb.add(t_eq, text="10-Band EQ")
        eq_top = ttk.Frame(t_eq)
        eq_top.pack(fill="x", pady=(0, 10))
        self.preset_var = tk.StringVar(value="0")
        ttk.Label(eq_top, text="Preset:").pack(side="left")
        ttk.Combobox(eq_top, textvariable=self.preset_var, values=[str(i) for i in range(10)] + ["User"], state="readonly", width=10).pack(side="left", padx=6)
        ttk.Button(eq_top, text="Apply Preset", command=self.apply_eq_preset).pack(side="left", padx=4)
        ttk.Button(eq_top, text="Reset Flat (0 dB)", command=self.reset_eq_flat).pack(side="right")

        sliders = ttk.Frame(t_eq)
        sliders.pack(fill="both", expand=True)
        self.eq_scales: List[tk.Scale] = []
        for idx, hz in enumerate(EQ_FREQS):
            col = ttk.Frame(sliders)
            col.pack(side="left", expand=True, fill="y")
            sc = tk.Scale(col, from_=12, to=-12, resolution=0.5, orient="vertical", length=200, bg="#16161c", fg="#f0f0f4", highlightthickness=0)
            sc.pack()
            sc.bind("<ButtonRelease-1>", lambda _e, b=idx, s=sc: self.apply_eq_band(b, s.get()))
            self.eq_scales.append(sc)
            ttk.Label(col, text=f"{hz//1000}k" if hz >= 1000 else str(hz)).pack()

        # Tab 4: Hardware & Stability
        t_hw = ttk.Frame(nb, padding=14)
        nb.add(t_hw, text="Hardware & Stability")
        self.led_var = tk.StringVar(value=LED_LABELS[0])
        self.hall_var = tk.BooleanVar(value=False)
        self.inear_var = tk.BooleanVar(value=False)

        ttk.Label(t_hw, text="LED Effect:").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(t_hw, textvariable=self.led_var, values=LED_LABELS, state="readonly", width=16).grid(row=0, column=1, sticky="w")
        ttk.Button(t_hw, text="Apply LED", command=self.apply_led).grid(row=0, column=2, padx=8)
        ttk.Checkbutton(t_hw, text="Case Hall LED", variable=self.hall_var, command=self.apply_hall).grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Checkbutton(t_hw, text="In-Ear Wear Detection (disable to stop false pauses)", variable=self.inear_var, command=self.apply_inear).grid(row=2, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Label(t_hw, text="Bluetooth Multipoint:").grid(row=3, column=0, sticky="w", pady=10)
        ttk.Button(t_hw, text="Single-Point (Recommended)", command=lambda: self.apply_multipoint(False)).grid(row=3, column=1, sticky="w")
        ttk.Button(t_hw, text="Multipoint ON", command=lambda: self.apply_multipoint(True)).grid(row=3, column=2, sticky="w")

        ttk.Label(self, textvariable=self.status_var, padding=(12, 6)).pack(fill="x", side="bottom")

    def _run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def refresh_async(self):
        mac = self.mac_var.get().strip()
        self.status_var.set("Querying device...")

        def work():
            dongle = detect_dongle_present()
            self.after(0, lambda: self.dongle_var.set("Dongle USB (19d2:0616): CONNECTED" if dongle else "Dongle USB: not detected"))
            if not mac:
                self.after(0, lambda: self.status_var.set("No Bluetooth MAC found — pair DAO TWS or enter MAC manually"))
                return
            try:
                with GaiaClient(mac) as c:
                    st = c.read_all()
                self.after(0, lambda: self._apply_state(st))
            except Exception as e:
                self.after(0, lambda: self.status_var.set(f"Bluetooth error: {e}"))

        self._run_bg(work)

    def _apply_state(self, st: Dict[str, object]):
        bl, br, bc = st["bat_l"], st["bat_r"], st["bat_c"]
        self.bat_var.set(f"L: {bl if bl >= 0 else '--'}%   |   R: {br if br >= 0 else '--'}%   |   Case: {bc if bc >= 0 else '--'}%   ({st['primary']})")
        self.mode_var.set(int(st["mode"]))
        cidx = max(1, min(3, int(st["codec"])))
        self.codec_var.set(CODEC_LABELS[cidx])
        self.anc_var.set(bool(st["anc_on"]))
        self.anc_mode_var.set(int(st["anc_mode"]))
        for i, v in enumerate(st["touch"]):
            self.touch_vars[i].set(TOUCH_LABELS[max(0, min(5, int(v)))])
        p = int(st["eq_preset"])
        self.preset_var.set("User" if p == 0x3F else str(p))
        for i, g in enumerate(st["eq_gains"]):
            self.eq_scales[i].set(g)
        self.led_var.set(LED_LABELS[max(0, min(3, int(st["led_mode"])))])
        self.hall_var.set(bool(st["led_hall"]))
        self.inear_var.set(bool(st["inear"]))
        self.status_var.set(f"Connected — Firmware {st['firmware']}")

    def _send(self, feat: int, pid: int, payload: bytes, label: str):
        mac = self.mac_var.get().strip()
        if not mac:
            messagebox.showwarning("DAO Buds", "Enter or pair your DAO TWS Bluetooth MAC first.")
            return

        def work():
            try:
                with GaiaClient(mac) as c:
                    ok, _ = c.cmd(feat, pid, payload)
                self.after(0, lambda: self.status_var.set(f"{label}: {'OK' if ok else 'REJECTED'}"))
                if ok:
                    self.after(200, self.refresh_async)
            except Exception as e:
                self.after(0, lambda: self.status_var.set(f"Error: {e}"))

        self._run_bg(work)

    def apply_mode(self):
        m = self.mode_var.get()
        c = 0 if m == 1 else CODEC_LABELS.index(self.codec_var.get())
        self._send(FEAT_CUSTOM, 0x02, bytes([m, c]), "Mode/Codec")

    def apply_anc_state(self):
        self._send(FEAT_AC, 0x01, bytes([0x01, 1 if self.anc_var.get() else 0]), "ANC")

    def apply_anc_mode(self):
        self._send(FEAT_AC, 0x04, bytes([int(self.anc_mode_var.get())]), "ANC Mode")

    def apply_touch(self):
        vals = [TOUCH_LABELS.index(v.get()) for v in self.touch_vars]
        self._send(FEAT_CUSTOM, 0x13, bytes(vals), "Touch Controls")

    def apply_eq_preset(self):
        p = 0x3F if self.preset_var.get() == "User" else int(self.preset_var.get())
        self._send(FEAT_EQ, 0x03, bytes([p]), "EQ Preset")

    def apply_eq_band(self, band: int, db: float):
        raw = int(round(max(-12.0, min(12.0, db)) * 60.0))
        self._send(FEAT_EQ, 0x06, struct.pack(">BBh", band, band, raw), f"EQ Band {band}")

    def reset_eq_flat(self):
        self._send(FEAT_EQ, 0x06, bytes([0, 9]) + bytes(20), "EQ Flat")

    def apply_led(self):
        idx = LED_LABELS.index(self.led_var.get())
        pl = bytes([1, 0, 0, 0]) if idx == 0 else bytes([idx, 0, 255, 255])
        self._send(FEAT_CUSTOM, 0x04, pl, "LED")

    def apply_hall(self):
        self._send(FEAT_CUSTOM, 0x06, bytes([1 if self.hall_var.get() else 0]), "Hall LED")

    def apply_inear(self):
        self._send(FEAT_CUSTOM, 0x11, bytes([1 if self.inear_var.get() else 0]), "In-Ear")

    def apply_multipoint(self, enabled: bool):
        self._send(FEAT_HANDSET, 0x00, bytes([1 if enabled else 0]), "Multipoint")

    def apply_battery_saver(self):
        mac = self.mac_var.get().strip()
        if not mac:
            return

        def work():
            try:
                with GaiaClient(mac) as c:
                    c.cmd(FEAT_CUSTOM, 0x04, bytes([1, 0, 0, 0]))
                    c.cmd(FEAT_CUSTOM, 0x06, bytes([0]))
                    c.cmd(FEAT_CUSTOM, 0x11, bytes([0]))
                    c.cmd(FEAT_HANDSET, 0x00, bytes([0]))
                    c.cmd(FEAT_CUSTOM, 0x02, bytes([2, 1]))
                self.after(0, lambda: self.status_var.set("Battery Saver & Stability applied!"))
                self.after(200, self.refresh_async)
            except Exception as e:
                self.after(0, lambda: self.status_var.set(f"Error: {e}"))

        self._run_bg(work)


if __name__ == "__main__":
    DaoBudsApp().mainloop()
