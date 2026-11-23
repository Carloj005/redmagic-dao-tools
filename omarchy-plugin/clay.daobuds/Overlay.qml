import Quickshell
import Quickshell.Wayland
import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  property var shell: null
  property var manifest: null
  property var service: null
  property bool opened: false

  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color border: Color.menu.border
  property var borderSpec: Border.surfaceSpec("menu", "border", border, Math.max(1, Style.space(2)))
  property color scrim: Color.menu.scrim
  property color selectedBackground: Color.menu.selectedBackground
  property color selectedText: Color.menu.selectedText
  readonly property int cornerRadius: Style.cornerRadius
  property string fontFamily: Style.font.menuFamily
  property int contentMargin: Style.spacing.panelPadding
  property int cardWidth: Math.min(Style.space(420), panel.width - Style.gapsOut * 2)

  function open(payloadJson) {
    root.opened = true
    if (root.service) root.service.refresh()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() { root.opened = false }

  function dismiss() {
    root.opened = false
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide((root.manifest && root.manifest.id) || "clay.daobuds")
  }

  function toggle() {
    if (root.opened) root.dismiss()
    else root.open("{}")
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "clay-daobuds"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle { anchors.fill: parent; color: root.scrim }
    MouseArea { anchors.fill: parent; onClicked: root.dismiss() }

    BorderSurface {
      id: card
      width: root.cardWidth
      height: content.height + card.contentTopInset + card.contentBottomInset
      radius: root.cornerRadius
      anchors.centerIn: parent
      color: root.background
      borderSpec: root.borderSpec
      padding: root.contentMargin

      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true
        Keys.onEscapePressed: root.dismiss()
        Keys.onPressed: function(event) {
          if (!root.service) return
          if (event.key === Qt.Key_R) { root.service.refresh(); event.accepted = true }
          else if (event.key === Qt.Key_O) { root.dismiss(); root.service.openFullApp(); event.accepted = true }
          else if (root.service.btConnected) {
            if (event.key === Qt.Key_A) { root.service.setAnc(!root.service.ancEnabled); event.accepted = true }
            else if (event.key === Qt.Key_G) { root.service.setMode("game", "normal"); event.accepted = true }
            else if (event.key === Qt.Key_M) { root.service.setMode("music", "normal"); event.accepted = true }
            else if (event.key === Qt.Key_B) { root.service.applyBatterySaver(); event.accepted = true }
          }
        }

        Column {
          id: content
          anchors.top: parent.top
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.topMargin: card.contentTopInset
          anchors.leftMargin: card.contentLeftInset
          anchors.rightMargin: card.contentRightInset
          spacing: Style.spacing.md

          // Header
          Item {
            width: parent.width
            height: hdrTitle.implicitHeight
            Text {
              id: hdrTitle
              anchors.left: parent.left
              text: "DAO Buds"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.heading
              font.bold: true
            }
            Text {
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              text: root.service && root.service.btConnected
                ? "BT · FW " + root.service.firmware
                : (root.service && root.service.dongleConnected ? "Dongle · FW " + root.service.dongleFirmware : "Disconnesso")
              color: root.foreground
              opacity: 0.7
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
            }
          }

          // Alert banner
          Rectangle {
            visible: root.service && root.service.alertText.length > 0
            width: parent.width
            height: alertTxt.implicitHeight + 12
            radius: Math.min(4, root.cornerRadius)
            color: "#332211"
            border.color: "#faad14"
            border.width: 1
            Text {
              id: alertTxt
              anchors.fill: parent
              anchors.margins: 6
              text: root.service ? root.service.alertText : ""
              color: "#ffd666"
              wrapMode: Text.WordWrap
              font.family: root.fontFamily
              font.pixelSize: Style.font.small
            }
          }

          // Battery row
          Row {
            width: parent.width
            spacing: 8
            Repeater {
              model: [
                { lbl: "Sinistro", val: root.service ? root.service.batteryLeft : -1 },
                { lbl: "Destro", val: root.service ? root.service.batteryRight : -1 },
                { lbl: "Case", val: root.service ? root.service.batteryCase : -1 }
              ]
              delegate: Rectangle {
                required property var modelData
                width: (parent.width - 16) / 3
                height: 52
                radius: Math.min(4, root.cornerRadius)
                color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.06)
                Column {
                  anchors.centerIn: parent
                  spacing: 2
                  Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: modelData.lbl
                    color: root.foreground
                    opacity: 0.65
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.small
                  }
                  Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: modelData.val >= 0 ? (modelData.val + "%") : "--"
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    font.bold: true
                  }
                }
              }
            }
          }

          // Quick BT controls
          Row {
            width: parent.width
            spacing: 8
            visible: root.service && root.service.btConnected
            Repeater {
              model: [
                { lbl: (root.service && root.service.ancEnabled ? "ANC ON" : "ANC OFF"), active: root.service && root.service.ancEnabled, act: "anc" },
                { lbl: "Game", active: root.service && root.service.modeType === 1, act: "game" },
                { lbl: "Music", active: root.service && root.service.modeType === 2, act: "music" },
                { lbl: "Eco", active: false, act: "eco" }
              ]
              delegate: Rectangle {
                required property var modelData
                width: (parent.width - 24) / 4
                height: 34
                radius: Math.min(4, root.cornerRadius)
                color: modelData.active ? root.selectedBackground : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.08)
                Text {
                  anchors.centerIn: parent
                  text: modelData.lbl
                  color: modelData.active ? root.selectedText : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.small
                  font.bold: modelData.active
                }
                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (!root.service) return
                    if (modelData.act === "anc") root.service.setAnc(!root.service.ancEnabled)
                    else if (modelData.act === "game") root.service.setMode("game", "normal")
                    else if (modelData.act === "music") root.service.setMode("music", "normal")
                    else if (modelData.act === "eco") root.service.applyBatterySaver()
                  }
                }
              }
            }
          }

          // Footer: Open Full App button + key hint
          Row {
            width: parent.width
            spacing: 8
            Rectangle {
              width: parent.width * 0.65
              height: 34
              radius: Math.min(4, root.cornerRadius)
              color: root.selectedBackground
              Text {
                anchors.centerIn: parent
                text: "Apri DAO Buds (O)"
                color: root.selectedText
                font.family: root.fontFamily
                font.pixelSize: Style.font.small
                font.bold: true
              }
              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: { root.dismiss(); if (root.service) root.service.openFullApp() }
              }
            }
            Rectangle {
              width: parent.width * 0.35 - 8
              height: 34
              radius: Math.min(4, root.cornerRadius)
              color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.08)
              Text {
                anchors.centerIn: parent
                text: "Aggiorna (R)"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.small
              }
              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: if (root.service) root.service.refresh()
              }
            }
          }
        }
      }
    }
  }
}
