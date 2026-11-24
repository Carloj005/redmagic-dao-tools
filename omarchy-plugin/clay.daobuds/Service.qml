import QtQuick
import Quickshell
import Quickshell.Io

// Headless Omarchy service for Redmagic Cyberbuds DAO TWS (BH4010) & QCC3086 Dongle.
// Calls the installed `daobuds` binary (or local daotws.py fallback) to query live status.
Item {
  id: root

  property var shell: null
  property var settings: ({})

  readonly property string pluginId: "clay.daobuds"
  readonly property string fallbackCli: Quickshell.env("HOME") + "/.local/bin/daotws"
  readonly property string fallbackApp: Quickshell.env("HOME") + "/.local/bin/daobuds"

  property bool btConnected: false
  property bool dongleConnected: false
  property string firmware: ""
  property string dongleFirmware: ""
  property string primary: ""
  property int batteryLeft: -1
  property int batteryRight: -1
  property int batteryCase: -1
  property bool ancEnabled: false
  property int modeType: 2      // 1=game, 2=music
  property int codecMode: 1     // 1=normal, 2=lhdc, 3=aptx-lossless
  property string alertText: ""
  property bool busy: false
  property bool alertNotified: false

  function refresh() {
    if (!probeProc.running) probeProc.running = true
  }

  function toggleOverlay() {
    Quickshell.execDetached(["omarchy-shell", "shell", "toggle", root.pluginId, "{}"])
  }

  function openFullApp() {
    Quickshell.execDetached(["sh", "-c",
      "if command -v daobuds >/dev/null 2>&1; then exec daobuds; else exec \"$1\"; fi",
      "sh", root.fallbackApp])
  }

  function runCli(args) {
    if (cmdProc.running) return
    root.busy = true
    var fullCmd = ["sh", "-c",
      "if command -v daotws >/dev/null 2>&1; then exec daotws \"$@\"; else exec python3 \"$HOME/.local/bin/daotws\" \"$@\"; fi",
      "sh"].concat(args)
    cmdProc.command = fullCmd
    cmdProc.running = true
  }

  function setAnc(enabled) { runCli(["anc", "--state", enabled ? "on" : "off"]) }
  function setMode(mode, codec) { runCli(["mode", mode, "--codec", codec || "normal"]) }
  function applyBatterySaver() { runCli(["battery-saver"]) }

  function parseJson(raw) {
    var trimmed = (raw || "").trim()
    if (!trimmed.startsWith("{")) return
    try {
      var d = JSON.parse(trimmed)
      root.btConnected = !!d.bt_connected
      root.firmware = d.firmware || ""
      root.primary = d.primary || ""
      var bat = d.battery || {}
      root.batteryLeft = typeof bat.left === "number" ? bat.left : -1
      root.batteryRight = typeof bat.right === "number" ? bat.right : -1
      root.batteryCase = typeof bat.case === "number" ? bat.case : -1

      // Support both daobuds C++ JSON and daotws.py JSON schemas.
      if (typeof d.anc_enabled === "boolean") {
        root.ancEnabled = d.anc_enabled
      } else if (d.anc && typeof d.anc.enabled === "boolean") {
        root.ancEnabled = d.anc.enabled
      }

      if (typeof d.mode_type === "number") {
        root.modeType = d.mode_type
        root.codecMode = typeof d.codec_mode === "number" ? d.codec_mode : 1
      } else if (typeof d.mode === "string") {
        root.modeType = d.mode === "game" ? 1 : 2
        root.codecMode = d.codec_profile === "lhdc" ? 2 : (d.codec_profile === "aptx-lossless" ? 3 : 1)
      }

      var dg = d.dongle || {}
      root.dongleConnected = !!dg.connected
      root.dongleFirmware = dg.firmware || ""

      // Detect classic DAO TWS failure modes: stuck-in-case single bud or severe imbalance.
      var alert = ""
      if (root.btConnected) {
        if ((root.batteryLeft >= 0) !== (root.batteryRight >= 0)) {
          alert = "Solo un auricolare connesso (controlla pogo-pin nel case)"
        } else if (root.batteryLeft >= 0 && root.batteryRight >= 0 && Math.abs(root.batteryLeft - root.batteryRight) >= 20) {
          alert = "Batteria sbilanciata: L " + root.batteryLeft + "% / R " + root.batteryRight + "%"
        }
      }
      root.alertText = alert
      if (alert.length > 0 && !root.alertNotified) {
        root.alertNotified = true
        Quickshell.execDetached(["omarchy-notification-send", "--app-name", "DAO Buds", "-u", "normal", "-g", "󰋋", "DAO Buds", alert])
      } else if (alert.length === 0) {
        root.alertNotified = false
      }
    } catch (e) {
      // Ignore transient partial output.
    }
  }

  Component.onCompleted: refresh()

  Timer {
    interval: 25000
    repeat: true
    running: true
    onTriggered: root.refresh()
  }

  Process {
    id: probeProc
    command: ["sh", "-c",
      "if command -v daobuds >/dev/null 2>&1; then daobuds status; " +
      "elif [ -x \"$1\" ]; then \"$1\" status; " +
      "else python3 \"$2\" status --json; fi",
      "sh", root.fallbackApp, root.fallbackCli]
    stdout: StdioCollector {
      onStreamFinished: root.parseJson(text.slice(0, 8192))
    }
  }

  Process {
    id: cmdProc
    onExited: function(code, status) {
      root.busy = false
      root.refresh()
    }
  }

  IpcHandler {
    target: "daobuds"
    function toggle(): void { root.toggleOverlay() }
    function status(): string {
      return JSON.stringify({
        btConnected: root.btConnected,
        dongleConnected: root.dongleConnected,
        batteryLeft: root.batteryLeft,
        batteryRight: root.batteryRight,
        batteryCase: root.batteryCase,
        ancEnabled: root.ancEnabled,
        modeType: root.modeType,
        dongleFirmware: root.dongleFirmware,
        alertText: root.alertText
      })
    }
  }
}
