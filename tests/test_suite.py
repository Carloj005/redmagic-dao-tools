#!/usr/bin/env python3
"""Unit tests for offline APPUHDR5 inspector, GAIA v3 stats decoder, and BLE 0x08CA watchdog."""

import importlib.util
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import daotws  # noqa: E402
import fw_inspect  # noqa: E402


def _load_watchdog():
    spec = importlib.util.spec_from_file_location(
        "daobuds_ble_watchdog", os.path.join(ROOT, "daobuds-ble-watchdog.py")
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


watchdog = _load_watchdog()


def build_synthetic_appuhdr5(
    variant: bytes = b"BH4010\x00\x00",
    major: int = 9,
    minor: int = 0,
    ps_cfg: int = 2,
    compat_upgrades=((8, 0),),
    compat_cfgs=(1,),
    partitions=((1, 0, b"\xAA" * 64), (2, 1, b"\xBB" * 32)),
    footer_sig: bytes = b"\x55" * 256,
    trailing: bytes = b"",
) -> bytes:
    hdr_body = bytearray()
    hdr_body.extend(variant[:8].ljust(8, b"\x00"))
    hdr_body.extend(struct.pack(">HHH", major, minor, len(compat_upgrades)))
    for cmaj, cmin in compat_upgrades:
        hdr_body.extend(struct.pack(">HH", cmaj, cmin))
    hdr_body.extend(struct.pack(">HH", ps_cfg, len(compat_cfgs)))
    for ccfg in compat_cfgs:
        hdr_body.extend(struct.pack(">H", ccfg))

    out = bytearray(b"APPUHDR5")
    out.extend(struct.pack(">I", len(hdr_body)))
    out.extend(hdr_body)

    for ptype, pnum, payload in partitions:
        out.extend(b"PARTDATA")
        out.extend(struct.pack(">IHH", len(payload) + 4, ptype, pnum))
        out.extend(payload)

    if footer_sig is not None:
        out.extend(b"APPUPFTR")
        out.extend(struct.pack(">I", len(footer_sig)))
        out.extend(footer_sig)

    out.extend(trailing)
    return bytes(out)


class TestAppuhdr5Inspector(unittest.TestCase):
    def test_valid_container_parses_cleanly(self):
        blob = build_synthetic_appuhdr5()
        info = fw_inspect.inspect_firmware_bytes(blob, "test.bin")
        self.assertTrue(info["valid"], info["errors"])
        self.assertEqual(info["errors"], [])
        self.assertEqual(info["warnings"], [])
        self.assertEqual(info["header"]["magic"], "APPUHDR5")
        self.assertEqual(info["header"]["device_variant"], "BH4010")
        self.assertEqual(info["header"]["version"], "9.0.2")
        self.assertEqual(info["header"]["compatible_upgrades"], ["8.0"])
        self.assertEqual(info["header"]["compatible_ps_configs"], [1])
        self.assertEqual(len(info["partitions"]), 2)
        self.assertEqual(info["partitions"][0]["payload_size"], 64)
        self.assertEqual(info["partitions"][1]["number"], 1)
        self.assertEqual(info["footer"]["length"], 256)
        self.assertIn("RSA-2048", info["footer"]["signature_class"])

    def test_missing_footer_is_invalid(self):
        blob = build_synthetic_appuhdr5(footer_sig=None)
        info = fw_inspect.inspect_firmware_bytes(blob)
        self.assertFalse(info["valid"])
        self.assertTrue(any("APPUPFTR" in e for e in info["errors"]))

    def test_truncated_partition_is_invalid(self):
        blob = build_synthetic_appuhdr5()[:-300]
        info = fw_inspect.inspect_firmware_bytes(blob)
        self.assertFalse(info["valid"])

    def test_unsigned_and_trailing_emit_warnings(self):
        blob = build_synthetic_appuhdr5(footer_sig=b"", trailing=b"\x00\x01")
        info = fw_inspect.inspect_firmware_bytes(blob)
        self.assertTrue(info["valid"])
        self.assertEqual(info["trailing_bytes"], 2)
        self.assertEqual(len(info["warnings"]), 2)

    def test_file_inspection_roundtrip(self):
        blob = build_synthetic_appuhdr5()
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
            tf.write(blob)
            path = tf.name
        try:
            info = fw_inspect.inspect_firmware_file(path)
            self.assertTrue(info["valid"])
            report = fw_inspect.format_report(info)
            self.assertIn("READ-ONLY", report)
            self.assertIn("BH4010", report)
        finally:
            os.unlink(path)


class TestGaiaStatsDecoder(unittest.TestCase):
    def test_parse_category_streaming_stats(self):
        # more=0, cat=0x0001, codec=5 (aptX Adaptive), bitrate=320000 LE, rssi=-58 (0xC6), snr=24 (0x18)
        payload = bytes.fromhex("000001010105030400e204000401c6080118")
        more, cat, items = daotws.parse_statistics_category_response(payload)
        self.assertFalse(more)
        self.assertEqual(cat, 0x0001)
        self.assertEqual(len(items), 4)
        decoded = {
            d["name"]: d for d in (daotws.decode_stat_value(cat, sid, raw) for sid, raw in items)
        }
        self.assertEqual(decoded["codec_type"]["value"], "aptX Adaptive")
        self.assertEqual(decoded["bitrate"]["value"], 320.0)
        self.assertEqual(decoded["primary_rssi_dbm"]["value"], -58)
        self.assertEqual(decoded["primary_snr_db"]["value"], 24)


class TestBleWatchdog08ca(unittest.TestCase):
    def test_parse_live_captured_packet(self):
        # Live hardware capture verified against GAIA RFCOMM: L=49 (0x31), R=61 (0x3d), Case=31 (0x1f)
        raw_both = bytes.fromhex("0101dcf090506c810106020002313d1f00")
        parsed_both = watchdog.parse_nubia_08ca(raw_both)
        self.assertIsNotNone(parsed_both)
        self.assertEqual(parsed_both["mac"], "DC:F0:90:50:6C:81")
        self.assertEqual(parsed_both["left"], 49)
        self.assertEqual(parsed_both["right"], 61)
        self.assertEqual(parsed_both["case"], 31)

        # Single-bud packet (L=71, R=absent 0xFF, Case=57)
        raw_single = bytes.fromhex("0101dcf090506c81010602000247ff3900")
        parsed = watchdog.parse_nubia_08ca(raw_single)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["left"], 71)
        self.assertIsNone(parsed["right"])
        self.assertEqual(parsed["case"], 57)

    def test_charging_flag_bit7(self):
        # left=0x80|85=0xD5, right=0x80|80=0xD0, case=100=0x64
        raw = bytes.fromhex("0101dcf090506c810106020002d5d06400")
        parsed = watchdog.parse_nubia_08ca(raw)
        self.assertEqual(parsed["left"], 85)
        self.assertTrue(parsed["left_charging"])
        self.assertEqual(parsed["right"], 80)
        self.assertTrue(parsed["right_charging"])
        self.assertEqual(parsed["case"], 100)
        self.assertFalse(parsed["case_charging"])

    def test_evaluator_stuck_bud_debounce_and_imbalance(self):
        ev = watchdog.WatchdogEvaluator(imbalance_pct=20, cooldown_sec=600.0, stuck_delay_sec=30.0)
        single = {"mac": "DC:F0:90:50:6C:81", "left": None, "right": 71, "case": 57}
        self.assertEqual(ev.evaluate(single, bt_connected=True, now=100.0), [])
        alerts = ev.evaluate(single, bt_connected=True, now=135.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0][0], "single_bud")
        # Cooldown suppresses duplicate
        self.assertEqual(ev.evaluate(single, bt_connected=True, now=200.0), [])

        imbal = {"mac": "DC:F0:90:50:6C:81", "left": 40, "right": 72, "case": 50}
        alerts2 = ev.evaluate(imbal, bt_connected=True, now=210.0)
        self.assertEqual(len(alerts2), 1)
        self.assertEqual(alerts2[0][0], "imbalance")


if __name__ == "__main__":
    unittest.main()
