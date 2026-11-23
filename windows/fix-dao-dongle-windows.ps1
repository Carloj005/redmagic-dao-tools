<#
.SYNOPSIS
    Fix Windows audio lockups, robotic voice, and stuttering for Redmagic DAO TWS USB Dongle (VID_19D2&PID_0616).

.DESCRIPTION
    Root causes verified from USB descriptors of the QCC3086 dongle (19d2:0616) & base hub (19d2:0617):
      1. Capture interface (16 kHz / 16-bit) and Playback (48 kHz / 24-bit) both declare Isochronous
         Synch Type = None on a 12 Mbps Full-Speed hub. Opening the 16 kHz mic forces bidirectional
         low-bandwidth voice mode -> robotic voice & stuttering.
      2. UAC 1.0 declares Sampling Frequency Control on single-rate endpoints + HID Telephony (MI_00),
         which can stall Windows audiosrv / other sound cards when communications devices switch.
      3. USB Selective Suspend can put the 12 Mbps hub/dongle to sleep and freeze the audio mixer.

    This script:
      - Disables the dongle's 16 kHz microphone endpoint (keeps 48 kHz/24-bit playback clean).
      - Disables USB Selective Suspend (EnhancedPowerManagementEnabled=0) for 19D2:0616 and 19D2:0617.
      - Optionally disables the HID Telephony/Headset interface (-DisableTelephonyHid).
      - Fully reversible with -Restore.

.EXAMPLE
    .\fix-dao-dongle-windows.ps1 -Status
    .\fix-dao-dongle-windows.ps1
    .\fix-dao-dongle-windows.ps1 -DisableTelephonyHid
    .\fix-dao-dongle-windows.ps1 -Restore
#>

[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Restore,
    [switch]$DisableTelephonyHid
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-DaoPnpDevices {
    Get-PnpDevice | Where-Object {
        $_.InstanceId -match "VID_19D2&PID_061[67]" -or
        ($_.FriendlyName -match "DAO TWS" -and $_.Class -in @("AudioEndpoint", "MEDIA", "HIDClass", "USB"))
    }
}

$devices = @(Get-DaoPnpDevices)
if ($devices.Count -eq 0) {
    Write-Warning "No Redmagic DAO TWS dongle (19D2:0616 / 19D2:0617) detected. Plug it in and retry."
    exit 1
}

if ($Status) {
    Write-Host "`n=== Redmagic DAO TWS PnP Devices ===" -ForegroundColor Cyan
    $devices | Select-Object Status, Class, FriendlyName, InstanceId | Format-Table -AutoSize
    exit 0
}

if (-not (Test-IsAdmin)) {
    Write-Error "Run PowerShell as Administrator to apply or restore device changes."
    exit 1
}

# 1. Identify the buggy 16 kHz microphone AudioEndpoint(s) belonging to DAO TWS
$micEndpoints = @(Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue | Where-Object {
    $_.FriendlyName -match "DAO TWS" -and (
        $_.InstanceId -match "0\.0\.1\." -or
        $_.FriendlyName -match "(Microphone|Microfono|Headset|Input|Capture)"
    )
})

# 2. Identify HID Telephony / Consumer interface (MI_00) if requested
$hidTelephony = @($devices | Where-Object {
    $_.Class -eq "HIDClass" -and $_.InstanceId -match "VID_19D2&PID_0616&MI_00"
})

if ($Restore) {
    Write-Host "Restoring Redmagic DAO TWS devices to Windows defaults..." -ForegroundColor Yellow
    foreach ($d in ($micEndpoints + $hidTelephony)) {
        if ($d.Status -ne "OK") {
            Write-Host "  Enabling: $($d.FriendlyName) [$($d.InstanceId)]"
            Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
        }
    }
    foreach ($id in @("VID_19D2&PID_0616", "VID_19D2&PID_0617")) {
        Get-ChildItem "HKLM:\SYSTEM\CurrentControlSet\Enum\USB\$id*" -ErrorAction SilentlyContinue | ForEach-Object {
            Get-ChildItem $_.PSPath -ErrorAction SilentlyContinue | ForEach-Object {
                $dp = Join-Path $_.PSPath "Device Parameters"
                if (Test-Path $dp) {
                    Remove-ItemProperty -Path $dp -Name "EnhancedPowerManagementEnabled" -ErrorAction SilentlyContinue
                }
            }
        }
    }
    Write-Host "Restored. Unplug and replug the dongle." -ForegroundColor Green
    exit 0
}

Write-Host "Applying Redmagic DAO TWS Windows audio stability fixes..." -ForegroundColor Cyan

if ($micEndpoints.Count -eq 0) {
    Write-Warning "Could not auto-match the 16 kHz capture endpoint by name; run with -Status to inspect InstanceIds."
} else {
    foreach ($mic in $micEndpoints) {
        Write-Host "  Disabling 16 kHz Capture endpoint: $($mic.FriendlyName) [$($mic.InstanceId)]"
        Disable-PnpDevice -InstanceId $mic.InstanceId -Confirm:$false
    }
}

if ($DisableTelephonyHid) {
    foreach ($h in $hidTelephony) {
        Write-Host "  Disabling HID Telephony interface (MI_00): $($h.FriendlyName) [$($h.InstanceId)]"
        Disable-PnpDevice -InstanceId $h.InstanceId -Confirm:$false
    }
}

# Disable USB Selective Suspend on 19D2:0616 (dongle) and 19D2:0617 (12 Mbps hub)
foreach ($id in @("VID_19D2&PID_0616", "VID_19D2&PID_0617")) {
    Get-ChildItem "HKLM:\SYSTEM\CurrentControlSet\Enum\USB\$id*" -ErrorAction SilentlyContinue | ForEach-Object {
        Get-ChildItem $_.PSPath -ErrorAction SilentlyContinue | ForEach-Object {
            $dp = Join-Path $_.PSPath "Device Parameters"
            if (Test-Path $dp) {
                Set-ItemProperty -Path $dp -Name "EnhancedPowerManagementEnabled" -Type DWord -Value 0
                Write-Host "  Disabled USB selective suspend for $($_.PSChildName)"
            }
        }
    }
}

Write-Host "`nDone! Unplug and replug the dongle (or restart Windows Audio service):" -ForegroundColor Green
Write-Host "  Restart-Service audiosrv -Force"
Write-Host "To undo at any time: .\fix-dao-dongle-windows.ps1 -Restore"
