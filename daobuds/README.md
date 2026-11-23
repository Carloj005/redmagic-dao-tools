# DAO Buds (Omarchy App)

Native C++ / Qt Quick desktop controller for **Redmagic Cyberbuds DAO TWS (`BH4010`)** and the **QCC3086 USB Dongle (`19d2:0616`)**, following Omarchy's live theme, Hyprland rounding, and language settings (`en`, `it`).

## Build, Test & Install

```sh
./bin/build      # Builds build/daobuds
./bin/test       # Runs offscreen Qt Test suite
./bin/install    # Builds & installs Arch package (adds DAO Buds to launcher)
```

Headless CLI mode (used by the Omarchy shell plugin & scripts):
```sh
daobuds status
```

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` / `R` | Refresh Bluetooth & USB dongle status |
| `1` – `4` | Switch tabs (Audio & ANC, Touch, EQ, Hardware) |
| `B` | Apply 1-click Battery Saver & Stability preset |
| `?` | Toggle keyboard shortcut help overlay |
| `Q` | Quit |
