#!/usr/bin/env python3
"""Read-only Qualcomm S5/S3 Gen2 HID VM Upgrade version query for DAO TWS QCC3086 dongle (19d2:0616).

Uses the exact same read-only HostVersionReq handshake as Linux fwupd's qc-s5gen2 plugin:
  1. SET_FEATURE RID 3: Connect (0x02 0x00 0x00)
  2. WRITE RID 5: HostVersionReq (0x19 0x00 0x00) -> reads major.minor.config
  3. SET_FEATURE RID 3: Disconnect (0x07 0x00 0x00)
Never sends StartReq/Data/Commit/Reboot.
"""

import fcntl
import glob
import os
import select
import struct
import sys


def hidiocsfeature(length: int) -> int:
    return (3 << 30) | (length << 16) | (ord("H") << 8) | 0x06


def find_datalink_hidraw() -> str:
    for syspath in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = os.path.join(syspath, "device", "uevent")
        if not os.path.exists(uevent):
            continue
        txt = open(uevent, "r", encoding="utf-8", errors="ignore").read()
        if "000019D2:00000616" in txt.upper() and "/input1" in txt:
            return "/dev/" + os.path.basename(syspath)
    raise RuntimeError("DAO TWS dongle (19d2:0616 input1) not found")


def read_resp(fd: int, timeout: float = 1.0) -> bytes:
    r, _, _ = select.select([fd], [], [], timeout)
    if not r:
        return b""
    return os.read(fd, 512)


def send_feature_cmd(fd: int, payload: bytes) -> None:
    buf = bytearray(63)  # [RID=3, payload_len, payload[61]]
    buf[0] = 0x03
    buf[1] = len(payload)
    buf[2 : 2 + len(payload)] = payload
    fcntl.ioctl(fd, hidiocsfeature(len(buf)), buf)


def send_data_msg(fd: int, payload: bytes) -> None:
    buf = bytearray(255)  # [RID=5, payload_len, payload[253]]
    buf[0] = 0x05
    buf[1] = len(payload)
    buf[2 : 2 + len(payload)] = payload
    os.write(fd, bytes(buf))


def main():
    dev = find_datalink_hidraw()
    print(f"Opening {dev} (read-only qc-s5gen2 version query)...")
    fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    try:
        # 1. Connect
        send_feature_cmd(fd, bytes([0x02, 0x00, 0x00]))
        resp = read_resp(fd, 1.0)
        print(f"Connect RX ({len(resp)}B): {resp.hex(' ')}")
        if len(resp) >= 3 and resp[0] == 0x06:
            plen = resp[1]
            status = resp[2 : 2 + plen]
            print(f"  -> Connect status bytes: {status.hex(' ')}")

        # 2. HostVersionReq (0x19, len=0)
        send_data_msg(fd, bytes([0x19, 0x00, 0x00]))
        vresp = read_resp(fd, 1.0)
        print(f"HostVersion RX ({len(vresp)}B): {vresp.hex(' ')}")
        if len(vresp) >= 11 and vresp[0] == 0x06 and vresp[2] == 0x1A:
            dlen, major, minor, config = struct.unpack(">HHHH", vresp[3:11])
            print(f"  -> DONGLE FIRMWARE VERSION: major={major}, minor={minor}, config={config} (len={dlen})")

        # 3. SyncReq (0x13, fileId=0) read-only protocolVersion & resumePoint check
        send_data_msg(fd, struct.pack(">BHI", 0x13, 4, 0))
        sresp = read_resp(fd, 1.0)
        print(f"SyncCfm RX ({len(sresp)}B): {sresp.hex(' ')}")
        if len(sresp) >= 11 and sresp[0] == 0x06 and sresp[2] == 0x14:
            dlen = struct.unpack(">H", sresp[3:5])[0]
            resume_pt = sresp[5]
            file_id = struct.unpack(">I", sresp[6:10])[0]
            proto_ver = sresp[10]
            print(f"  -> Upgrade Protocol Version: v{proto_ver}, resume_point={resume_pt}, last_file_id=0x{file_id:08x}")
    finally:
        # 4. Always clean Disconnect (0x07 0x00 0x00)
        try:
            send_feature_cmd(fd, bytes([0x07, 0x00, 0x00]))
            dresp = read_resp(fd, 0.5)
            print(f"Disconnect RX ({len(dresp)}B): {dresp.hex(' ')}")
        except OSError as e:
            print(f"Disconnect note: {e}")
        os.close(fd)


if __name__ == "__main__":
    main()
