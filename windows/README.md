# DAO Buds for Windows

## 1. Fix Dongle Audio Lockups & Robotic Voice (`19d2:0616`)
Open PowerShell as **Administrator**:
```powershell
.\fix-dao-dongle-windows.ps1 -Status
.\fix-dao-dongle-windows.ps1
# If Windows sound cards still hang on plug-in, also disable HID Telephony (MI_00):
.\fix-dao-dongle-windows.ps1 -DisableTelephonyHid
# To revert everything:
.\fix-dao-dongle-windows.ps1 -Restore
```

## 2. Run the Desktop Controller App
Requires Python 3.9+ on Windows (uses built-in `tkinter` and native Windows Bluetooth RFCOMM sockets — zero `pip install` needed):
```powershell
python daobuds_win.py
```
Or build a standalone `.exe`:
```powershell
.\build-exe.ps1
```
