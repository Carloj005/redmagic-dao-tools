#!/usr/bin/env python3
"""Read-only Bluetooth SDP + BlueZ D-Bus + BLE inspector for Redmagic DAO TWS."""

import dbus
import socket
import struct
import sys

MAC = sys.argv[1] if len(sys.argv) > 1 else "DC:F0:90:50:6C:81"


def dump_bluez_dbus(mac: str) -> None:
    print("=== BLUEZ D-BUS OBJECTS ===")
    bus = dbus.SystemBus()
    om = dbus.Interface(
        bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager"
    )
    objs = om.GetManagedObjects()
    needle = mac.upper().replace(":", "_")
    for path, ifaces in sorted(objs.items()):
        if needle in path.upper() or "DAO" in str(ifaces):
            print(f"\n[PATH] {path}")
            for iface, props in sorted(ifaces.items()):
                if iface.startswith("org.freedesktop."):
                    continue
                print(f"  [{iface}]")
                for k, v in sorted(props.items()):
                    if isinstance(v, dbus.Array) and v.signature == "y":
                        b = bytes(v)
                        print(f"    {k}: {b.hex(' ')} (len={len(b)})")
                    elif isinstance(v, dbus.Dictionary):
                        print(f"    {k}:")
                        for dk, dv in v.items():
                            if isinstance(dv, dbus.Array) and dv.signature == "y":
                                b = bytes(dv)
                                print(f"      {hex(int(dk)) if isinstance(dk, int) else dk}: {b.hex(' ')}")
                            else:
                                print(f"      {dk}: {dv}")
                    elif isinstance(v, dbus.Byte):
                        print(f"    {k}: {int(v)} (0x{int(v):02x})")
                    else:
                        print(f"    {k}: {v}")


# Minimal SDP Data Element parser (Bluetooth Core Spec Vol 3 Part B)
def parse_de(data: bytes, offset: int = 0):
    if offset >= len(data):
        return None, offset
    hdr = data[offset]
    dtype = hdr >> 3
    size_idx = hdr & 0x07
    offset += 1

    if dtype == 0:  # Nil
        return None, offset

    if size_idx <= 4:
        size = 1 << size_idx
    elif size_idx == 5:
        size = data[offset]
        offset += 1
    elif size_idx == 6:
        size = struct.unpack(">H", data[offset : offset + 2])[0]
        offset += 2
    elif size_idx == 7:
        size = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
    else:
        raise ValueError(f"bad size_idx {size_idx}")

    payload = data[offset : offset + size]
    end = offset + size

    if dtype == 1:  # Unsigned int
        return int.from_bytes(payload, "big"), end
    if dtype == 2:  # Signed int
        return int.from_bytes(payload, "big", signed=True), end
    if dtype == 3:  # UUID
        if size == 2:
            return f"UUID16:0x{payload.hex()}", end
        if size == 4:
            return f"UUID32:0x{payload.hex()}", end
        if size == 16:
            h = payload.hex()
            return f"UUID128:{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}", end
        return f"UUID:{payload.hex()}", end
    if dtype == 4:  # String
        return payload.decode("utf-8", errors="replace"), end
    if dtype == 5:  # Bool
        return bool(payload[0]), end
    if dtype in (6, 7):  # Sequence / Alternative
        items = []
        pos = 0
        while pos < len(payload):
            item, pos = parse_de(payload, pos)
            items.append(item)
        return items, end
    if dtype == 8:  # URL
        return payload.decode("utf-8", errors="replace"), end
    return payload.hex(), end


def sdp_browse(mac: str) -> None:
    print("\n=== RAW SDP BROWSE (L2CAP PSM 1) ===")
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    sock.settimeout(5.0)
    try:
        sock.connect((mac, 1))
    except OSError as e:
        print(f"SDP L2CAP connect failed: {e}")
        return

    # ServiceSearchAttributeRequest (PDU 0x06) for PublicBrowseRoot (0x1002) and L2CAP (0x0100)
    for label, uuid16 in [("L2CAP (0x0100) - ALL SERVICES", 0x0100), ("PublicBrowseRoot (0x1002)", 0x1002)]:
        print(f"\n--- Query: {label} ---")
        full_attr_bytes = bytearray()
        cont = b"\x00"
        tid = 1
        while True:
            # ServiceSearchPattern: Sequence(UUID16) -> 0x35 0x03 0x19 <hi> <lo>
            search_pat = struct.pack(">BBBH", 0x35, 0x03, 0x19, uuid16)
            max_attr_bc = struct.pack(">H", 0xFFFF)
            # AttributeIDList: Sequence(Range 0x0000-0xFFFF) -> 0x35 0x05 0x0a 0x00 0x00 0xff 0xff
            attr_list = b"\x35\x05\x0a\x00\x00\xff\xff"
            params = search_pat + max_attr_bc + attr_list + cont
            pdu = struct.pack(">BHH", 0x06, tid, len(params)) + params
            tid += 1
            sock.send(pdu)
            resp = sock.recv(4096)
            pdu_id, r_tid, plen = struct.unpack(">BHH", resp[:5])
            if pdu_id != 0x07:
                print(f"Unexpected SDP PDU: 0x{pdu_id:02x} {resp.hex(' ')}")
                break
            body = resp[5 : 5 + plen]
            bc = struct.unpack(">H", body[:2])[0]
            full_attr_bytes.extend(body[2 : 2 + bc])
            cont_len = body[2 + bc]
            if cont_len == 0:
                break
            cont = body[2 + bc : 2 + bc + 1 + cont_len]

        if full_attr_bytes:
            records, _ = parse_de(bytes(full_attr_bytes), 0)
            if isinstance(records, list):
                for idx, rec in enumerate(records):
                    print(f"\nService Record #{idx + 1}:")
                    if isinstance(rec, list):
                        for i in range(0, len(rec), 2):
                            attr_id = rec[i]
                            val = rec[i + 1] if i + 1 < len(rec) else None
                            attr_names = {
                                0x0000: "RecordHandle",
                                0x0001: "ServiceClassIDList",
                                0x0004: "ProtocolDescriptorList",
                                0x0005: "BrowseGroupList",
                                0x0006: "LanguageBaseAttrIDList",
                                0x0009: "BluetoothProfileDescriptorList",
                                0x0100: "ServiceName",
                                0x0101: "ServiceDescription",
                                0x0102: "ProviderName",
                                0x0200: "SpecID/Version",
                                0x0201: "VendorID",
                                0x0202: "ProductID",
                                0x0203: "Version",
                                0x0205: "VendorIDSource",
                            }
                            name = attr_names.get(attr_id, f"0x{attr_id:04x}")
                            print(f"  {name}: {val}")
        break  # L2CAP 0x0100 returns all services!
    sock.close()


if __name__ == "__main__":
    dump_bluez_dbus(MAC)
    sdp_browse(MAC)
