#!/usr/bin/env python3
"""Passive BLE Watchdog (Company ID 0x08CA — Nubia) for Redmagic DAO TWS (BH4010).

Passively listens to BlueZ D-Bus ManufacturerData updates (zero RFCOMM sockets opened)
and sends desktop notifications via omarchy-notification-send (fallback: notify-send) when:
  - One earbud stays awake/connected while the other is absent/in the case
  - Left/Right battery imbalance reaches >= 20% (configurable)
"""

import argparse
import json
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

NUBIA_COMPANY_ID = 0x08CA


def parse_nubia_08ca(payload: bytes) -> Optional[Dict[str, Any]]:
    """Decode Nubia 0x08CA BLE ManufacturerData advertisement payload.

    Live captured format (17 bytes, verified against GAIA RFCOMM L=49%/R=61%/Case=31%):
      01 01 <6B BR/EDR MAC> 01 06 02 00 02 <L_bat> <R_bat> <Case_bat> 00
      Battery byte: 0xFF = disconnected/absent; bit 7 (0x80) = charging flag; bits 0..6 = percentage (0..100).
    """
    if len(payload) < 16:
        return None
    if payload[0] != 0x01 or payload[1] != 0x01:
        return None

    mac = ":".join(f"{b:02X}" for b in payload[2:8])

    def _decode_bat(raw: int) -> Tuple[Optional[int], bool]:
        if raw == 0xFF:
            return None, False
        charging = bool(raw & 0x80)
        pct = raw & 0x7F
        if pct > 100:
            return None, False
        return pct, charging

    left_pct, left_chg = _decode_bat(payload[13])
    right_pct, right_chg = _decode_bat(payload[14])
    case_pct, case_chg = _decode_bat(payload[15])

    return {
        "mac": mac,
        "left": left_pct,
        "right": right_pct,
        "case": case_pct,
        "left_charging": left_chg,
        "right_charging": right_chg,
        "case_charging": case_chg,
        "raw_hex": payload.hex(),
    }


def send_notification(title: str, body: str, urgency: str = "normal") -> bool:
    """Send desktop notification preferring omarchy-notification-send, falling back to notify-send."""
    omarchy_bin = shutil.which("omarchy-notification-send")
    if omarchy_bin:
        cmd = [
            omarchy_bin,
            "--app-name",
            "DAO Buds",
            "-u",
            urgency,
            "-g",
            "󰋋",
            title,
            body,
        ]
    else:
        notify_bin = shutil.which("notify-send")
        if not notify_bin:
            print(f"[notify-fallback] {title}: {body}", file=sys.stderr, flush=True)
            return False
        cmd = [notify_bin, "-a", "DAO Buds", "-u", urgency, title, body]

    try:
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


class WatchdogEvaluator:
    """Stateful alert evaluator with debounce (stuck bud) and notification cooldown."""

    def __init__(self, imbalance_pct: int = 20, cooldown_sec: float = 900.0, stuck_delay_sec: float = 60.0):
        self.imbalance_pct = imbalance_pct
        self.cooldown_sec = cooldown_sec
        self.stuck_delay_sec = stuck_delay_sec
        self._last_sent: Dict[str, float] = {}
        self._single_bud_since: Optional[float] = None
        self._single_bud_side: Optional[str] = None

    def _can_notify(self, key: str, now: float) -> bool:
        prev = self._last_sent.get(key)
        if prev is not None and (now - prev) < self.cooldown_sec:
            return False
        self._last_sent[key] = now
        return True

    def evaluate(
        self,
        parsed: Dict[str, Any],
        bt_connected: Optional[bool] = None,
        now: Optional[float] = None,
    ) -> List[Tuple[str, str, str]]:
        """Evaluate a parsed 0x08CA packet; returns list of (key, title, body) notifications to emit."""
        ts = time.monotonic() if now is None else now
        alerts: List[Tuple[str, str, str]] = []

        left = parsed.get("left")
        right = parsed.get("right")
        case_bat = parsed.get("case")

        # 1. Single earbud awake/stuck while the other is absent/in-case
        one_missing = (left is None) != (right is None)
        if one_missing:
            active_side = "sinistro" if left is not None else "destro"
            missing_side = "destro" if left is not None else "sinistro"
            active_pct = left if left is not None else right
            if self._single_bud_since is None or self._single_bud_side != active_side:
                self._single_bud_since = ts
                self._single_bud_side = active_side
            elapsed = ts - self._single_bud_since
            # Trigger after debounce delay (or immediately if stuck_delay_sec == 0)
            if elapsed >= self.stuck_delay_sec:
                ctx = "connesso" if bt_connected else "acceso"
                case_note = f" (case {case_bat}%)" if case_bat is not None else ""
                body = (
                    f"Solo auricolare {active_side} {ctx} ({active_pct}%), "
                    f"{missing_side} assente{case_note}. Controlla i pogo-pin nel case."
                )
                if self._can_notify("single_bud", ts):
                    alerts.append(("single_bud", "DAO Buds — Auricolare bloccato", body))
        else:
            self._single_bud_since = None
            self._single_bud_side = None

        # 2. Severe Left/Right battery imbalance (>= threshold)
        if left is not None and right is not None:
            diff = abs(left - right)
            if diff >= self.imbalance_pct:
                if self._can_notify("imbalance", ts):
                    body = f"Sbilanciamento batteria {diff}%: Sinistro {left}% vs Destro {right}%."
                    alerts.append(("imbalance", "DAO Buds — Batteria sbilanciata", body))

        return alerts


def _extract_08ca_bytes(mdata: Any) -> Optional[bytes]:
    if not mdata:
        return None
    for k, v in mdata.items():
        if int(k) == NUBIA_COMPANY_ID:
            return bytes(int(b) & 0xFF for b in v)
    return None


def run_once(mac_filter: Optional[str]) -> int:
    import dbus

    bus = dbus.SystemBus()
    om = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
    objs = om.GetManagedObjects()
    found = []
    for path, ifaces in objs.items():
        dev = ifaces.get("org.bluez.Device1")
        if not dev:
            continue
        raw = _extract_08ca_bytes(dev.get("ManufacturerData"))
        if not raw:
            continue
        parsed = parse_nubia_08ca(raw)
        if not parsed:
            continue
        if mac_filter and parsed["mac"].upper() != mac_filter.upper():
            continue
        parsed["dbus_path"] = str(path)
        parsed["connected"] = bool(dev.get("Connected", False))
        found.append(parsed)
    print(json.dumps(found, indent=2))
    return 0


def run_daemon(mac_filter: Optional[str], imbalance: int, cooldown: float, stuck_delay: float) -> int:
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    evaluator = WatchdogEvaluator(
        imbalance_pct=imbalance,
        cooldown_sec=cooldown,
        stuck_delay_sec=stuck_delay,
    )
    connected_by_mac: Dict[str, bool] = {}

    def handle_device_props(path: str, props: Dict[str, Any]) -> None:
        addr = str(props.get("Address", "")).upper()
        if "Connected" in props and addr:
            connected_by_mac[addr] = bool(props["Connected"])
        raw = _extract_08ca_bytes(props.get("ManufacturerData"))
        if not raw:
            return
        parsed = parse_nubia_08ca(raw)
        if not parsed:
            return
        mac = parsed["mac"].upper()
        if mac_filter and mac != mac_filter.upper():
            return
        bt_conn = connected_by_mac.get(mac)
        if bt_conn is None and "Connected" in props:
            bt_conn = bool(props["Connected"])
        alerts = evaluator.evaluate(parsed, bt_connected=bt_conn)
        print(
            f"[0x08CA] {mac} L={parsed['left']} R={parsed['right']} C={parsed['case']} bt_conn={bt_conn}",
            flush=True,
        )
        for _key, title, body in alerts:
            print(f"[ALERT] {title}: {body}", flush=True)
            send_notification(title, body, urgency="normal")

    def scan_cached() -> bool:
        try:
            om = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
            objs = om.GetManagedObjects()
            for path, ifaces in objs.items():
                dev = ifaces.get("org.bluez.Device1")
                if dev:
                    addr = str(dev.get("Address", "")).upper()
                    if addr:
                        connected_by_mac[addr] = bool(dev.get("Connected", False))
                    if "ManufacturerData" in dev:
                        handle_device_props(str(path), dev)
        except Exception as e:
            print(f"[watchdog] BlueZ cache check error: {e}", file=sys.stderr, flush=True)
        return True

    def on_properties_changed(interface: str, changed: Dict[str, Any], _invalidated: Any, path: str = "") -> None:
        if interface != "org.bluez.Device1":
            return
        if "Connected" in changed:
            try:
                p = dbus.Interface(bus.get_object("org.bluez", path), "org.freedesktop.DBus.Properties")
                addr = str(p.Get("org.bluez.Device1", "Address")).upper()
                connected_by_mac[addr] = bool(changed["Connected"])
            except Exception:
                pass
        if "ManufacturerData" in changed:
            handle_device_props(path, changed)

    def on_interfaces_added(path: str, interfaces: Dict[str, Any]) -> None:
        dev = interfaces.get("org.bluez.Device1")
        if dev:
            handle_device_props(str(path), dev)

    bus.add_signal_receiver(
        on_properties_changed,
        dbus_interface="org.freedesktop.DBus.Properties",
        signal_name="PropertiesChanged",
        bus_name="org.bluez",
        path_keyword="path",
    )
    bus.add_signal_receiver(
        on_interfaces_added,
        dbus_interface="org.freedesktop.DBus.ObjectManager",
        signal_name="InterfacesAdded",
        bus_name="org.bluez",
    )

    print(
        f"[daobuds-ble-watchdog] Listening passively for BLE 0x08CA (imbalance>={imbalance}%, stuck>={stuck_delay}s, cooldown={cooldown}s)",
        flush=True,
    )
    scan_cached()
    GLib.timeout_add_seconds(60, scan_cached)

    loop = GLib.MainLoop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_a: loop.quit())
    loop.run()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Passive BLE 0x08CA watchdog for Redmagic Cyberbuds DAO TWS (BH4010)"
    )
    parser.add_argument("--mac", help="Only monitor this BR/EDR MAC address (optional)")
    parser.add_argument("--imbalance", type=int, default=20, help="Battery imbalance alert threshold %% (default: 20)")
    parser.add_argument("--cooldown", type=float, default=900.0, help="Seconds between repeated alerts (default: 900)")
    parser.add_argument("--stuck-delay", type=float, default=60.0, help="Seconds before single-bud stuck alert (default: 60)")
    parser.add_argument("--once", action="store_true", help="Inspect current BlueZ cached 0x08CA data once and exit")
    parser.add_argument("--parse-hex", help="Decode a raw 0x08CA ManufacturerData hex payload offline and exit")
    args = parser.parse_args()

    if args.parse_hex:
        raw = bytes.fromhex(args.parse_hex.replace(" ", ""))
        parsed = parse_nubia_08ca(raw)
        if not parsed:
            print("Invalid Nubia 0x08CA payload", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(parsed, indent=2))
        sys.exit(0)

    if args.once:
        sys.exit(run_once(args.mac))

    sys.exit(run_daemon(args.mac, args.imbalance, args.cooldown, args.stuck_delay))


if __name__ == "__main__":
    main()
