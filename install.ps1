<#
.SYNOPSIS
    Automatic Windows installer for Redmagic DAO TWS Suite.

.DESCRIPTION
    1. Installs DAO Buds desktop controller to %LOCALAPPDATA%\DAOBuds\
    2. Creates Start Menu and Desktop shortcuts (or compiles standalone DAOBuds.exe with -BuildExe)
    3. Applies the QCC3086 USB dongle audio stability fix (fix-dao-dongle-windows.ps1) when run as Administrator

.EXAMPLE
    .\install.ps1
    .\install.ps1 -BuildExe
    .\install.ps1 -DisableTelephonyHid
    .\install.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [switch]$BuildExe,
    [switch]$DisableTelephonyHid,
    [switch]$SkipAudioFix,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Join-Path $env:LOCALAPPDATA "DAOBuds"
$StartMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\DAO Buds.lnk"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "DAO Buds.lnk"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function New-Shortcut($LinkPath, $TargetPath, $Arguments, $WorkingDir) {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($LinkPath)
    $sc.TargetPath = $TargetPath
    $sc.Arguments = $Arguments
    $sc.WorkingDirectory = $WorkingDir
    $sc.Description = "Redmagic Cyberbuds DAO TWS Controller"
    $sc.Save()
}

if ($Uninstall) {
    Write-Host "Uninstalling DAO Buds..." -ForegroundColor Yellow
    Remove-Item -Path $StartMenuShortcut, $DesktopShortcut -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-IsAdmin) {
        & (Join-Path $Root "windows\fix-dao-dongle-windows.ps1") -Restore
    } else {
        Write-Warning "Not Administrator: to restore USB dongle audio endpoints, run .\windows\fix-dao-dongle-windows.ps1 -Restore as Administrator."
    }
    Write-Host "Uninstall complete." -ForegroundColor Green
    exit 0
}

Write-Host "=== Redmagic DAO TWS Windows Installer ===" -ForegroundColor Cyan

# 1. Copy app files
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path (Join-Path $Root "windows\daobuds_win.py") -Destination $InstallDir -Force
Copy-Item -Path (Join-Path $Root "windows\fix-dao-dongle-windows.ps1") -Destination $InstallDir -Force
Copy-Item -Path (Join-Path $Root "PROTOCOL.md") -Destination $InstallDir -Force

# 2. Check Python 3 & optionally build .exe
$pyCmd = Get-Command pythonw -ErrorAction SilentlyContinue
if (-not $pyCmd) { $pyCmd = Get-Command python -ErrorAction SilentlyContinue }
if (-not $pyCmd) {
    Write-Warning "Python 3 not found on PATH. Install Python 3 from https://www.python.org/ or Microsoft Store, then re-run .\install.ps1."
} else {
    if ($BuildExe) {
        Write-Host "[1/3] Building standalone DAOBuds.exe via PyInstaller..." -ForegroundColor Cyan
        Push-Location $InstallDir
        python -m pip install --upgrade pyinstaller
        python -m PyInstaller --noconfirm --onefile --windowed --name DAOBuds daobuds_win.py
        $exePath = Join-Path $InstallDir "dist\DAOBuds.exe"
        Pop-Location
        New-Shortcut $StartMenuShortcut $exePath "" $InstallDir
        New-Shortcut $DesktopShortcut $exePath "" $InstallDir
    } else {
        Write-Host "[1/3] Creating Start Menu & Desktop shortcuts -> $InstallDir\daobuds_win.py" -ForegroundColor Cyan
        $scriptPath = Join-Path $InstallDir "daobuds_win.py"
        New-Shortcut $StartMenuShortcut $pyCmd.Source "`"$scriptPath`"" $InstallDir
        New-Shortcut $DesktopShortcut $pyCmd.Source "`"$scriptPath`"" $InstallDir
    }
}

# 3. Apply USB dongle audio stability fix if Administrator
if (-not $SkipAudioFix) {
    if (Test-IsAdmin) {
        Write-Host "[2/3] Applying QCC3086 USB dongle audio stability fix..." -ForegroundColor Cyan
        $fixArgs = @{}
        if ($DisableTelephonyHid) { $fixArgs["DisableTelephonyHid"] = $true }
        try {
            & (Join-Path $InstallDir "fix-dao-dongle-windows.ps1") @fixArgs
        } catch {
            Write-Warning "Dongle fix skipped (plug in dongle and run $InstallDir\fix-dao-dongle-windows.ps1 as Admin): $_"
        }
    } else {
        Write-Warning "[2/3] Skipping USB dongle audio fix (not Administrator). Re-run PowerShell as Administrator to fix robotic voice & audio freezes."
    }
}

Write-Host "`n[3/3] Done! Launch 'DAO Buds' from the Start Menu or Desktop." -ForegroundColor Green
