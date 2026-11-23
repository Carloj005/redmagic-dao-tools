# Build standalone DAOBuds.exe on Windows 10/11 (requires Python 3.10+ and pyinstaller)
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name DAOBuds daobuds_win.py
Write-Host "Built dist\DAOBuds.exe" -ForegroundColor Green
