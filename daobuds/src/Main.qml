import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: 980
    height: 700
    minimumWidth: 700
    minimumHeight: 520
    visible: true
    title: qsTr("DAO Buds")
    color: "#0e0e10"

    Material.theme: Material.Dark
    Material.accent: theme.accent
    Material.roundedScale: theme.radius

    property bool helpVisible: false
    property int currentTab: 0

    // Local editing buffers synced whenever backend state refreshes.
    property int editLD: backend.touchLD
    property int editLT: backend.touchLT
    property int editRD: backend.touchRD
    property int editRT: backend.touchRT
    property int editLedMode: backend.ledMode
    property int editLedR: backend.ledR
    property int editLedG: backend.ledG
    property int editLedB: backend.ledB

    Connections {
        target: backend
        function onStateChanged() {
            win.editLD = backend.touchLD
            win.editLT = backend.touchLT
            win.editRD = backend.touchRD
            win.editRT = backend.touchRT
            win.editLedMode = backend.ledMode
            win.editLedR = backend.ledR
            win.editLedG = backend.ledG
            win.editLedB = backend.ledB
        }
    }

    readonly property var touchModel: [
        qsTr("Off"),
        qsTr("Play / Pause"),
        qsTr("Previous Track"),
        qsTr("Next Track"),
        qsTr("Switch ANC"),
        qsTr("Game Mode")
    ]

    Shortcut { sequence: "?"; context: Qt.ApplicationShortcut; onActivated: win.helpVisible = !win.helpVisible }
    Shortcut { sequence: "Escape"; context: Qt.ApplicationShortcut; onActivated: win.helpVisible = false }
    Shortcut { sequence: "Q"; context: Qt.ApplicationShortcut; onActivated: Qt.quit() }
    Shortcut { sequence: "Space"; context: Qt.ApplicationShortcut; onActivated: backend.refresh() }
    Shortcut { sequence: "R"; context: Qt.ApplicationShortcut; onActivated: backend.refresh() }
    Shortcut { sequence: "1"; context: Qt.ApplicationShortcut; onActivated: win.currentTab = 0 }
    Shortcut { sequence: "2"; context: Qt.ApplicationShortcut; onActivated: win.currentTab = 1 }
    Shortcut { sequence: "3"; context: Qt.ApplicationShortcut; onActivated: win.currentTab = 2 }
    Shortcut { sequence: "4"; context: Qt.ApplicationShortcut; onActivated: win.currentTab = 3 }
    Shortcut { sequence: "5"; context: Qt.ApplicationShortcut; onActivated: win.currentTab = 4 }
    Shortcut { sequence: "B"; context: Qt.ApplicationShortcut; onActivated: if (backend.btConnected) backend.applyBatterySaver() }

    function batteryColor(pct) {
        if (pct < 0) return "#555860"
        if (pct <= 20) return "#ff4d4f"
        if (pct <= 45) return "#faad14"
        return theme.accent
    }

    function formatHz(hz) {
        return hz >= 1000 ? (hz / 1000) + "k" : String(hz)
    }

    Item {
        anchors.fill: parent
        LayoutMirroring.enabled: Qt.application.layoutDirection === Qt.RightToLeft
        LayoutMirroring.childrenInherit: true

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 14

            // --- Header bar ---
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                ColumnLayout {
                    spacing: 2
                    Label {
                        text: qsTr("DAO Buds")
                        font.pixelSize: 22
                        font.bold: true
                        color: "#f4f4f6"
                    }
                    RowLayout {
                        spacing: 10
                        Rectangle {
                            radius: Math.min(4, theme.radius)
                            color: backend.btConnected ? "#193524" : "#25252b"
                            border.color: backend.btConnected ? "#38c172" : "#3a3a44"
                            border.width: 1
                            implicitWidth: btLabel.implicitWidth + 14
                            implicitHeight: 22
                            Label {
                                id: btLabel
                                anchors.centerIn: parent
                                text: qsTr("Bluetooth") + ": " + (backend.btConnected
                                    ? (backend.firmware.length > 0 ? "FW " + backend.firmware : qsTr("Connected"))
                                    : qsTr("Disconnected"))
                                font.pixelSize: 11
                                color: backend.btConnected ? "#7ef0a6" : "#a0a0aa"
                            }
                        }
                        Rectangle {
                            radius: Math.min(4, theme.radius)
                            color: backend.dongleConnected ? "#172b3a" : "#25252b"
                            border.color: backend.dongleConnected ? theme.accent : "#3a3a44"
                            border.width: 1
                            implicitWidth: dgLabel.implicitWidth + 14
                            implicitHeight: 22
                            Label {
                                id: dgLabel
                                anchors.centerIn: parent
                                text: qsTr("USB Dongle") + ": " + (backend.dongleConnected
                                    ? (backend.dongleFirmware.length > 0 ? "FW " + backend.dongleFirmware : qsTr("Connected"))
                                    : qsTr("Disconnected"))
                                font.pixelSize: 11
                                color: backend.dongleConnected ? "#e6f2ff" : "#a0a0aa"
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                Button {
                    text: qsTr("Battery Saver")
                    enabled: backend.btConnected && !backend.busy
                    highlighted: true
                    Material.accent: theme.accent
                    Material.roundedScale: theme.radius
                    onClicked: backend.applyBatterySaver()
                }
                Button {
                    text: qsTr("Refresh")
                    enabled: !backend.busy
                    Material.roundedScale: theme.radius
                    onClicked: backend.refresh()
                }
            }

            // --- Alert banner (battery imbalance / stuck bud / udev permission) ---
            Rectangle {
                Layout.fillWidth: true
                visible: backend.alertMessage.length > 0
                color: "#332211"
                border.color: "#faad14"
                border.width: 1
                radius: theme.radius
                implicitHeight: alertLbl.implicitHeight + 16

                Label {
                    id: alertLbl
                    anchors.fill: parent
                    anchors.margins: 8
                    text: backend.alertMessage
                    color: "#ffd666"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }

            // --- Battery cards (Left / Right / Case) ---
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Repeater {
                    model: [
                        { label: qsTr("Left"), pct: backend.batteryLeft, isPrimary: backend.primary === "left" },
                        { label: qsTr("Right"), pct: backend.batteryRight, isPrimary: backend.primary === "right" },
                        { label: qsTr("Case"), pct: backend.batteryCase, isPrimary: false }
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 74
                        radius: theme.radius
                        color: "#16161b"
                        border.color: "#282832"
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 6

                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    text: modelData.label + (modelData.isPrimary ? " (" + qsTr("Primary") + ")" : "")
                                    color: "#b4b4c0"
                                    font.pixelSize: 12
                                }
                                Item { Layout.fillWidth: true }
                                Label {
                                    text: modelData.pct >= 0 ? (modelData.pct + "%") : "--"
                                    color: "#f4f4f6"
                                    font.pixelSize: 16
                                    font.bold: true
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 6
                                radius: Math.min(3, theme.radius)
                                color: "#262630"
                                Rectangle {
                                    width: modelData.pct >= 0 ? parent.width * Math.min(1, modelData.pct / 100.0) : 0
                                    height: parent.height
                                    radius: parent.radius
                                    color: win.batteryColor(modelData.pct)
                                }
                            }
                        }
                    }
                }
            }

            // --- Tab bar ---
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Repeater {
                    model: [qsTr("Audio & ANC"), qsTr("Touch"), qsTr("EQ"), qsTr("Hardware"), qsTr("Telemetry & Mimi")]
                    delegate: Button {
                        required property string modelData
                        required property int index
                        text: (index + 1) + ". " + modelData
                        Layout.fillWidth: true
                        highlighted: win.currentTab === index
                        Material.accent: theme.accent
                        Material.roundedScale: theme.radius
                        onClicked: win.currentTab = index
                    }
                }
            }

            // --- Bluetooth offline hint ---
            Rectangle {
                Layout.fillWidth: true
                visible: !backend.btConnected
                color: "#16161b"
                border.color: "#2c2c38"
                border.width: 1
                radius: theme.radius
                implicitHeight: btHint.implicitHeight + 16
                Label {
                    id: btHint
                    anchors.fill: parent
                    anchors.margins: 8
                    text: qsTr("Connect DAO TWS via Bluetooth to change earbud settings. USB dongle audio fix runs via WirePlumber.")
                    color: "#a8a8b8"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }

            // --- Tab pages ---
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: win.currentTab

                // TAB 0: AUDIO & ANC
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: win.width - 42
                        spacing: 14
                        enabled: backend.btConnected && !backend.busy

                        Rectangle {
                            Layout.fillWidth: true
                            radius: theme.radius
                            color: "#16161b"
                            border.color: "#282832"
                            implicitHeight: modeCol.implicitHeight + 24

                            ColumnLayout {
                                id: modeCol
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 10

                                Label { text: qsTr("Mode & Codec"); font.pixelSize: 15; font.bold: true; color: "#f4f4f6" }
                                RowLayout {
                                    spacing: 10
                                    Button {
                                        text: qsTr("Music Mode")
                                        highlighted: backend.modeType === 2
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setModeAndCodec(2, backend.codecMode > 0 ? backend.codecMode : 1)
                                    }
                                    Button {
                                        text: qsTr("Game Mode")
                                        highlighted: backend.modeType === 1
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setModeAndCodec(1, 0)
                                    }
                                }
                                RowLayout {
                                    spacing: 10
                                    Label { text: qsTr("Codec Profile"); color: "#b4b4c0"; font.pixelSize: 13 }
                                    Button {
                                        text: qsTr("Normal (SBC/AAC/aptX)")
                                        highlighted: backend.modeType === 2 && backend.codecMode === 1
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setModeAndCodec(2, 1)
                                    }
                                    Button {
                                        text: qsTr("LHDC 5.0")
                                        highlighted: backend.modeType === 2 && backend.codecMode === 2
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setModeAndCodec(2, 2)
                                    }
                                    Button {
                                        text: qsTr("aptX Lossless")
                                        highlighted: backend.modeType === 2 && backend.codecMode === 3
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setModeAndCodec(2, 3)
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: theme.radius
                            color: "#16161b"
                            border.color: "#282832"
                            implicitHeight: ancCol.implicitHeight + 24

                            ColumnLayout {
                                id: ancCol
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 10

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: qsTr("Active Noise Cancellation"); font.pixelSize: 15; font.bold: true; color: "#f4f4f6" }
                                    Item { Layout.fillWidth: true }
                                    Switch {
                                        text: qsTr("ANC Enabled")
                                        checked: backend.ancEnabled
                                        onToggled: backend.setAncEnabled(checked)
                                    }
                                }

                                RowLayout {
                                    spacing: 10
                                    Label { text: qsTr("ANC Mode"); color: "#b4b4c0"; font.pixelSize: 13 }
                                    ComboBox {
                                        model: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(function(m) { return qsTr("Mode %1").arg(m) })
                                        currentIndex: Math.max(0, Math.min(9, backend.ancMode - 1))
                                        onActivated: function(idx) { backend.setAncMode(idx + 1) }
                                    }
                                }

                                Label { text: qsTr("Touch ANC Toggle Slots"); color: "#b4b4c0"; font.pixelSize: 13 }
                                RowLayout {
                                    spacing: 12
                                    Repeater {
                                        model: [
                                            { slot: 1, val: backend.ancToggle1 },
                                            { slot: 2, val: backend.ancToggle2 },
                                            { slot: 3, val: backend.ancToggle3 }
                                        ]
                                        delegate: ColumnLayout {
                                            required property var modelData
                                            spacing: 4
                                            Label { text: qsTr("Slot %1").arg(modelData.slot); color: "#90909e"; font.pixelSize: 12 }
                                            ComboBox {
                                                model: [qsTr("Disabled"), qsTr("Mode %1").arg(1), qsTr("Mode %1").arg(2),
                                                        qsTr("Mode %1").arg(3), qsTr("Mode %1").arg(4), qsTr("Mode %1").arg(5),
                                                        qsTr("Mode %1").arg(6), qsTr("Mode %1").arg(7), qsTr("Mode %1").arg(8),
                                                        qsTr("Mode %1").arg(9), qsTr("Mode %1").arg(10)]
                                                currentIndex: modelData.val < 0 ? 0 : Math.min(10, modelData.val)
                                                onActivated: function(idx) { backend.setAncToggleSlot(modelData.slot, idx === 0 ? -1 : idx) }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // TAB 1: TOUCH CONTROLS
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: win.width - 42
                        spacing: 14
                        enabled: backend.btConnected && !backend.busy

                        Rectangle {
                            Layout.fillWidth: true
                            radius: theme.radius
                            color: "#16161b"
                            border.color: "#282832"
                            implicitHeight: touchCol.implicitHeight + 24

                            ColumnLayout {
                                id: touchCol
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 14

                                Label { text: qsTr("Touch Controls"); font.pixelSize: 15; font.bold: true; color: "#f4f4f6" }

                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 2
                                    columnSpacing: 20
                                    rowSpacing: 12

                                    // Left column
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        Label { text: qsTr("Left Earbud"); font.pixelSize: 14; font.bold: true; color: theme.accent }
                                        Label { text: qsTr("Double Tap"); color: "#b4b4c0"; font.pixelSize: 12 }
                                        ComboBox {
                                            Layout.fillWidth: true
                                            model: win.touchModel
                                            currentIndex: Math.max(0, Math.min(5, win.editLD))
                                            onActivated: function(idx) { win.editLD = idx }
                                        }
                                        Label { text: qsTr("Triple Tap"); color: "#b4b4c0"; font.pixelSize: 12 }
                                        ComboBox {
                                            Layout.fillWidth: true
                                            model: win.touchModel
                                            currentIndex: Math.max(0, Math.min(5, win.editLT))
                                            onActivated: function(idx) { win.editLT = idx }
                                        }
                                    }

                                    // Right column
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        Label { text: qsTr("Right Earbud"); font.pixelSize: 14; font.bold: true; color: theme.accent }
                                        Label { text: qsTr("Double Tap"); color: "#b4b4c0"; font.pixelSize: 12 }
                                        ComboBox {
                                            Layout.fillWidth: true
                                            model: win.touchModel
                                            currentIndex: Math.max(0, Math.min(5, win.editRD))
                                            onActivated: function(idx) { win.editRD = idx }
                                        }
                                        Label { text: qsTr("Triple Tap"); color: "#b4b4c0"; font.pixelSize: 12 }
                                        ComboBox {
                                            Layout.fillWidth: true
                                            model: win.touchModel
                                            currentIndex: Math.max(0, Math.min(5, win.editRT))
                                            onActivated: function(idx) { win.editRT = idx }
                                        }
                                    }
                                }

                                RowLayout {
                                    Item { Layout.fillWidth: true }
                                    Button {
                                        text: qsTr("Save Touch Mapping")
                                        highlighted: true
                                        Material.accent: theme.accent
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setTouchControls(win.editLD, win.editLT, win.editRD, win.editRT)
                                    }
                                }
                            }
                        }
                    }
                }

                // TAB 2: 10-BAND PARAMETRIC EQ
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: win.width - 42
                        spacing: 14
                        enabled: backend.btConnected && !backend.busy

                        Rectangle {
                            Layout.fillWidth: true
                            radius: theme.radius
                            color: "#16161b"
                            border.color: "#282832"
                            implicitHeight: eqCol.implicitHeight + 24

                            ColumnLayout {
                                id: eqCol
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 12

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: qsTr("10-Band Parametric EQ"); font.pixelSize: 15; font.bold: true; color: "#f4f4f6" }
                                    Item { Layout.fillWidth: true }
                                    Label { text: qsTr("Preset"); color: "#b4b4c0"; font.pixelSize: 13 }
                                    ComboBox {
                                        model: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", qsTr("Custom User EQ")]
                                        currentIndex: backend.eqPreset === 63 ? 10 : Math.max(0, Math.min(9, backend.eqPreset))
                                        onActivated: function(idx) { backend.setEqPreset(idx === 10 ? 63 : idx) }
                                    }
                                    Button {
                                        text: qsTr("Reset Flat")
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.resetEqFlat()
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Repeater {
                                        model: 10
                                        delegate: ColumnLayout {
                                            required property int index
                                            Layout.fillWidth: true
                                            spacing: 4
                                            readonly property double bandVal: index < backend.eqGains.length ? backend.eqGains[index] : 0.0
                                            readonly property int bandHz: index < backend.eqFreqs.length ? backend.eqFreqs[index] : 0

                                            Label {
                                                Layout.alignment: Qt.AlignHCenter
                                                text: (bandSlider.value >= 0 ? "+" : "") + bandSlider.value.toFixed(1)
                                                font.pixelSize: 11
                                                color: "#d4d4dc"
                                            }
                                            Slider {
                                                id: bandSlider
                                                Layout.alignment: Qt.AlignHCenter
                                                orientation: Qt.Vertical
                                                implicitHeight: 190
                                                from: -12.0
                                                to: 12.0
                                                stepSize: 0.5
                                                value: bandVal
                                                onMoved: {}
                                                onPressedChanged: {
                                                    if (!pressed) backend.setEqBand(index, value)
                                                }
                                            }
                                            Label {
                                                Layout.alignment: Qt.AlignHCenter
                                                text: win.formatHz(bandHz)
                                                font.pixelSize: 11
                                                color: "#90909e"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // TAB 3: HARDWARE, RGB & STABILITY
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: win.width - 42
                        spacing: 14
                        enabled: backend.btConnected && !backend.busy

                        Rectangle {
                            Layout.fillWidth: true
                            radius: theme.radius
                            color: "#16161b"
                            border.color: "#282832"
                            implicitHeight: ledCol.implicitHeight + 24

                            ColumnLayout {
                                id: ledCol
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 10

                                Label { text: qsTr("RGB Lighting"); font.pixelSize: 15; font.bold: true; color: "#f4f4f6" }
                                RowLayout {
                                    spacing: 8
                                    Repeater {
                                        model: [qsTr("Off"), qsTr("Static"), qsTr("Breathing"), qsTr("Rainbow")]
                                        delegate: Button {
                                            required property string modelData
                                            required property int index
                                            text: modelData
                                            highlighted: win.editLedMode === index
                                            Material.roundedScale: theme.radius
                                            onClicked: {
                                                win.editLedMode = index
                                                backend.setLedMode(index, win.editLedR, win.editLedG, win.editLedB)
                                            }
                                        }
                                    }
                                    Item { Layout.fillWidth: true }
                                    Switch {
                                        text: qsTr("Case Hall LED")
                                        checked: backend.ledHall
                                        onToggled: backend.setLedHall(checked)
                                    }
                                }

                                RowLayout {
                                    spacing: 8
                                    Repeater {
                                        model: [
                                            { r: 0, g: 255, b: 255 },
                                            { r: 255, g: 40, b: 80 },
                                            { r: 120, g: 0, b: 255 },
                                            { r: 0, g: 255, b: 120 },
                                            { r: 255, g: 200, b: 0 },
                                            { r: 255, g: 255, b: 255 }
                                        ]
                                        delegate: Rectangle {
                                            required property var modelData
                                            width: 28; height: 28
                                            radius: 14
                                            color: Qt.rgba(modelData.r / 255, modelData.g / 255, modelData.b / 255, 1)
                                            border.color: "#ffffff"
                                            border.width: (win.editLedR === modelData.r && win.editLedG === modelData.g && win.editLedB === modelData.b) ? 2 : 0
                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    win.editLedR = modelData.r
                                                    win.editLedG = modelData.g
                                                    win.editLedB = modelData.b
                                                    if (win.editLedMode === 0) win.editLedMode = 1
                                                    backend.setLedMode(win.editLedMode, win.editLedR, win.editLedG, win.editLedB)
                                                }
                                            }
                                        }
                                    }
                                    Item { Layout.fillWidth: true }
                                    Label { text: qsTr("Brightness"); color: "#b4b4c0"; font.pixelSize: 12 }
                                    SpinBox {
                                        from: 0; to: 10; value: backend.ledBrightness
                                        onValueModified: backend.setLedBrightness(value)
                                    }
                                    Label { text: qsTr("Speed"); color: "#b4b4c0"; font.pixelSize: 12 }
                                    SpinBox {
                                        from: 0; to: 10; value: backend.ledSpeed
                                        onValueModified: backend.setLedSpeed(value)
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: theme.radius
                            color: "#16161b"
                            border.color: "#282832"
                            implicitHeight: stabCol.implicitHeight + 24

                            ColumnLayout {
                                id: stabCol
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 12

                                Label { text: qsTr("Stability & Sensors"); font.pixelSize: 15; font.bold: true; color: "#f4f4f6" }

                                RowLayout {
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        spacing: 2
                                        Label { text: qsTr("In-Ear Wear Detection"); color: "#f4f4f6"; font.pixelSize: 13 }
                                        Label { text: qsTr("Disable to prevent false pauses or disconnects"); color: "#888896"; font.pixelSize: 11 }
                                    }
                                    Item { Layout.fillWidth: true }
                                    Switch {
                                        checked: backend.inEarDetection
                                        onToggled: backend.setInEarDetection(checked)
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        spacing: 2
                                        Label { text: qsTr("Bluetooth Multipoint"); color: "#f4f4f6"; font.pixelSize: 13 }
                                        Label { text: qsTr("Single-Point mode prevents dongle/phone switching freezes"); color: "#888896"; font.pixelSize: 11 }
                                    }
                                    Item { Layout.fillWidth: true }
                                    Button {
                                        text: qsTr("Single-Point (Recommended)")
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setMultipoint(false)
                                    }
                                    Button {
                                        text: qsTr("Multipoint")
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setMultipoint(true)
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: qsTr("Voice Prompt Language"); color: "#f4f4f6"; font.pixelSize: 13 }
                                    Item { Layout.fillWidth: true }
                                    Button {
                                        text: qsTr("Chinese")
                                        highlighted: backend.language === 0
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setLanguage(0)
                                    }
                                    Button {
                                        text: qsTr("English")
                                        highlighted: backend.language === 1
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setLanguage(1)
                                    }
                                }
                            }
                        }
                    }
                }

                // TAB 4: LIVE RADIO TELEMETRY (0x0C) & MIMI SOUND DSP (0x0E)
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: win.width - 42
                        spacing: 14
                        enabled: backend.btConnected && !backend.busy

                        Rectangle {
                            Layout.fillWidth: true
                            radius: theme.radius
                            color: "#16161b"
                            border.color: "#282832"
                            implicitHeight: statsCol.implicitHeight + 24

                            ColumnLayout {
                                id: statsCol
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 10

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: qsTr("Live Radio Telemetry (Feature 0x0C)"); font.pixelSize: 15; font.bold: true; color: "#f4f4f6" }
                                    Item { Layout.fillWidth: true }
                                    Button {
                                        text: qsTr("Refresh Stats")
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.refresh()
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 10
                                    Repeater {
                                        model: [
                                            { lbl: qsTr("Stream Codec"), val: backend.activeStreamCodec.length > 0 ? backend.activeStreamCodec : "--" },
                                            { lbl: "RSSI", val: backend.primaryRssi > -900 ? (backend.primaryRssi + " dBm") : "--" },
                                            { lbl: "SNR", val: backend.primarySnr > -900 ? (backend.primarySnr + " dB") : "--" },
                                            { lbl: qsTr("Link Quality"), val: backend.primaryLinkQuality >= 0 ? String(backend.primaryLinkQuality) : "--" },
                                            { lbl: qsTr("Bitrate"), val: backend.streamBitrateKbps >= 0 ? (backend.streamBitrateKbps + " kbps") : "--" }
                                        ]
                                        delegate: Rectangle {
                                            required property var modelData
                                            Layout.fillWidth: true
                                            implicitHeight: 54
                                            radius: Math.min(4, theme.radius)
                                            color: "#1e1e26"
                                            border.color: "#2c2c38"
                                            ColumnLayout {
                                                anchors.centerIn: parent
                                                spacing: 2
                                                Label { Layout.alignment: Qt.AlignHCenter; text: modelData.lbl; font.pixelSize: 11; color: "#90909e" }
                                                Label { Layout.alignment: Qt.AlignHCenter; text: modelData.val; font.pixelSize: 13; font.bold: true; color: "#f4f4f6" }
                                            }
                                        }
                                    }
                                }

                                Label {
                                    visible: backend.radioStats.length === 0
                                    text: qsTr("No active streaming statistics yet — start Bluetooth audio playback and refresh.")
                                    color: "#888896"
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                }

                                Repeater {
                                    model: backend.radioStats
                                    delegate: RowLayout {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        Label { text: modelData.category + ":" + modelData.id; color: theme.accent; font.pixelSize: 11; font.family: "monospace"; Layout.preferredWidth: 96 }
                                        Label { text: modelData.name; color: "#d4d4dc"; font.pixelSize: 12; Layout.fillWidth: true }
                                        Label { text: modelData.value + (modelData.unit.length > 0 ? (" " + modelData.unit) : ""); color: "#f4f4f6"; font.pixelSize: 12; font.bold: true }
                                        Label { text: "(" + modelData.rawHex + ")"; color: "#6e6e7c"; font.pixelSize: 11; font.family: "monospace" }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: theme.radius
                            color: "#16161b"
                            border.color: "#282832"
                            implicitHeight: mimiCol.implicitHeight + 24

                            ColumnLayout {
                                id: mimiCol
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 10

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: qsTr("Mimi Sound DSP (Feature 0x0E)"); font.pixelSize: 15; font.bold: true; color: "#f4f4f6" }
                                    Item { Layout.fillWidth: true }
                                    Label {
                                        text: backend.mimiSupported ? qsTr("Supported") : qsTr("Unsupported on this firmware")
                                        color: backend.mimiSupported ? "#7ef0a6" : "#faad14"
                                        font.pixelSize: 12
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Switch {
                                        text: qsTr("Mimi Enabled")
                                        checked: backend.mimiEnabled
                                        onToggled: backend.setMimiEnabled(checked)
                                    }
                                    Item { Layout.fillWidth: true }
                                    Label { text: qsTr("Intensity") + ": " + Math.round(mimiSlider.value) + "%"; color: "#b4b4c0"; font.pixelSize: 12 }
                                    Slider {
                                        id: mimiSlider
                                        from: 0; to: 100; stepSize: 1
                                        value: backend.mimiIntensity
                                        Layout.preferredWidth: 180
                                        onPressedChanged: {
                                            if (!pressed) backend.setMimiIntensity(Math.round(value))
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Label { text: qsTr("Preset ID (MD5)"); color: "#b4b4c0"; font.pixelSize: 12 }
                                    TextField {
                                        id: mimiPresetField
                                        Layout.fillWidth: true
                                        placeholderText: "32 hex chars (16-byte MD5)"
                                        text: backend.mimiPresetId
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                    }
                                    Button {
                                        text: qsTr("Set ID")
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.setMimiPresetId(mimiPresetField.text)
                                    }
                                    Button {
                                        text: qsTr("Clear Preset")
                                        Material.roundedScale: theme.radius
                                        onClicked: backend.clearMimiPreset()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // --- Status footer ---
            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: backend.statusMessage
                    color: "#9898a6"
                    font.pixelSize: 12
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                BusyIndicator {
                    running: backend.busy
                    visible: backend.busy
                    implicitWidth: 18
                    implicitHeight: 18
                }
                Label {
                    text: "? " + qsTr("Keyboard Shortcuts")
                    color: "#6a6a78"
                    font.pixelSize: 11
                }
            }
        }

        // --- Keyboard shortcut help overlay (?) ---
        Rectangle {
            anchors.fill: parent
            visible: win.helpVisible
            color: "#cc000000"
            MouseArea { anchors.fill: parent; onClicked: win.helpVisible = false }

            Rectangle {
                anchors.centerIn: parent
                width: 400
                implicitHeight: helpCol.implicitHeight + 32
                radius: theme.radius
                color: "#18181f"
                border.color: theme.accent
                border.width: 1

                ColumnLayout {
                    id: helpCol
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 8

                    Label { text: qsTr("Keyboard Shortcuts"); font.pixelSize: 16; font.bold: true; color: "#f4f4f6" }
                    GridLayout {
                        columns: 2
                        columnSpacing: 16
                        rowSpacing: 6
                        Label { text: "Space / R"; color: theme.accent; font.bold: true }
                        Label { text: qsTr("Refresh status"); color: "#d4d4dc" }
                        Label { text: "1 - 5"; color: theme.accent; font.bold: true }
                        Label { text: qsTr("Switch tabs"); color: "#d4d4dc" }
                        Label { text: "B"; color: theme.accent; font.bold: true }
                        Label { text: qsTr("Apply Battery Saver"); color: "#d4d4dc" }
                        Label { text: "?"; color: theme.accent; font.bold: true }
                        Label { text: qsTr("Toggle this help"); color: "#d4d4dc" }
                        Label { text: "Q"; color: theme.accent; font.bold: true }
                        Label { text: qsTr("Quit"); color: "#d4d4dc" }
                    }
                    Button {
                        Layout.alignment: Qt.AlignRight
                        text: qsTr("Close")
                        Material.roundedScale: theme.radius
                        onClicked: win.helpVisible = false
                    }
                }
            }
        }
    }
}
