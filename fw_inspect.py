#!/usr/bin/env python3
"""Offline read-only validator/inspector for Qualcomm APPUHDR5 firmware packages.

Inspects APPUHDR# header, PARTDATA partitions, APPUPFTR footer/signature,
target device variant, versions, CRC-32 (qc-s5gen2 file_id), and SHA-256 digests.
Strictly read-only: performs NO Bluetooth, USB, or firmware flashing operations.
"""

import argparse
import hashlib
import json
import os
import struct
import sys
import zlib
from typing import Any, Dict, List

HEADER_MAGIC_PREFIX = b"APPUHDR"
PART_MAGIC = b"PARTDATA"
FOOTER_MAGIC = b"APPUPFTR"

PARTITION_TYPE_NAMES = {
    0: "raw/unknown",
    1: "apps_p0/ro_fs",
    2: "apps_p1/vm",
    3: "curator/fs",
    4: "ro_cfg_fs",
    5: "device_ro_fs",
    6: "rw_config",
    7: "rw_fs",
    8: "dsp/audio",
}


def _describe_signature_len(n: int) -> str:
    if n == 0:
        return "empty (unsigned)"
    if n == 32:
        return "32 B (SHA-256 / HMAC-256)"
    if n == 64:
        return "64 B (ECDSA-P256 / Ed25519)"
    if n == 128:
        return "128 B (RSA-1024 / QCC OEM signature)"
    if n == 256:
        return "256 B (RSA-2048 / QCC OEM signature)"
    if n == 384:
        return "384 B (RSA-3072)"
    if n == 512:
        return "512 B (RSA-4096)"
    return f"{n} B (OEM signature/footer blob)"


def inspect_firmware_bytes(data: bytes, filename: str = "<memory>") -> Dict[str, Any]:
    """Parse and validate a Qualcomm APPUHDR# firmware container from raw bytes."""
    errors: List[str] = []
    warnings: List[str] = []
    total_size = len(data)
    file_sha256 = hashlib.sha256(data).hexdigest()
    file_crc32 = zlib.crc32(data) & 0xFFFFFFFF

    result: Dict[str, Any] = {
        "file": filename,
        "size": total_size,
        "sha256": file_sha256,
        "crc32_file_id": f"0x{file_crc32:08x}",
        "valid": False,
        "read_only": True,
        "header": None,
        "partitions": [],
        "footer": None,
        "trailing_bytes": 0,
        "errors": errors,
        "warnings": warnings,
    }

    if total_size < 26:
        errors.append(f"File too small ({total_size} bytes); minimum APPUHDR header is 26 bytes")
        return result

    magic = data[0:8]
    if not magic.startswith(HEADER_MAGIC_PREFIX) or not (ord("0") <= magic[7] <= ord("9")):
        errors.append(f"Invalid header magic {magic!r}; expected APPUHDR<digit> (e.g. APPUHDR5)")
        return result

    protocol_ver = magic[7] - ord("0")
    if protocol_ver != 5:
        warnings.append(f"Header protocol version is {protocol_ver} ({magic.decode('ascii')}), not APPUHDR5")

    hdr_len = struct.unpack_from(">I", data, 8)[0]
    hdr_end = 12 + hdr_len
    if hdr_end > total_size:
        errors.append(f"Header length ({hdr_len} B, end={hdr_end}) exceeds file size ({total_size} B)")
        return result

    raw_variant = data[12:20]
    device_variant = raw_variant.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
    major, minor, num_compat_upgrades = struct.unpack_from(">HHH", data, 20)

    off = 26
    compat_upgrades: List[str] = []
    compat_end = off + num_compat_upgrades * 4
    if compat_end + 4 > hdr_end:
        errors.append(
            f"Compatible upgrades list ({num_compat_upgrades} entries) overflows header boundary ({hdr_end})"
        )
        return result

    for _ in range(num_compat_upgrades):
        c_maj, c_min = struct.unpack_from(">HH", data, off)
        compat_upgrades.append(f"{c_maj}.{c_min}")
        off += 4

    ps_config_ver, num_compat_configs = struct.unpack_from(">HH", data, off)
    off += 4

    compat_configs: List[int] = []
    cfg_end = off + num_compat_configs * 2
    if cfg_end > hdr_end:
        errors.append(
            f"Compatible PS config list ({num_compat_configs} entries) overflows header boundary ({hdr_end})"
        )
        return result

    for _ in range(num_compat_configs):
        compat_configs.append(struct.unpack_from(">H", data, off)[0])
        off += 2

    if off != hdr_end:
        warnings.append(f"Header has {hdr_end - off} extra trailing metadata bytes before first section")

    result["header"] = {
        "magic": magic.decode("ascii"),
        "protocol_version": protocol_ver,
        "header_length": hdr_len,
        "device_variant": device_variant,
        "device_variant_hex": raw_variant.hex(),
        "version": f"{major}.{minor}.{ps_config_ver}",
        "major": major,
        "minor": minor,
        "ps_config_version": ps_config_ver,
        "compatible_upgrades": compat_upgrades,
        "compatible_ps_configs": compat_configs,
    }

    # Walk PARTDATA sections until APPUPFTR
    pos = hdr_end
    seq = 0
    seen_footer = False

    while pos < total_size:
        if pos + 12 > total_size:
            errors.append(f"Truncated section header at offset 0x{pos:x} ({total_size - pos} bytes left)")
            break

        sec_magic = data[pos : pos + 8]
        sec_len = struct.unpack_from(">I", data, pos + 8)[0]

        if sec_magic == PART_MAGIC:
            if sec_len < 4:
                errors.append(f"PARTDATA #{seq} at 0x{pos:x} has invalid length {sec_len} (< 4)")
                break
            sec_end = pos + 12 + sec_len
            if sec_end > total_size:
                errors.append(
                    f"PARTDATA #{seq} at 0x{pos:x} truncated (needs {sec_end} B, file is {total_size} B)"
                )
                break
            part_type, part_num = struct.unpack_from(">HH", data, pos + 12)
            payload = data[pos + 16 : sec_end]
            result["partitions"].append(
                {
                    "index": seq,
                    "offset": pos,
                    "type": part_type,
                    "type_name": PARTITION_TYPE_NAMES.get(part_type, f"type_{part_type}"),
                    "number": part_num,
                    "payload_size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
            pos = sec_end
            seq += 1
        elif sec_magic == FOOTER_MAGIC:
            sec_end = pos + 12 + sec_len
            if sec_end > total_size:
                errors.append(
                    f"APPUPFTR at 0x{pos:x} truncated (needs {sec_end} B, file is {total_size} B)"
                )
                break
            sig = data[pos + 12 : sec_end]
            result["footer"] = {
                "magic": FOOTER_MAGIC.decode("ascii"),
                "offset": pos,
                "length": sec_len,
                "signature_class": _describe_signature_len(sec_len),
                "signature_sha256": hashlib.sha256(sig).hexdigest(),
            }
            if sec_len == 0:
                warnings.append("APPUPFTR signature length is 0 bytes (unsigned package — Secure Boot will reject)")
            pos = sec_end
            seen_footer = True
            break
        else:
            errors.append(f"Unexpected section magic {sec_magic!r} at offset 0x{pos:x}")
            break

    if not seen_footer:
        errors.append("Missing APPUPFTR footer (incomplete or corrupted firmware file)")

    if not result["partitions"]:
        warnings.append("Container contains zero PARTDATA partitions")

    trailing = total_size - pos
    result["trailing_bytes"] = trailing
    if seen_footer and trailing > 0:
        warnings.append(f"Found {trailing} trailing byte(s) after APPUPFTR footer")

    result["valid"] = len(errors) == 0
    return result


def inspect_firmware_file(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        data = f.read()
    return inspect_firmware_bytes(data, filename=os.path.abspath(path))


def format_report(info: Dict[str, Any]) -> str:
    lines = [
        f"Firmware Container Inspection (READ-ONLY — no flashing performed)",
        f"  File           : {info['file']}",
        f"  Size           : {info['size']} bytes",
        f"  SHA-256        : {info['sha256']}",
        f"  CRC-32 File ID : {info['crc32_file_id']}",
        f"  Valid          : {'YES' if info['valid'] else 'NO'}",
    ]
    hdr = info.get("header")
    if hdr:
        lines.extend(
            [
                f"  Header         : {hdr['magic']} (protocol v{hdr['protocol_version']}, {hdr['header_length']} B)",
                f"  Device Variant : {hdr['device_variant'] or '(empty)'} (hex: {hdr['device_variant_hex']})",
                f"  Version        : {hdr['version']} (major={hdr['major']}, minor={hdr['minor']}, ps_cfg={hdr['ps_config_version']})",
                f"  Compat Upgr.   : {', '.join(hdr['compatible_upgrades']) or 'none'}",
                f"  Compat PS Cfg  : {', '.join(str(x) for x in hdr['compatible_ps_configs']) or 'none'}",
            ]
        )
    parts = info.get("partitions", [])
    lines.append(f"  Partitions     : {len(parts)}")
    for p in parts:
        lines.append(
            f"    [{p['index']}] offset=0x{p['offset']:06x}  part={p['number']}  "
            f"type={p['type']} ({p['type_name']})  size={p['payload_size']} B  sha256={p['sha256'][:16]}..."
        )
    ftr = info.get("footer")
    if ftr:
        lines.append(
            f"  Footer         : {ftr['magic']} @ 0x{ftr['offset']:06x}  "
            f"len={ftr['length']} B ({ftr['signature_class']})  sig_sha256={ftr['signature_sha256'][:16]}..."
        )
    if info.get("trailing_bytes"):
        lines.append(f"  Trailing Bytes : {info['trailing_bytes']}")
    for w in info.get("warnings", []):
        lines.append(f"  WARNING        : {w}")
    for e in info.get("errors", []):
        lines.append(f"  ERROR          : {e}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only offline validator for Qualcomm APPUHDR5 firmware .bin files"
    )
    parser.add_argument("file", help="Path to Qualcomm APPUHDR5 .bin firmware file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    try:
        info = inspect_firmware_file(args.file)
    except OSError as e:
        print(f"Error reading {args.file}: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(format_report(info))
    sys.exit(0 if info["valid"] else 1)


if __name__ == "__main__":
    main()
