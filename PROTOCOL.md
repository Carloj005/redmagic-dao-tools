# Redmagic Cyberbuds DAO TWS (`BH4010`) — Protocol Specification

Reverse-engineered directly from live hardware (`DC:F0:90:50:6C:81`, USB `19d2:0616` / `19d2:0617`) and the official Goper APK (`cn.nubia.externdevice`).

## 1. Hardware Map

| Component | Chipset | Identifiers | Interfaces |
|---|---|---|---|
| Earbuds (L + R) | Qualcomm **QCC5171** (S5 Gen 2, Kalimba) | FCC `2A9QD-BH4010`, BT Company ID `0x08CA` (Nubia) | BR/EDR A2DP (SBC, AAC, aptX, LHDC v5, aptX Adaptive/Lossless), HFP, AVRCP, RFCOMM Ch 11 (`GAIA`) |
| USB-C 2.4 GHz Dongle | Qualcomm **QCC3086** (S3 Gen 2) | USB `19d2:0616`, `bcdDevice 29.67`, FCC `2A9QD-BH4010DONGLE` | If0: HID Consumer/Telephony; If1: Qualcomm HID Datalink / VM Upgrade (`0xFF00`, RID 1–9); If2–4: UAC 1.0 (48kHz/24-bit OUT, 16kHz/16-bit IN, `Synch Type: None`) |
| Desktop Base Station | 4-port USB 1.1 Hub (12 Mbps) + MT5805 Qi TX + LP6261A | USB `19d2:0617`, `bcdDevice 21.02` | Hub only on USB; knob/controls route through dongle |

## 2. BLE Advertisement (`ManufacturerData 0x08CA`)

Example captured live (verified against GAIA RFCOMM L=49%, R=61%, Case=31%):
```
01 01 dc f0 90 50 6c 81 01 06 02 00 02 31 3d 1f 00
```
- Bytes `2..7`: BR/EDR MAC address (`dc:f0:90:50:6c:81`)
- Bytes `13..15`: Battery levels: `[Left, Right, Case]` (`0xFF` = disconnected/unavailable; bit 7 `0x80` = charging flag, bits `0..6` = `0..100%`)

## 3. Bluetooth RFCOMM GAIA v3 Protocol (Channel 11)

Frame format (big-endian):
```
[0xFF] [0x03] [FLAGS=0x00] [LEN (1B)] [VENDOR_ID (2B)] [PDU_DESC (2B)] [PAYLOAD (LEN B)]
```
- `PDU_DESC = ((FEATURE_ID & 0x7F) << 9) | ((PDU_TYPE & 0x03) << 7) | (PDU_ID & 0x7F)`
  - `PDU_TYPE`: `0 = CMD`, `1 = NOTIF`, `2 = RESP`, `3 = ERR`
- Unsolicited banner on RFCOMM connect: `ff 03 00 05 28 28 00 00 53 50 50 4f 4b` (`vendor=0x2828`, `"SPPOK"`).
- Standard Vendor ID: `0x001D` (Qualcomm / QTIL).

### Supported Features on Firmware `9.0"(released)"`

| Feature ID | Name | Ver | Key Commands (PDU ID) |
|---|---|---|---|
| `0x00` | `BASIC` (Core) | v4 | `0x00` GET_API_VERSION, `0x01` GET_SUPPORTED_FEATURES, `0x03` GET_SERIAL, `0x04` GET_VARIANT, `0x05` GET_APP_VERSION |
| `0x01` | `EARBUD` | v3 | `0x00` IS_PRIMARY_L_OR_R (`0=L, 1=R`), `0x01` GET_SECONDARY_SERIAL |
| `0x05` | `MUSIC_PROCESSING` | v1 | `0x00` GET_EQ_STATE, `0x01` GET_AVAILABLE_PRESETS (`0..9, 0x3F`), `0x02` GET_EQ_SET, `0x03` SET_EQ_SET, `0x04` GET_USER_BANDS (`10`), `0x05` GET_USER_BAND_INFO, `0x06` SET_USER_BAND_GAINS |
| `0x06` | `UPGRADE` (DFU) | v2 | Qualcomm VM Upgrade Protocol (signed firmware images) |
| `0x07` | `HANDSET_SERVICE` | v1 | `0x00` SET_MULTIPOINT (`0 = SINGLE_POINT`, `1 = MULTI_POINT`) |
| `0x08` | `AUDIO_CURATION` | v6 | `0x00` GET_AC_STATE, `0x01` SET_AC_STATE, `0x02` GET_MODES_COUNT (`10`), `0x03` GET_CURRENT_MODE, `0x04` SET_CURRENT_MODE, `0x07` GET_TOGGLE_COUNT (`3`), `0x08` GET_TOGGLE_CFG, `0x09` SET_TOGGLE_CFG. **WARNING:** PDU `0x10` hangs firmware 9.0's GAIA RFCOMM task until BT reconnect! |
| `0x0C` | `STATISTICS` | v1 | `0x00` GET_ALL_CATEGORIES (`[last_cat u16be]` → `[more u8, cats...]`), `0x01` GET_ALL_STATISTICS_IN_CATEGORY (`[cat u16be, last_stat u8]` → `[more u8, cat u16be, {id u8, len u8, val...}...]`), `0x02` GET_STATISTIC_VALUES. Category `0x0001` (`STREAMING`): `0x01` codec, `0x02` lossless, `0x03` bitrate, `0x04` primary RSSI (dBm), `0x05` link quality, `0x06` transport, `0x08` primary SNR (dB). |
| `0x0D` | `BATTERY` | v1 | `0x00` GET_SUPPORTED_BATTERIES, `0x01` GET_BATTERY_LEVELS (`0=SINGLE, 1=LEFT, 2=RIGHT, 3=CASE`) |
| `0x0E` | **`CUSTOM` (Redmagic)** | v1 | See full table below |

### Feature `0x0E` (`CUSTOM`) Complete Command Table (`Vendor 0x001D`)

| Setting | GET PDU | SET PDU | Payload Format |
|---|---|---|---|
| **Mode / Codec** | `0x01` | `0x02` | 2 bytes: `[ModeType, MusicType]` — `ModeType`: `1=GAME_MODE`, `2=MUSIC_MODE`; `MusicType`: `0=EMPTY`, `1=NORMAL_MUSIC`, `2=LHDC_MUSIC`, `3=APXX_LOSSLESS_MUSIC` |
| **RGB Light Mode** | `0x03` | `0x04` | 4 bytes: `[mode, R, G, B]` — `mode`: `1=Static` (`[1,0,0,0]`=OFF), `2=Breathing`, `3=Rainbow` |
| **Light Hall** | `0x05` | `0x06` | 1 byte: `0=OFF`, `1=ON` |
| **Light Speed** | `0x07` | `0x08` | 1 byte |
| **Light Brightness** | `0x09` | `0x0A` | 1 byte |
| **Voice Language** | `0x0E` | `0x0F` | 1 byte |
| **In-Ear Detection** | `0x10` | `0x11` | 1 byte: `0=OFF`, `1=ON` |
| **Touch Controls** | `0x12` | `0x13` | 4 bytes: `[left_double, left_triple, right_double, right_triple]` — Actions: `0=CLOSE (off)`, `1=PLAY_OR_PAUSE`, `2=PLAY_PREV`, `3=PLAY_NEXT`, `4=SWITCH_ANC`, `5=GAME_MODE` |
| **Mimi Enable** | `0x14` | `0x15` | 1 byte |
| **Mimi Intensity** | `0x16` | `0x17` | 1 byte |
| **Mimi Preset Payload** | — | `0x18` | Payload bytes (MD5 sent to `0x1A`) |
| **Mimi Preset ID** | `0x19` | `0x1A` | 16-byte MD5 |
| **Mimi Tech Level** | `0x1B` | — | Read-only |
| **Mimi Clear Preset** | — | `0x1D` | Clear (0B payload). *Note: Global firmware 9.0 returns `ERR 0x01` (disabled); CN firmware enables Mimi DSP.* |

## 4. Offline Firmware Container Layout (`APPUHDR5` — Read-Only Validation)

Qualcomm VM Upgrade packages (for both `QCC5171` earbuds and `QCC3086` dongle) follow the signed `APPUHDR#` container format:
- **Header (`APPUHDR5`, 8B magic + 4B big-endian length):** 8B ASCII `device_variant`, `major`/`minor` (`u16be`), compatible upgrades table (`u16be` count + 4B pairs), `ps_config_version` (`u16be`), compatible PS configs table.
- **Partitions (`PARTDATA`, repeated):** 8B magic, 4B big-endian `length` (`payload + 4`), `partition_type` (`u16be`), `partition_num` (`u16be`), raw payload bytes.
- **Footer (`APPUPFTR`):** 8B magic, 4B big-endian signature length, cryptographic OEM signature verified by hardware Secure Boot (eFuse).

Use `daotws inspect-fw <file.bin>` (or `python3 fw_inspect.py <file.bin>`) to inspect headers, variants, versions, CRC-32 `file_id`, and SHA-256 digests offline without flashing.

## 5. USB Dongle HID Interface (`19d2:0616`, Interface 1, Usage Page `0xFF00`)

Verified live via `probe_dongle_version.py` using Qualcomm `qc-s5gen2` VM Upgrade protocol:
- **Dongle Firmware Version:** `major=1, minor=1, config=2` (`v1.1 config=2`).
- `SET_FEATURE` RID `3` (`[0x03, len, payload[61]]`): `0x02 0x00 0x00` Connect, `0x07 0x00 0x00` Disconnect.
- `WRITE` RID `5` (`[0x05, len, payload[253]]`): VM Upgrade opcodes (`0x19 0x00 0x00` = `HostVersionReq`).
- `READ` RID `6` (`[0x06, len, payload[11]]`): VM Upgrade responses (`0x1A` = `HostVersionCfm`).

| Report ID | Type | Size | Role |
|---|---|---|---|
| `1` / `2` | OUT / IN | 62 B / 16 B | Qualcomm HID Datalink Command / Response |
| `3` / `4` | FEATURE | 62 B / 62 B | Qualcomm VM Upgrade Handshake (`qc-s5gen2`) — **verified live** |
| `5` / `6` | OUT / IN | 254 B / 12 B | Qualcomm VM Upgrade Data / Response — **verified live** |
| `7` / `8` | OUT / IN | 446 B / 446 B | Qualcomm High-Bandwidth HID Datalink / GAIA / QACT |
| `9` | IN | 11 B | Qualcomm Status / Event Report |
