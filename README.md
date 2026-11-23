# Redmagic Cyberbuds DAO TWS (`BH4010`) — Open-Source Control & Fix Suite

Complete reverse-engineered protocol, OS audio stability fixes, CLI, Omarchy native app + shell plugin, Windows suite, and Android app for the **Redmagic DAO TWS** (`QCC5171` earbuds + `QCC3086` 2.4 GHz USB dongle).

## Automatic Install (by OS)

### Linux / Omarchy / Arch
```bash
chmod +x install.sh
./install.sh            # Installs CLI, WirePlumber fix, udev rule, native daobuds app, and Omarchy plugin
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
Open `android/DaoBuds` in Android Studio, build `assembleDebug`, and install via `adb`:
```bash
adb install -r android/DaoBuds/app/build/outputs/apk/debug/app-debug.apk
```

## Repository Contents

- [`PROTOCOL.md`](PROTOCOL.md) — Complete reverse-engineered GAIA v3 (`0x001D`) + Redmagic Custom (`0x0E`) + USB HID `qc-s5gen2` (`19d2:0616`) specification.
- [`daotws.py`](daotws.py) — Zero-dependency Python 3 CLI for Bluetooth + dongle diagnostics.
- [`daobuds/`](daobuds/) — Native Omarchy C++17 / Qt Quick desktop app (`qmake6`, live theme, Hyprland rounding, EN/IT, Arch `PKGBUILD`).
- [`omarchy-plugin/clay.daobuds/`](omarchy-plugin/clay.daobuds/) — Native Omarchy Shell bar widget + overlay card + stuck-in-case battery alerts.
- [`dao-tws-dongle.conf`](dao-tws-dongle.conf) & [`70-redmagic-dao.rules`](70-redmagic-dao.rules) — Linux PipeWire/WirePlumber fix & non-root `hidraw` udev rule.
- [`windows/`](windows/) — Windows PowerShell dongle audio fix + zero-dependency desktop app & `.exe` builder.
- [`android/DaoBuds/`](android/DaoBuds/) — Kotlin + Jetpack Compose + Material 3 Goper replacement.
- [`inspect_bt.py`](inspect_bt.py) & [`probe_dongle_version.py`](probe_dongle_version.py) — Read-only hardware diagnostic utilities.
