# DAO Buds for Android

Standalone Kotlin + Jetpack Compose companion app replacing Redmagic Goper (`cn.nubia.externdevice`).
Zero bloat, zero regional locks, full GAIA v3 (`0x001D`) + Redmagic Custom (`0x0E`) control over Bluetooth Classic RFCOMM (`00001101`).

## Build & Install via ADB
1. Open `android/DaoBuds` in Android Studio (or install JDK 17 + Android SDK CLI tools).
2. Build debug APK:
   ```bash
   ./gradlew assembleDebug
   ```
3. Install onto your phone over USB (`adb`):
   ```bash
   adb install -r app/build/outputs/apk/debug/app-debug.apk
   ```
