#!/usr/bin/env python3
"""daotws — Open-source controller for Redmagic Cyberbuds DAO TWS (BH4010).

Supports:
  - Bluetooth Classic RFCOMM Channel 11: Qualcomm GAIA v3 (0x001D) + Redmagic Custom (0x0E)
  - Live Radio Telemetry (Feature 0x0C STATISTICS: RSSI/SNR/codec/link diagnostics)
  - Mimi Sound DSP (Feature 0x0E PDU 0x14-0x1D)
  - Offline read-only APPUHDR5 firmware package validator (inspect-fw)
  - USB Dongle QCC3086 (19d2:0616): safe sysfs detection & read-only qc-s5gen2 version query
Zero external dependencies (Python 3 stdlib only).
"""

import argparse
try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]
import glob
import hashlib
import json
import os
import re
import select
import socket
import struct
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_CHANNEL = 11
VENDOR_QTIL = 0x001D

FEAT_BASIC = 0x00
FEAT_EARBUD = 0x01
FEAT_MUSIC_EQ = 0x05
FEAT_HANDSET = 0x07
FEAT_AUDIO_CURATION = 0x08
FEAT_STATS = 0x0C
FEAT_BATTERY = 0x0D
FEAT_CUSTOM = 0x0E

TOUCH_ACTIONS = {
    "off": 0,
    "play": 1,
    "prev": 2,
    "next": 3,
    "anc": 4,
    "game": 5,
}
TOUCH_NAMES = {v: k for k, v in TOUCH_ACTIONS.items()}

MODE_TYPES = {"game": 1, "music": 2}
MODE_NAMES = {v: k for k, v in MODE_TYPES.items()}

CODEC_MODES = {"empty": 0, "normal": 1, "lhdc": 2, "aptx-lossless": 3}
CODEC_NAMES = {v: k for k, v in CODEC_MODES.items()}

LIGHT_MODES = {"off": 0, "static": 1, "breath": 2, "rainbow": 3}
LIGHT_NAMES = {v: k for k, v in LIGHT_MODES.items()}

BAT_NAMES = {0: "single", 1: "left", 2: "right", 3: "case"}

STAT_CATEGORY_NAMES = {
    0x0001: "streaming",
    0x0002: "spatial_audio",
}

STREAMING_CODEC_NAMES = {
    0: "None",
    1: "SBC",
    2: "AAC",
    3: "aptX",
    4: "aptX HD",
    5: "aptX Adaptive",
    6: "aptX Lossless",
    7: "LHDC / Vendor",
    8: "LC3",
}

TRANSPORT_NAMES = {
    0: "None",
    1: "BR/EDR",
    2: "LE",
}

# Qualcomm GAIA v3 Category 0x0001 (Streaming / Radio Link) Statistic IDs
STREAMING_STAT_DEFS: Dict[int, Tuple[str, str]] = {
    0x01: ("codec_type", "codec"),
    0x02: ("lossless_enabled", "bool"),
    0x03: ("bitrate", "u32_bitrate"),
    0x04: ("primary_rssi_dbm", "signed"),
    0x05: ("primary_link_quality", "uint"),
    0x06: ("transport_type", "transport"),
    0x07: ("audio_format", "uint"),
    0x08: ("primary_snr_db", "signed"),
    0x09: ("secondary_rssi_dbm", "signed"),
    0x0A: ("secondary_link_quality", "uint"),
    0x0B: ("primary_tx_power_dbm", "signed"),
    0x0C: ("secondary_snr_db", "signed"),
}


def decode_stat_value(cat_id: int, stat_id: int, raw: bytes) -> Dict[str, Any]:
    """Decode a GAIA v3 Feature 0x0C statistic value while always preserving raw hex."""
    name = f"stat_0x{stat_id:02x}"
    kind = "raw"
    if cat_id == 0x0001 and stat_id in STREAMING_STAT_DEFS:
        name, kind = STREAMING_STAT_DEFS[stat_id]

    val: Any = raw.hex()
    unit = ""

    def _u_le(b: bytes) -> int:
        return int.from_bytes(b, "little", signed=False)

    def _s_le(b: bytes) -> int:
        return int.from_bytes(b, "little", signed=True)

    if len(raw) > 0:
        if kind == "codec":
            c = raw[0]
            val = STREAMING_CODEC_NAMES.get(c, f"0x{c:02x}")
        elif kind == "bool":
            val = bool(raw[0])
        elif kind == "transport":
            t = raw[0]
            val = TRANSPORT_NAMES.get(t, f"0x{t:02x}")
        elif kind == "signed" and len(raw) in (1, 2, 4):
            val = _s_le(raw)
            if "dbm" in name:
                unit = "dBm"
            elif "db" in name:
                unit = "dB"
        elif kind == "u32_bitrate" and len(raw) in (2, 4):
            bps = _u_le(raw)
            if bps > 10000:
                val = round(bps / 1000.0, 1)
                unit = "kbps"
            else:
                val = bps
                unit = "kbps"
        elif kind == "uint" and len(raw) in (1, 2, 4):
            val = _u_le(raw)
        elif len(raw) in (1, 2, 4):
            val = _u_le(raw)

    out: Dict[str, Any] = {"id": stat_id, "name": name, "value": val, "raw_hex": raw.hex()}
    if unit:
        out["unit"] = unit
    return out


def parse_statistics_category_response(payload: bytes) -> Tuple[bool, int, List[Tuple[int, bytes]]]:
    """Parse Feature 0x0C PDU 0x01 (GET_ALL_STATISTICS_IN_CATEGORY) response payload."""
    if len(payload) < 3:
        return False, 0, []
    more = payload[0] != 0
    cat_id = struct.unpack_from(">H", payload, 1)[0]
    items: List[Tuple[int, bytes]] = []
    pos = 3
    while pos + 2 <= len(payload):
        sid = payload[pos]
        vlen = payload[pos + 1]
        pos += 2
        if pos + vlen > len(payload):
            break
        items.append((sid, payload[pos : pos + vlen]))
        pos += vlen
    return more, cat_id, items


def _load_fw_inspect():
    """Import sibling or installed fw_inspect module without external dependencies."""
    search_dirs = [
        os.path.dirname(os.path.realpath(__file__)),
        os.path.join(os.path.expanduser("~"), ".local", "lib", "daotws"),
    ]
    for d in search_dirs:
        if os.path.isfile(os.path.join(d, "fw_inspect.py")) and d not in sys.path:
            sys.path.insert(0, d)
    import fw_inspect  # type: ignore

    return fw_inspect


def find_dao_mac() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["bluetoothctl", "devices"], text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            if "DAO TWS" in line.upper():
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]
    except Exception:
        pass
    return None


def is_bt_connected(mac: str) -> bool:
    try:
        out = subprocess.check_output(
            ["bluetoothctl", "info", mac], text=True, stderr=subprocess.DEVNULL
        )
        return "Connected: yes" in out
    except Exception:
        return False


def get_bluez_rssi(mac: str) -> Optional[int]:
    try:
        out = subprocess.check_output(
            ["bluetoothctl", "info", mac], text=True, stderr=subprocess.DEVNULL
        )
        m = re.search(r"RSSI:\s*0x[0-9a-fA-F]+\s*\((-?\d+)\)", out)
        if m:
            return int(m.group(1))
        m2 = re.search(r"RSSI:\s*(-?\d+)", out)
        if m2:
            return int(m2.group(1))
    except Exception:
        pass
    return None


def get_dongle_status(query_hid_fw: bool = False) -> Dict[str, object]:
    """Detect QCC3086 USB dongle (19d2:0616) safely via sysfs; optionally query qc-s5gen2 HID."""
    info: Dict[str, object] = {"connected": False}
    hidraw_path = None
    for syspath in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = os.path.join(syspath, "device", "uevent")
        if not os.path.exists(uevent):
            continue
        try:
            txt = open(uevent, "r", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if "000019D2:00000616" in txt.upper():
            info["connected"] = True
            for line in txt.splitlines():
                if line.startswith("HID_UNIQ="):
                    info["serial"] = line.split("=", 1)[1].strip()
            if "/input1" in txt:
                hidraw_path = "/dev/" + os.path.basename(syspath)
                info["hidraw"] = hidraw_path

    if info["connected"]:
        for usbpath in sorted(glob.glob("/sys/bus/usb/devices/*")):
            try:
                vid = open(os.path.join(usbpath, "idVendor")).read().strip().lower()
                pid = open(os.path.join(usbpath, "idProduct")).read().strip().lower()
                if vid == "19d2" and pid == "0616":
                    bcd = open(os.path.join(usbpath, "bcdDevice")).read().strip()
                    if len(bcd) == 4:
                        info["usb_bcd"] = f"{bcd[:2]}.{bcd[2:]}"
                    break
            except OSError:
                continue

    if not query_hid_fw or not hidraw_path or fcntl is None:
        return info

    # Read-only qc-s5gen2 HostVersionReq (0x19)
    try:
        fd = os.open(hidraw_path, os.O_RDWR | os.O_NONBLOCK)
    except PermissionError:
        info["permission_error"] = True
        return info
    except OSError as e:
        info["error"] = str(e)
        return info

    def _sfeature(payload: bytes) -> None:
        buf = bytearray(63)
        buf[0] = 0x03
        buf[1] = len(payload)
        buf[2 : 2 + len(payload)] = payload
        ioctl_num = (3 << 30) | (len(buf) << 16) | (ord("H") << 8) | 0x06
        fcntl.ioctl(fd, ioctl_num, buf)

    def _wdata(payload: bytes) -> None:
        buf = bytearray(255)
        buf[0] = 0x05
        buf[1] = len(payload)
        buf[2 : 2 + len(payload)] = payload
        os.write(fd, bytes(buf))

    def _rresp(timeout: float = 0.6) -> bytes:
        r, _, _ = select.select([fd], [], [], timeout)
        return os.read(fd, 512) if r else b""

    try:
        _sfeature(bytes([0x02, 0x00, 0x00]))  # Connect
        _rresp(0.6)
        _wdata(bytes([0x19, 0x00, 0x00]))  # HostVersionReq
        vresp = _rresp(0.6)
        if len(vresp) >= 11 and vresp[0] == 0x06 and vresp[2] == 0x1A:
            _, major, minor, cfg = struct.unpack(">HHHH", vresp[3:11])
            info["firmware"] = f"{major}.{minor} (cfg {cfg})"
    except OSError as e:
        info["error"] = str(e)
    finally:
        try:
            _sfeature(bytes([0x07, 0x00, 0x00]))  # Disconnect
            _rresp(0.2)
        except OSError:
            pass
        os.close(fd)
    return info


class DaoTwsClient:
    def __init__(self, mac: str, channel: int = DEFAULT_CHANNEL, timeout: float = 4.0):
        self.mac = mac
        self.channel = channel
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def __enter__(self) -> "DaoTwsClient":
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    def connect(self) -> None:
        self.sock = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        )
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.mac, self.channel))
        self._recv_some(0.35)

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _recv_some(self, timeout: float = 0.8) -> bytes:
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
    def _parse_frames(buf: bytes) -> List[Tuple[int, int, int, int, bytes]]:
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
            frames.append(
                (vendor, (pdu >> 9) & 0x7F, (pdu >> 7) & 0x03, pdu & 0x7F, buf[i + 8 : i + 8 + plen])
            )
            i = end
        return frames

    def command(self, feat: int, pdu_id: int, payload: bytes = b"") -> Tuple[bool, bytes]:
        assert self.sock is not None
        pdu = ((feat & 0x7F) << 9) | (0 << 7) | (pdu_id & 0x7F)
        frame = struct.pack(">BBBBHH", 0xFF, 0x03, 0x00, len(payload), VENDOR_QTIL, pdu) + payload
        self.sock.send(frame)
        rx = self._recv_some(0.8)
        for vendor, rf, pt, pid, pl in self._parse_frames(rx):
            if vendor == VENDOR_QTIL and rf == feat and pid == pdu_id:
                if pt == 2:
                    return True, pl
                if pt == 3:
                    return False, pl
        return False, b""

    def get_version(self) -> str:
        ok, d = self.command(FEAT_BASIC, 0x05)
        return d.decode("utf-8", errors="replace").replace('"', "") if ok else "unknown"

    def get_primary(self) -> str:
        ok, d = self.command(FEAT_EARBUD, 0x00)
        return ("right" if d[0] == 1 else "left") if ok and d else "unknown"

    def get_batteries(self) -> Dict[str, int]:
        ok, sup = self.command(FEAT_BATTERY, 0x00)
        if not ok or not sup:
            return {}
        ok, lvls = self.command(FEAT_BATTERY, 0x01, sup)
        if not ok:
            return {}
        return {
            BAT_NAMES.get(lvls[i], str(lvls[i])): lvls[i + 1]
            for i in range(0, len(lvls) - 1, 2)
        }

    def get_mode(self) -> Tuple[str, str]:
        ok, d = self.command(FEAT_CUSTOM, 0x01)
        if not ok or len(d) < 2:
            return "unknown", "unknown"
        return MODE_NAMES.get(d[0], str(d[0])), CODEC_NAMES.get(d[1], str(d[1]))

    def get_led(self) -> Dict[str, object]:
        res: Dict[str, object] = {}
        ok, d = self.command(FEAT_CUSTOM, 0x03)
        if ok and len(d) >= 4:
            res["mode"] = LIGHT_NAMES.get(d[0], str(d[0]))
            res["rgb"] = [d[1], d[2], d[3]]
        ok, d = self.command(FEAT_CUSTOM, 0x05)
        if ok and d:
            res["hall"] = bool(d[0])
        ok, d = self.command(FEAT_CUSTOM, 0x07)
        if ok and d:
            res["speed"] = d[0]
        ok, d = self.command(FEAT_CUSTOM, 0x09)
        if ok and d:
            res["brightness"] = d[0]
        return res

    def get_inear(self) -> Optional[bool]:
        ok, d = self.command(FEAT_CUSTOM, 0x10)
        return bool(d[0]) if ok and d else None

    def get_language(self) -> Optional[int]:
        ok, d = self.command(FEAT_CUSTOM, 0x0E)
        return d[0] if ok and d else None

    def get_touch(self) -> Dict[str, str]:
        ok, d = self.command(FEAT_CUSTOM, 0x12)
        if not ok or len(d) < 4:
            return {}
        return {
            "left_double": TOUCH_NAMES.get(d[0], str(d[0])),
            "left_triple": TOUCH_NAMES.get(d[1], str(d[1])),
            "right_double": TOUCH_NAMES.get(d[2], str(d[2])),
            "right_triple": TOUCH_NAMES.get(d[3], str(d[3])),
        }

    def get_mimi(self) -> Dict[str, Any]:
        """Read Mimi Sound DSP state (Feature 0x0E PDU 0x14, 0x16, 0x19, 0x1B)."""
        res: Dict[str, Any] = {"supported": False}
        ok_en, d_en = self.command(FEAT_CUSTOM, 0x14)
        if ok_en and d_en:
            res["supported"] = True
            res["enabled"] = bool(d_en[0])
        elif not ok_en and d_en:
            res["error_code"] = d_en[0]

        ok_int, d_int = self.command(FEAT_CUSTOM, 0x16)
        if ok_int and d_int:
            res["supported"] = True
            res["intensity"] = d_int[0]

        ok_pid, d_pid = self.command(FEAT_CUSTOM, 0x19)
        if ok_pid and d_pid:
            res["supported"] = True
            res["preset_id"] = d_pid.hex()

        ok_tl, d_tl = self.command(FEAT_CUSTOM, 0x1B)
        if ok_tl and d_tl:
            res["supported"] = True
            res["tech_level"] = d_tl[0] if len(d_tl) == 1 else d_tl.hex()

        return res

    def get_statistics(self) -> Dict[str, Any]:
        """Query Feature 0x0C STATISTICS categories & live radio/codec/link metrics."""
        categories: List[int] = []
        last_cat = 0
        for _ in range(16):
            ok, d = self.command(FEAT_STATS, 0x00, struct.pack(">H", last_cat))
            if not ok or len(d) < 1:
                break
            more = d[0] != 0
            page_cats = [struct.unpack_from(">H", d, i)[0] for i in range(1, len(d) - 1, 2)]
            for c in page_cats:
                if c not in categories:
                    categories.append(c)
            if not more or not page_cats or page_cats[-1] == last_cat:
                break
            last_cat = page_cats[-1]

        cat_results: Dict[str, Any] = {}
        summary: Dict[str, Any] = {}
        for cat in categories:
            cat_name = STAT_CATEGORY_NAMES.get(cat, f"cat_0x{cat:04x}")
            entries: List[Dict[str, Any]] = []
            seen_ids = set()
            last_sid = 0
            for _ in range(32):
                ok, d = self.command(FEAT_STATS, 0x01, struct.pack(">HB", cat, last_sid))
                if not ok or len(d) < 3:
                    break
                more, _rcat, raw_items = parse_statistics_category_response(d)
                if not raw_items:
                    break
                progressed = False
                for sid, val_bytes in raw_items:
                    if sid not in seen_ids:
                        seen_ids.add(sid)
                        decoded = decode_stat_value(cat, sid, val_bytes)
                        entries.append(decoded)
                        if cat == 0x0001:
                            summary[decoded["name"]] = decoded["value"]
                        progressed = True
                    last_sid = sid
                if not more or not progressed:
                    break
            cat_results[f"0x{cat:04x}"] = {"name": cat_name, "stats": entries}

        bluez_rssi = get_bluez_rssi(self.mac)
        if bluez_rssi is not None:
            summary["bluez_rssi_dbm"] = bluez_rssi

        return {
            "mac": self.mac,
            "categories": [f"0x{c:04x}" for c in categories],
            "summary": summary,
            "by_category": cat_results,
        }

    def get_anc(self) -> Dict[str, object]:
        res: Dict[str, object] = {}
        ok, d = self.command(FEAT_AUDIO_CURATION, 0x00, bytes([0x01]))
        if ok and len(d) >= 2:
            res["enabled"] = bool(d[1])
        ok, d = self.command(FEAT_AUDIO_CURATION, 0x03)
        if ok and d:
            res["mode"] = d[0]
        toggles = {}
        for slot in (1, 2, 3):
            ok, d = self.command(FEAT_AUDIO_CURATION, 0x08, bytes([slot]))
            if ok and len(d) >= 2:
                toggles[f"slot{slot}"] = None if d[1] == 0xFF else d[1]
        res["toggles"] = toggles
        return res

    def get_eq(self) -> Dict[str, object]:
        res: Dict[str, object] = {}
        ok, d = self.command(FEAT_MUSIC_EQ, 0x00)
        if ok and d:
            res["enabled"] = bool(d[0])
        ok, d = self.command(FEAT_MUSIC_EQ, 0x02)
        if ok and d:
            res["preset"] = "user" if d[0] == 0x3F else d[0]
        ok, d = self.command(FEAT_MUSIC_EQ, 0x05, bytes([0, 9]))
        if ok and len(d) >= 72:
            bands = []
            for idx in range(10):
                off = 2 + idx * 7
                freq = struct.unpack(">H", d[off : off + 2])[0]
                gain_raw = struct.unpack(">h", d[off + 5 : off + 7])[0]
                bands.append({"band": idx, "hz": freq, "db": round(gain_raw / 60.0, 2)})
            res["bands"] = bands
        return res

    def status(self, include_stats: bool = False) -> Dict[str, object]:
        mode, codec = self.get_mode()
        bat = self.get_batteries()
        alerts = []
        l_bat = bat.get("left")
        r_bat = bat.get("right")
        if l_bat is not None and r_bat is not None and abs(l_bat - r_bat) >= 20:
            alerts.append(f"Battery imbalance L={l_bat}% vs R={r_bat}%")
        if (l_bat is None) != (r_bat is None):
            alerts.append("Only one earbud connected (check case/pogo pins)")
        out: Dict[str, object] = {
            "bt_connected": True,
            "mac": self.mac,
            "firmware": self.get_version(),
            "primary": self.get_primary(),
            "battery": bat,
            "mode": mode,
            "codec_profile": codec,
            "anc": self.get_anc(),
            "led": self.get_led(),
            "in_ear_detection": self.get_inear(),
            "language": self.get_language(),
            "touch": self.get_touch(),
            "eq": self.get_eq(),
            "mimi": self.get_mimi(),
            "alerts": alerts,
        }
        if include_stats:
            out["statistics"] = self.get_statistics()
        return out

    def set_touch(self, ld: int, lt: int, rd: int, rt: int) -> bool:
        return self.command(FEAT_CUSTOM, 0x13, bytes([ld, lt, rd, rt]))[0]

    def set_mode(self, mode_type: int, music_type: int) -> bool:
        return self.command(FEAT_CUSTOM, 0x02, bytes([mode_type, music_type]))[0]

    def set_led_mode(self, mode: int, r: int, g: int, b: int) -> bool:
        return self.command(FEAT_CUSTOM, 0x04, bytes([mode, r, g, b]))[0]

    def set_led_hall(self, enabled: bool) -> bool:
        return self.command(FEAT_CUSTOM, 0x06, bytes([1 if enabled else 0]))[0]

    def set_led_speed(self, speed: int) -> bool:
        return self.command(FEAT_CUSTOM, 0x08, bytes([speed & 0xFF]))[0]

    def set_led_brightness(self, strength: int) -> bool:
        return self.command(FEAT_CUSTOM, 0x0A, bytes([strength & 0xFF]))[0]

    def set_inear(self, enabled: bool) -> bool:
        return self.command(FEAT_CUSTOM, 0x11, bytes([1 if enabled else 0]))[0]

    def set_language(self, lang: int) -> bool:
        return self.command(FEAT_CUSTOM, 0x0F, bytes([lang & 0xFF]))[0]

    def set_multipoint(self, enabled: bool) -> bool:
        return self.command(FEAT_HANDSET, 0x00, bytes([1 if enabled else 0]))[0]

    def set_anc_state(self, enabled: bool) -> bool:
        return self.command(FEAT_AUDIO_CURATION, 0x01, bytes([0x01, 1 if enabled else 0]))[0]

    def set_anc_mode(self, mode: int) -> bool:
        return self.command(FEAT_AUDIO_CURATION, 0x04, bytes([mode & 0xFF]))[0]

    def set_anc_toggle(self, slot: int, mode_or_none: Optional[int]) -> bool:
        val = 0xFF if mode_or_none is None else (mode_or_none & 0xFF)
        return self.command(FEAT_AUDIO_CURATION, 0x09, bytes([slot & 0xFF, val]))[0]

    def set_eq_preset(self, preset: int) -> bool:
        return self.command(FEAT_MUSIC_EQ, 0x03, bytes([preset & 0xFF]))[0]

    def set_eq_band(self, band: int, gain_db: float) -> bool:
        clamped = max(-12.0, min(12.0, gain_db))
        raw = int(round(clamped * 60.0))
        return self.command(FEAT_MUSIC_EQ, 0x06, struct.pack(">BBh", band, band, raw))[0]

    def set_mimi_enable(self, enabled: bool) -> bool:
        return self.command(FEAT_CUSTOM, 0x15, bytes([1 if enabled else 0]))[0]

    def set_mimi_intensity(self, intensity: int) -> bool:
        clamped = max(0, min(100, intensity))
        return self.command(FEAT_CUSTOM, 0x17, bytes([clamped]))[0]

    def set_mimi_preset_id(self, preset_id_hex: str) -> bool:
        raw = bytes.fromhex(preset_id_hex.strip())
        if len(raw) != 16:
            raise ValueError("Mimi preset ID must be exactly 16 bytes (32 hex chars MD5)")
        return self.command(FEAT_CUSTOM, 0x1A, raw)[0]

    def set_mimi_preset_payload(self, payload: bytes) -> bool:
        ok1 = self.command(FEAT_CUSTOM, 0x18, payload)[0]
        digest = hashlib.md5(payload).digest()
        ok2 = self.command(FEAT_CUSTOM, 0x1A, digest)[0]
        return ok1 and ok2

    def clear_mimi_preset(self) -> bool:
        return self.command(FEAT_CUSTOM, 0x1D, b"")[0]


def _print_stats(stats: Dict[str, Any]) -> None:
    print(f"DAO TWS Live Radio Telemetry ({stats['mac']}) — Feature 0x0C STATISTICS")
    cats = stats.get("categories", [])
    print(f"  Categories : {', '.join(cats) if cats else 'none'}")
    by_cat = stats.get("by_category", {})
    for cid, cdata in by_cat.items():
        print(f"  [{cid} — {cdata['name']}]")
        if not cdata["stats"]:
            print("    (no active streaming metrics — start audio playback on BT)")
        for s in cdata["stats"]:
            unit = f" {s['unit']}" if "unit" in s else ""
            print(f"    0x{s['id']:02x} {s['name']:<24}: {s['value']}{unit}  (raw={s['raw_hex']})")
    if "bluez_rssi_dbm" in stats.get("summary", {}):
        print(f"  BlueZ RSSI : {stats['summary']['bluez_rssi_dbm']} dBm")


def main():
    parser = argparse.ArgumentParser(description="Redmagic DAO TWS (BH4010) CLI controller")
    parser.add_argument("--mac", help="Bluetooth MAC address (auto-detected if omitted)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_st = sub.add_parser("status", help="Show full earbuds + USB dongle status")
    p_st.add_argument("--json", action="store_true", help="Output JSON")
    p_st.add_argument("--stats", action="store_true", help="Also include Feature 0x0C radio statistics")

    p_stats = sub.add_parser("stats", help="Show live radio/link telemetry (Feature 0x0C STATISTICS)")
    p_stats.add_argument("--json", action="store_true", help="Output JSON")
    p_stats.add_argument("--watch", type=float, metavar="SEC", help="Continuously poll every SEC seconds")

    p_mimi = sub.add_parser("mimi", help="Inspect or control Mimi Sound DSP (Feature 0x0E PDU 0x14-0x1D)")
    p_mimi.add_argument("--enable", choices=["on", "off"], help="Enable or disable Mimi DSP")
    p_mimi.add_argument("--intensity", type=int, help="Set Mimi intensity (0..100)")
    p_mimi.add_argument("--preset-id", help="Set 16-byte MD5 preset ID (32 hex chars)")
    p_mimi.add_argument("--clear", action="store_true", help="Clear stored Mimi preset")
    p_mimi.add_argument("--json", action="store_true", help="Output JSON")

    p_fw = sub.add_parser("inspect-fw", help="Offline read-only APPUHDR5 firmware validator (no flashing)")
    p_fw.add_argument("file", help="Path to Qualcomm APPUHDR5 .bin firmware file")
    p_fw.add_argument("--json", action="store_true", help="Output JSON")

    p_touch = sub.add_parser("touch", help="Remap double/triple tap touch controls")
    acts = list(TOUCH_ACTIONS.keys())
    p_touch.add_argument("--ld", choices=acts, help="Left double-tap")
    p_touch.add_argument("--lt", choices=acts, help="Left triple-tap")
    p_touch.add_argument("--rd", choices=acts, help="Right double-tap")
    p_touch.add_argument("--rt", choices=acts, help="Right triple-tap")

    p_mode = sub.add_parser("mode", help="Set Game/Music mode and codec profile")
    p_mode.add_argument("mode", choices=["game", "music"])
    p_mode.add_argument("--codec", choices=["normal", "lhdc", "aptx-lossless"], default="normal")

    p_anc = sub.add_parser("anc", help="Control ANC/Ambient mode and touch toggle slots")
    p_anc.add_argument("--state", choices=["on", "off"])
    p_anc.add_argument("--mode", type=int, help="ANC mode ID (1..10)")
    p_anc.add_argument("--slot", type=int, choices=[1, 2, 3])
    p_anc.add_argument("--slot-mode", help="Mode ID (1..10) or 'off'")

    p_eq = sub.add_parser("eq", help="Control EQ presets and 10-band parametric EQ")
    p_eq.add_argument("--preset", help="Preset 0..9 or 'user'")
    p_eq.add_argument("--band", type=int, choices=range(10))
    p_eq.add_argument("--db", type=float)

    p_led = sub.add_parser("led", help="Control RGB LEDs")
    p_led.add_argument("effect", nargs="?", choices=["off", "static", "breath", "rainbow"])
    p_led.add_argument("--rgb", nargs=3, type=int, metavar=("R", "G", "B"), default=[0, 255, 255])
    p_led.add_argument("--hall", choices=["on", "off"])
    p_led.add_argument("--speed", type=int)
    p_led.add_argument("--brightness", type=int)

    p_inear = sub.add_parser("inear", help="Toggle in-ear wear detection")
    p_inear.add_argument("state", choices=["on", "off"])

    p_lang = sub.add_parser("language", help="Set voice prompt language (0=ZH, 1=EN)")
    p_lang.add_argument("lang", type=int)

    p_mp = sub.add_parser("multipoint", help="Toggle Bluetooth Multipoint")
    p_mp.add_argument("state", choices=["on", "off"])

    sub.add_parser("battery-saver", help="Disable LEDs, Hall, In-Ear, Multipoint")

    args = parser.parse_args()

    # Offline command — does not require Bluetooth or USB hardware
    if args.cmd == "inspect-fw":
        fw_mod = _load_fw_inspect()
        try:
            info = fw_mod.inspect_firmware_file(args.file)
        except OSError as e:
            print(f"Error reading {args.file}: {e}", file=sys.stderr)
            sys.exit(2)
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print(fw_mod.format_report(info))
        sys.exit(0 if info["valid"] else 1)

    dongle = get_dongle_status()
    mac = args.mac or find_dao_mac()

    if args.cmd == "status":
        st: Dict[str, object] = {"bt_connected": False, "dongle": dongle}
        if mac and is_bt_connected(mac):
            try:
                with DaoTwsClient(mac) as dev:
                    st = dev.status(include_stats=args.stats)
                    st["dongle"] = dongle
            except OSError as e:
                st["bt_error"] = str(e)
        if args.json:
            print(json.dumps(st, indent=2))
            return
        if st.get("bt_connected"):
            bat = st["battery"]
            print(f"DAO TWS ({st['mac']})  FW: {st['firmware']}  Primary: {str(st['primary']).upper()}")
            print(f"  Battery : L={bat.get('left', '?')}%  R={bat.get('right', '?')}%  Case={bat.get('case', '?')}%")
            print(f"  Mode    : {st['mode']} / codec={st['codec_profile']}")
            anc = st["anc"]
            print(f"  ANC     : enabled={anc.get('enabled')} mode={anc.get('mode')} toggles={anc.get('toggles')}")
            led = st["led"]
            print(f"  LED     : mode={led.get('mode')} rgb={led.get('rgb')} hall={led.get('hall')} speed={led.get('speed')} bright={led.get('brightness')}")
            print(f"  In-Ear  : {st['in_ear_detection']}   Lang: {st['language']}")
            t = st["touch"]
            print(f"  Touch   : L2={t.get('left_double')}  L3={t.get('left_triple')}  R2={t.get('right_double')}  R3={t.get('right_triple')}")
            eq = st["eq"]
            print(f"  EQ      : enabled={eq.get('enabled')} preset={eq.get('preset')}")
            mimi = st.get("mimi", {})
            if isinstance(mimi, dict) and mimi.get("supported"):
                print(
                    f"  Mimi    : enabled={mimi.get('enabled')} intensity={mimi.get('intensity')} "
                    f"preset={mimi.get('preset_id', '')[:12]}"
                )
            else:
                print("  Mimi    : unsupported by firmware")
            if args.stats and "statistics" in st:
                _print_stats(st["statistics"])  # type: ignore[arg-type]
            if st.get("alerts"):
                for a in st["alerts"]:
                    print(f"  ALERT   : {a}")
        else:
            print("DAO TWS Bluetooth: disconnected" + (f" ({st['bt_error']})" if "bt_error" in st else ""))
        if dongle.get("connected"):
            print(
                f"USB Dongle (19d2:0616): CONNECTED  USB: {dongle.get('usb_bcd', '?')}  "
                f"Serial: {dongle.get('serial', '?')}"
            )
        else:
            print("USB Dongle (19d2:0616): not connected")
        return

    if not mac:
        print("Error: DAO TWS Bluetooth not found. Connect Bluetooth or pass --mac.", file=sys.stderr)
        sys.exit(1)

    with DaoTwsClient(mac) as dev:
        if args.cmd == "stats":
            while True:
                stats = dev.get_statistics()
                if args.json:
                    print(json.dumps(stats, indent=2), flush=True)
                else:
                    _print_stats(stats)
                if not args.watch:
                    break
                time.sleep(max(0.5, args.watch))
        elif args.cmd == "mimi":
            if args.enable is not None:
                print("mimi enable   :", "OK" if dev.set_mimi_enable(args.enable == "on") else "FAILED/UNSUPPORTED")
            if args.intensity is not None:
                print("mimi intensity:", "OK" if dev.set_mimi_intensity(args.intensity) else "FAILED/UNSUPPORTED")
            if args.preset_id is not None:
                try:
                    ok = dev.set_mimi_preset_id(args.preset_id)
                    print("mimi preset_id:", "OK" if ok else "FAILED/UNSUPPORTED")
                except ValueError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(2)
            if args.clear:
                print("mimi clear    :", "OK" if dev.clear_mimi_preset() else "FAILED/UNSUPPORTED")
            mimi = dev.get_mimi()
            if args.json:
                print(json.dumps(mimi, indent=2))
            else:
                if not mimi.get("supported"):
                    err = mimi.get("error_code")
                    suffix = f" (GAIA ERR 0x{err:02x})" if isinstance(err, int) else ""
                    print(f"Mimi Sound DSP: unsupported/disabled on this firmware{suffix}")
                else:
                    print(
                        f"Mimi Sound DSP: enabled={mimi.get('enabled')} intensity={mimi.get('intensity')} "
                        f"tech_level={mimi.get('tech_level')} preset_id={mimi.get('preset_id', '')}"
                    )
        elif args.cmd == "touch":
            cur = dev.get_touch()
            ld = TOUCH_ACTIONS[args.ld] if args.ld else TOUCH_ACTIONS.get(cur.get("left_double", "play"), 1)
            lt = TOUCH_ACTIONS[args.lt] if args.lt else TOUCH_ACTIONS.get(cur.get("left_triple", "anc"), 4)
            rd = TOUCH_ACTIONS[args.rd] if args.rd else TOUCH_ACTIONS.get(cur.get("right_double", "next"), 3)
            rt = TOUCH_ACTIONS[args.rt] if args.rt else TOUCH_ACTIONS.get(cur.get("right_triple", "prev"), 2)
            print("OK" if dev.set_touch(ld, lt, rd, rt) else "FAILED", dev.get_touch())
        elif args.cmd == "mode":
            m = MODE_TYPES[args.mode]
            c = 0 if args.mode == "game" else CODEC_MODES[args.codec]
            print("OK" if dev.set_mode(m, c) else "FAILED", dev.get_mode())
        elif args.cmd == "anc":
            if args.state:
                print("anc state:", "OK" if dev.set_anc_state(args.state == "on") else "FAILED")
            if args.mode is not None:
                print("anc mode:", "OK" if dev.set_anc_mode(args.mode) else "FAILED")
            if args.slot is not None and args.slot_mode is not None:
                val = None if args.slot_mode == "off" else int(args.slot_mode)
                print("anc toggle:", "OK" if dev.set_anc_toggle(args.slot, val) else "FAILED")
            print(dev.get_anc())
        elif args.cmd == "eq":
            if args.preset is not None:
                p = 0x3F if args.preset == "user" else int(args.preset)
                print("eq preset:", "OK" if dev.set_eq_preset(p) else "FAILED")
            if args.band is not None and args.db is not None:
                print("eq band:", "OK" if dev.set_eq_band(args.band, args.db) else "FAILED")
            print(dev.get_eq())
        elif args.cmd == "led":
            if args.effect == "off":
                print("led off:", "OK" if dev.set_led_mode(1, 0, 0, 0) else "FAILED")
            elif args.effect == "static":
                print("led static:", "OK" if dev.set_led_mode(1, *args.rgb) else "FAILED")
            elif args.effect == "breath":
                print("led breath:", "OK" if dev.set_led_mode(2, *args.rgb) else "FAILED")
            elif args.effect == "rainbow":
                print("led rainbow:", "OK" if dev.set_led_mode(3, 0, 0, 0) else "FAILED")
            if args.hall:
                print("led hall:", "OK" if dev.set_led_hall(args.hall == "on") else "FAILED")
            if args.speed is not None:
                print("led speed:", "OK" if dev.set_led_speed(args.speed) else "FAILED")
            if args.brightness is not None:
                print("led brightness:", "OK" if dev.set_led_brightness(args.brightness) else "FAILED")
            print(dev.get_led())
        elif args.cmd == "inear":
            print("OK" if dev.set_inear(args.state == "on") else "FAILED", dev.get_inear())
        elif args.cmd == "language":
            print("OK" if dev.set_language(args.lang) else "FAILED", dev.get_language())
        elif args.cmd == "multipoint":
            print("OK" if dev.set_multipoint(args.state == "on") else "FAILED")
        elif args.cmd == "battery-saver":
            print("LED off       :", "OK" if dev.set_led_mode(1, 0, 0, 0) else "FAILED")
            print("LightHall off :", "OK" if dev.set_led_hall(False) else "FAILED")
            print("In-Ear off    :", "OK" if dev.set_inear(False) else "FAILED")
            print("Multipoint off:", "OK" if dev.set_multipoint(False) else "FAILED")
            print("Mode normal   :", "OK" if dev.set_mode(MODE_TYPES["music"], CODEC_MODES["normal"]) else "FAILED")


if __name__ == "__main__":
    main()
