# DAO Buds for Android

Standalone Kotlin + Jetpack Compose companion app replacing Redmagic Goper (`cn.nubia.externdevice`).
Zero bloat, zero regional locks, full GAIA v3 (`0x001D`) + Feature `0x0C` Telemetry + Redmagic Custom (`0x0E`, incl. Touch & Mimi DSP) over Bluetooth Classic RFCOMM (`00001101`).

## Download or Build & Install via ADB
1. Download the prebuilt `DaoBuds.apk` from GitHub Releases, or build locally using the included Gradle 8.9 wrapper (requires JDK 17 + Android SDK):
   ```bash
   ./gradlew assembleDebug
   ```
2. Install onto your phone over USB (`adb`):
   ```bash
   adb install -r app/build/outputs/apk/debug/app-debug.apk
   ```
