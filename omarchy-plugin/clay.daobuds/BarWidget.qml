import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "clay.daobuds"

  property var svc: null

  function resolveSvc() {
    if (!svc && bar && bar.shell) svc = bar.shell.serviceFor(moduleName)
    return svc
  }

  onBarChanged: resolveSvc()
  Component.onCompleted: resolveSvc()

  Timer {
    interval: 400
    repeat: true
    running: !root.svc
    onTriggered: root.resolveSvc()
  }

  function pillText() {
    if (!root.svc) return "󰋋"
    var showBat = root.setting("showBattery", true)
    if (root.svc.btConnected) {
      var warn = root.svc.alertText.length > 0 ? " !" : ""
      if (!showBat) return "󰋋" + warn
      var l = root.svc.batteryLeft >= 0 ? root.svc.batteryLeft : "--"
      var r = root.svc.batteryRight >= 0 ? root.svc.batteryRight : "--"
      return "󰋋 " + l + "/" + r + warn
    }
    if (root.svc.dongleConnected) return showBat ? "󰋋 USB" : "󰋋"
    return "󰋐"
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.pillText()
    horizontalMargin: 7.5
    onPressed: function(b) {
      var s = root.resolveSvc()
      if (s) s.toggleOverlay()
    }
  }
}
