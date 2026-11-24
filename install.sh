#!/usr/bin/env bash
# Universal OS-aware installer for Redmagic DAO TWS Suite (Linux / Omarchy / Arch / Generic Linux)
# On Windows, run: .\install.ps1
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DRY_RUN=0
UNINSTALL=0
NO_SUDO=0
INSTALL_PKG=1
INSTALL_ANDROID=0

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]
  --dry-run        Print actions without modifying the system
  --uninstall      Remove installed rules, WirePlumber fix, CLI, BLE watchdog, and Omarchy plugin
  --no-sudo        Skip sudo actions (udev rule & Arch makepkg install; install user-local only)
  --no-pkg         Skip building/installing the native Qt Quick app
  --android-adb    Build & install Android APK via adb (if Gradle/SDK + phone detected)
  -h, --help       Show this help
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run)       DRY_RUN=1 ;;
    --uninstall)     UNINSTALL=1 ;;
    --no-sudo)       NO_SUDO=1 ;;
    --no-pkg)        INSTALL_PKG=0 ;;
    --android-adb)   INSTALL_ANDROID=1 ;;
    -h|--help)       usage; exit 0 ;;
    *)               echo "Unknown option: $arg" >&2; usage; exit 1 ;;
  esac
done

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

OS="$(uname -s)"
case "$OS" in
  MINGW*|MSYS*|CYGWIN*)
    echo "Detected Windows environment ($OS). Run PowerShell installer instead:"
    echo "  powershell -ExecutionPolicy Bypass -File .\\install.ps1"
    exit 0
    ;;
  Darwin)
    echo "Detected macOS."
    echo "Installing daotws CLI + offline fw_inspect into ~/.local/bin and ~/.local/lib/daotws."
    run mkdir -p "$HOME/.local/bin" "$HOME/.local/lib/daotws"
    run install -m 755 "$ROOT/daotws.py" "$HOME/.local/bin/daotws"
    run install -m 644 "$ROOT/fw_inspect.py" "$HOME/.local/lib/daotws/fw_inspect.py"
    exit 0
    ;;
  Linux) ;;
  *)
    echo "Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

# Detect distro & Omarchy
IS_ARCH=0
IS_OMARCHY=0
if [ -f /etc/arch-release ] || grep -qiE 'arch|omarchy|endeavouros|cachyos|manjaro' /etc/os-release 2>/dev/null; then
  IS_ARCH=1
fi
if [ -d "$HOME/.config/omarchy" ] || command -v omarchy-shell >/dev/null 2>&1; then
  IS_OMARCHY=1
fi

echo "=== Redmagic DAO TWS Installer ==="
echo "  OS      : Linux (Arch=$IS_ARCH, Omarchy=$IS_OMARCHY)"
echo "  Repo    : $ROOT"
[ "$DRY_RUN" -eq 1 ] && echo "  Mode    : DRY-RUN"

if [ "$UNINSTALL" -eq 1 ]; then
  echo "--- Uninstalling user components ---"
  if command -v systemctl >/dev/null 2>&1; then
    run systemctl --user disable --now daobuds-ble-watchdog.service 2>/dev/null || true
  fi
  run rm -f "$HOME/.config/systemd/user/daobuds-ble-watchdog.service"
  if command -v systemctl >/dev/null 2>&1; then
    run systemctl --user daemon-reload 2>/dev/null || true
  fi
  run rm -f "$HOME/.local/bin/daotws" "$HOME/.local/bin/daobuds" "$HOME/.local/bin/daobuds-ble-watchdog"
  run rm -rf "$HOME/.local/lib/daotws"
  run rm -f "$HOME/.local/share/applications/daobuds.desktop"
  run rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/daobuds.svg"
  run rm -f "$HOME/.config/wireplumber/wireplumber.conf.d/dao-tws-dongle.conf"
  run rm -rf "$HOME/.config/omarchy/plugins/clay.daobuds"
  if command -v systemctl >/dev/null 2>&1 && systemctl --user is-active wireplumber >/dev/null 2>&1; then
    run systemctl --user restart wireplumber || true
  fi
  if [ "$NO_SUDO" -eq 0 ]; then
    echo "--- Removing udev rule (sudo) ---"
    run sudo rm -f /etc/udev/rules.d/70-redmagic-dao.rules /etc/udev/rules.d/99-redmagic-dao.rules
    run sudo udevadm control --reload-rules
    run sudo udevadm trigger -s hidraw
    if [ "$IS_ARCH" -eq 1 ] && pacman -Qi daobuds >/dev/null 2>&1; then
      run sudo pacman -Rs --noconfirm daobuds
    fi
  fi
  echo "Uninstall complete."
  exit 0
fi

# 1. CLI tool + offline APPUHDR5 validator
echo "[1/6] Installing daotws CLI + offline fw_inspect -> $HOME/.local/bin/daotws"
run mkdir -p "$HOME/.local/bin" "$HOME/.local/lib/daotws"
run install -m 755 "$ROOT/daotws.py" "$HOME/.local/bin/daotws"
run install -m 644 "$ROOT/fw_inspect.py" "$HOME/.local/lib/daotws/fw_inspect.py"

# 2. WirePlumber dongle audio fix (PipeWire)
if command -v wireplumber >/dev/null 2>&1 || [ -d "$HOME/.config/wireplumber" ]; then
  echo "[2/6] Installing WirePlumber dongle audio fix (48kHz/no-suspend + low mic priority)"
  run mkdir -p "$HOME/.config/wireplumber/wireplumber.conf.d"
  run install -m 644 "$ROOT/dao-tws-dongle.conf" "$HOME/.config/wireplumber/wireplumber.conf.d/dao-tws-dongle.conf"
  if command -v systemctl >/dev/null 2>&1; then
    run systemctl --user restart wireplumber || true
  fi
else
  echo "[2/6] WirePlumber not found — skipping PipeWire dongle rule"
fi

# 3. udev rule for QCC3086 USB dongle (19d2:0616)
if [ "$NO_SUDO" -eq 0 ]; then
  echo "[3/6] Installing udev rule 70-redmagic-dao.rules (requires sudo)"
  run sudo rm -f /etc/udev/rules.d/99-redmagic-dao.rules
  run sudo install -m 644 "$ROOT/70-redmagic-dao.rules" /etc/udev/rules.d/70-redmagic-dao.rules
  run sudo udevadm control --reload-rules
  run sudo udevadm trigger -s hidraw
else
  echo "[3/6] Skipping udev rule (--no-sudo). Install manually:"
  echo "      sudo install -m 644 $ROOT/70-redmagic-dao.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger -s hidraw"
fi

# 4. Native Qt Quick Desktop App (daobuds)
if [ "$INSTALL_PKG" -eq 1 ] && command -v qmake6 >/dev/null 2>&1 && command -v g++ >/dev/null 2>&1; then
  echo "[4/6] Building native Qt Quick app (daobuds)"
  if [ "$IS_ARCH" -eq 1 ] && [ "$NO_SUDO" -eq 0 ] && command -v makepkg >/dev/null 2>&1; then
    run "$ROOT/daobuds/bin/install" --noconfirm
  else
    run "$ROOT/daobuds/bin/build"
    run install -m 755 "$ROOT/daobuds/build/daobuds" "$HOME/.local/bin/daobuds"
    run mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/scalable/apps"
    run install -m 644 "$ROOT/daobuds/pkgbuild/daobuds.desktop" "$HOME/.local/share/applications/daobuds.desktop"
    run install -m 644 "$ROOT/daobuds/pkgbuild/daobuds.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/daobuds.svg"
  fi
else
  echo "[4/6] Skipping native Qt Quick build (qmake6/g++ missing or --no-pkg). You can still run python3 windows/daobuds_win.py on Linux."
fi

# 5. Omarchy Shell Plugin (clay.daobuds)
if [ "$IS_OMARCHY" -eq 1 ]; then
  echo "[5/6] Installing Omarchy Shell plugin -> $HOME/.config/omarchy/plugins/clay.daobuds"
  run mkdir -p "$HOME/.config/omarchy/plugins"
  run rm -rf "$HOME/.config/omarchy/plugins/clay.daobuds"
  run cp -r "$ROOT/omarchy-plugin/clay.daobuds" "$HOME/.config/omarchy/plugins/clay.daobuds"
  echo "      Add 'clay.daobuds' in Omarchy Shell bar settings (or ~/.config/omarchy/shell.json)."
else
  echo "[5/6] Omarchy not detected — skipping Omarchy Shell plugin"
fi

# 6. Passive BLE 0x08CA Watchdog (systemd --user)
echo "[6/6] Installing passive BLE 0x08CA watchdog (daobuds-ble-watchdog.service)"
run install -m 755 "$ROOT/daobuds-ble-watchdog.py" "$HOME/.local/bin/daobuds-ble-watchdog"
if command -v systemctl >/dev/null 2>&1; then
  run mkdir -p "$HOME/.config/systemd/user"
  run install -m 644 "$ROOT/systemd/daobuds-ble-watchdog.service" "$HOME/.config/systemd/user/daobuds-ble-watchdog.service"
  run systemctl --user daemon-reload || true
  run systemctl --user enable --now daobuds-ble-watchdog.service || true
else
  echo "      systemctl not found — run ~/.local/bin/daobuds-ble-watchdog manually"
fi

# Optional Android APK build & install via ADB
if [ "$INSTALL_ANDROID" -eq 1 ]; then
  echo "[+] Android ADB install requested"
  if command -v adb >/dev/null 2>&1 && [ -x "$ROOT/android/DaoBuds/gradlew" ]; then
    run sh -c "cd '$ROOT/android/DaoBuds' && ./gradlew assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk"
  else
    echo "    Android SDK / gradlew / adb not ready on this host. Download DaoBuds.apk from GitHub Releases or open android/DaoBuds in Android Studio."
  fi
fi

echo ""
echo "Installation finished!"
echo "  CLI      : daotws status | daotws stats | daotws mimi | daotws inspect-fw <file.bin>"
echo "  App      : daobuds"
echo "  Watchdog : systemctl --user status daobuds-ble-watchdog.service"
