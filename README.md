# Redmagic Cyberbuds DAO TWS (`BH4010`) — Open-Source Control & Fix Suite

[![Build & Test](https://github.com/Carloj005/redmagic-dao-tools/actions/workflows/build.yml/badge.svg)](https://github.com/Carloj005/redmagic-dao-tools/actions/workflows/build.yml)

Complete reverse-engineered protocol, OS audio stability fixes, CLI, live radio telemetry (`Feature 0x0C`), Mimi Sound DSP (`Feature 0x0E`), offline read-only `APPUHDR5` firmware inspector, passive BLE `0x08CA` watchdog, Omarchy native app + shell plugin, Windows suite, and Android app for the **Redmagic DAO TWS** (`QCC5171` earbuds + `QCC3086` 2.4 GHz USB dongle).

## Prebuilt Downloads (GitHub Releases)

Every tagged release (`v*`) automatically builds and attaches:
- **Android:** `DaoBuds.apk` (Jetpack Compose + Material 3)
- **Windows:** `DAOBuds.exe` (standalone PyInstaller build)
- **Linux (x86_64):** `daobuds-linux-x86_64` (native Qt6 Quick binary) + `SHA256SUMS.txt`

## Automatic Install (by OS)

### Linux / Omarchy / Arch
```bash
chmod +x install.sh
./install.sh            # Installs daotws CLI, fw_inspect, WirePlumber fix, udev rule, native daobuds app, Omarchy plugin, and BLE watchdog
./install.sh --dry-run  # Preview every step before applying
./install.sh --uninstall
```

### Windows 10 / 11 (PowerShell as Administrator)
```powershell
.\install.ps1                      # Installs DAO Buds desktop app + fixes 16 kHz mic / USB suspend
.\install.ps1 -BuildExe            # Also compiles standalone DAOBuds.exe
.\install.ps1 -DisableTelephonyHid # Extra fix if Windows sound cards freeze on dongle plug-in
.\install.ps1 -Uninstall
```

### Android
Download `DaoBuds.apk` from [GitHub Releases](../../releases), or build locally with the included Gradle 8.9 wrapper:
```bash
cd android/DaoBuds
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Key Features & CLI Examples

```bash
# Full status (Bluetooth GAIA v3 + USB dongle sysfs detection)
daotws status --json

# Live radio & audio link telemetry (Feature 0x0C STATISTICS: RSSI, SNR, codec, bitrate)
daotws stats
daotws stats --watch 2

# Remap double/triple tap gestures (Feature 0x0E PDU 0x13 — missing from Goper)
daotws touch --ld play --lt anc --rd next --rt prev

# Battery Saver & Stability (LEDs OFF, Hall OFF, In-Ear OFF, Single-Point, Normal codec)
daotws battery-saver

# Mimi Sound DSP (Feature 0x0E PDU 0x14-0x1D; enabled on CN firmware, safely reported on Global 9.0)
daotws mimi --enable on --intensity 60
daotws mimi --clear

# Offline read-only Qualcomm APPUHDR5 firmware package validator (zero flashing)
daotws inspect-fw /path/to/official_firmware.bin --json

# Passive BLE 0x08CA watchdog (systemd --user service)
systemctl --user status daobuds-ble-watchdog.service
daobuds-ble-watchdog --once
```

## Repository Contents

- [`PROTOCOL.md`](PROTOCOL.md) — Reverse-engineered GAIA v3 (`0x001D`), Feature `0x0C` Statistics, Redmagic Custom (`0x0E` incl. Mimi DSP), `APPUHDR5` container spec, and USB HID `qc-s5gen2` (`19d2:0616`).
- [`daotws.py`](daotws.py) — Zero-dependency Python 3 CLI (status, touch, ANC, 10-band EQ, RGB, stats, Mimi, `inspect-fw`).
- [`fw_inspect.py`](fw_inspect.py) — Offline read-only `APPUHDR5` / `PARTDATA` / `APPUPFTR` validator (SHA-256 + CRC-32 `file_id`, no flash commands).
- [`daobuds-ble-watchdog.py`](daobuds-ble-watchdog.py) & [`systemd/daobuds-ble-watchdog.service`](systemd/daobuds-ble-watchdog.service) — Passive BlueZ D-Bus `0x08CA` monitor with `omarchy-notification-send` / `notify-send` alerts for stuck-in-case earbuds or battery imbalance ≥20%.
- [`daobuds/`](daobuds/) — Native Omarchy C++17 / Qt Quick desktop app (`qmake6`, live theme, Hyprland rounding, EN/IT, live Telemetry & Mimi tab, Arch `PKGBUILD`).
- [`omarchy-plugin/clay.daobuds/`](omarchy-plugin/clay.daobuds/) — Native Omarchy Shell bar widget + overlay card + battery alerts.
- [`dao-tws-dongle.conf`](dao-tws-dongle.conf) & [`70-redmagic-dao.rules`](70-redmagic-dao.rules) — Linux PipeWire/WirePlumber fix & non-root `hidraw` udev rule.
- [`windows/`](windows/) — Windows PowerShell dongle audio fix + zero-dependency desktop app (with Telemetry & Mimi tab) & `.exe` builder.
- [`android/DaoBuds/`](android/DaoBuds/) — Kotlin + Jetpack Compose + Material 3 Goper replacement with Gradle 8.9 wrapper.
- [`tests/test_suite.py`](tests/test_suite.py) & [`.github/workflows/build.yml`](.github/workflows/build.yml) — Automated test suite and CI/CD pipeline.

## Firmware / Secure Boot Note

Both `QCC5171` (earbuds) and `QCC3086` (dongle) enforce hardware Secure Boot (`APPUHDR5` cryptographic signatures checked via eFuse). This project strictly uses documented GAIA/HID/OS interfaces and read-only inspection; it does **not** bypass Secure Boot or flash unsigned firmware.
