#include "backend.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaObject>
#include <algorithm>
#include <cmath>
#include <thread>

Backend::Backend(bool autoPoll, QObject *parent) : QObject(parent) {
    if (autoPoll) {
        m_pollTimer.setInterval(20000);
        connect(&m_pollTimer, &QTimer::timeout, this, &Backend::refresh);
        m_pollTimer.start();
        QTimer::singleShot(150, this, &Backend::refresh);
    }
}

QString Backend::alertMessage() const {
    if (m_state.donglePermissionError)
        return tr("USB dongle detected without hidraw access — install 70-redmagic-dao.rules");
    if (!m_state.btConnected)
        return {};
    if ((m_state.batteryLeft >= 0) != (m_state.batteryRight >= 0))
        return tr("Only one earbud is connected — check charging case pogo pins");
    if (m_state.batteryLeft >= 0 && m_state.batteryRight >= 0 &&
        std::abs(m_state.batteryLeft - m_state.batteryRight) >= 20)
        return tr("Battery imbalance detected: L %1% vs R %2%")
            .arg(m_state.batteryLeft)
            .arg(m_state.batteryRight);
    return {};
}

QVariantList Backend::eqFreqs() const {
    QVariantList list;
    for (int f : m_state.eqFreqs) list.append(f);
    return list;
}

QVariantList Backend::eqGains() const {
    QVariantList list;
    for (double g : m_state.eqGains) list.append(g);
    return list;
}

QByteArray Backend::statusToJson(const DaoStatus &st) {
    QJsonObject root;
    root["bt_connected"] = st.btConnected;
    root["mac"] = st.mac;
    root["firmware"] = st.firmware;
    root["primary"] = st.primary;

    QJsonObject bat;
    if (st.batteryLeft >= 0) bat["left"] = st.batteryLeft;
    if (st.batteryRight >= 0) bat["right"] = st.batteryRight;
    if (st.batteryCase >= 0) bat["case"] = st.batteryCase;
    root["battery"] = bat;

    root["mode_type"] = st.modeType;
    root["codec_mode"] = st.codecMode;
    root["anc_enabled"] = st.ancEnabled;
    root["anc_mode"] = st.ancMode;
    root["in_ear_detection"] = st.inEarDetection;
    root["led_mode"] = st.ledMode;
    root["touch"] = QJsonArray{st.touchLD, st.touchLT, st.touchRD, st.touchRT};

    QJsonObject dongle;
    dongle["connected"] = st.dongleConnected;
    dongle["firmware"] = st.dongleFirmware;
    dongle["serial"] = st.dongleSerial;
    dongle["permission_error"] = st.donglePermissionError;
    root["dongle"] = dongle;
    return QJsonDocument(root).toJson(QJsonDocument::Compact);
}

void Backend::setBusy(bool b) {
    if (m_busy == b) return;
    m_busy = b;
    emit busyChanged();
}

void Backend::setStatusMessage(const QString &msg) {
    if (m_statusMessage == msg) return;
    m_statusMessage = msg;
    emit statusMessageChanged();
}

void Backend::refresh() {
    if (m_inFlight.exchange(true))
        return;
    setBusy(true);
    const QString mac = m_state.mac;
    std::thread([this, mac]() {
        const DaoStatus next = Gaia::queryFullStatus(mac);
        QMetaObject::invokeMethod(
            this,
            [this, next]() {
                m_state = next;
                m_inFlight.store(false);
                setBusy(false);
                if (m_state.btConnected)
                    setStatusMessage(tr("Connected to DAO TWS (%1)").arg(m_state.firmware));
                else if (m_state.dongleConnected)
                    setStatusMessage(tr("Dongle connected (FW %1) — connect Bluetooth for earbud settings")
                                         .arg(m_state.dongleFirmware.isEmpty() ? "?" : m_state.dongleFirmware));
                else if (!m_state.btError.isEmpty())
                    setStatusMessage(m_state.btError);
                else
                    setStatusMessage(tr("No DAO TWS connected via Bluetooth or USB dongle"));
                emit stateChanged();
            },
            Qt::QueuedConnection);
    }).detach();
}

void Backend::runAsyncWrite(const QString &okMsg, uint8_t feat, uint8_t pduId, const QByteArray &payload) {
    if (m_inFlight.exchange(true))
        return;
    setBusy(true);
    const QString mac = m_state.mac;
    std::thread([this, mac, okMsg, feat, pduId, payload]() {
        QString err;
        const bool ok = Gaia::sendCommand(mac, feat, pduId, payload, nullptr, &err);
        const DaoStatus next = ok ? Gaia::queryFullStatus(mac) : DaoStatus{};
        QMetaObject::invokeMethod(
            this,
            [this, ok, okMsg, err, next]() {
                m_inFlight.store(false);
                setBusy(false);
                if (ok) {
                    m_state = next;
                    setStatusMessage(okMsg);
                    emit stateChanged();
                } else {
                    setStatusMessage(err.isEmpty() ? tr("Command failed") : err);
                }
            },
            Qt::QueuedConnection);
    }).detach();
}

void Backend::setModeAndCodec(int modeType, int codecMode) {
    QByteArray pl;
    pl.append(static_cast<char>(modeType & 0xFF));
    pl.append(static_cast<char>((modeType == 1 ? 0 : codecMode) & 0xFF));
    runAsyncWrite(tr("Mode updated"), Gaia::kFeatCustom, 0x02, pl);
}

void Backend::setAncEnabled(bool enabled) {
    QByteArray pl;
    pl.append(static_cast<char>(0x01));
    pl.append(static_cast<char>(enabled ? 1 : 0));
    runAsyncWrite(enabled ? tr("ANC enabled") : tr("ANC disabled"), Gaia::kFeatAudioCuration, 0x01, pl);
}

void Backend::setAncMode(int mode) {
    runAsyncWrite(tr("ANC mode set to %1").arg(mode),
                  Gaia::kFeatAudioCuration, 0x04, QByteArray(1, static_cast<char>(mode & 0xFF)));
}

void Backend::setAncToggleSlot(int slot, int modeOrNegOne) {
    QByteArray pl;
    pl.append(static_cast<char>(slot & 0xFF));
    pl.append(static_cast<char>(modeOrNegOne < 0 ? 0xFF : (modeOrNegOne & 0xFF)));
    runAsyncWrite(tr("ANC toggle slot %1 updated").arg(slot), Gaia::kFeatAudioCuration, 0x09, pl);
}

void Backend::setTouchControls(int ld, int lt, int rd, int rt) {
    QByteArray pl;
    pl.append(static_cast<char>(ld & 0xFF));
    pl.append(static_cast<char>(lt & 0xFF));
    pl.append(static_cast<char>(rd & 0xFF));
    pl.append(static_cast<char>(rt & 0xFF));
    runAsyncWrite(tr("Touch gestures saved"), Gaia::kFeatCustom, 0x13, pl);
}

void Backend::setEqPreset(int preset) {
    runAsyncWrite(tr("EQ preset updated"), Gaia::kFeatMusicEq, 0x03,
                  QByteArray(1, static_cast<char>(preset & 0xFF)));
}

void Backend::setEqBand(int band, double gainDb) {
    const double clamped = std::clamp(gainDb, -12.0, 12.0);
    const int16_t raw = static_cast<int16_t>(std::llround(clamped * 60.0));
    QByteArray pl;
    pl.append(static_cast<char>(band & 0xFF));
    pl.append(static_cast<char>(band & 0xFF));
    pl.append(static_cast<char>((raw >> 8) & 0xFF));
    pl.append(static_cast<char>(raw & 0xFF));
    runAsyncWrite(tr("EQ band updated"), Gaia::kFeatMusicEq, 0x06, pl);
}

void Backend::resetEqFlat() {
    QByteArray pl;
    pl.append(static_cast<char>(0));
    pl.append(static_cast<char>(9));
    for (int i = 0; i < 10; ++i) {
        pl.append(static_cast<char>(0));
        pl.append(static_cast<char>(0));
    }
    runAsyncWrite(tr("User EQ reset to flat"), Gaia::kFeatMusicEq, 0x06, pl);
}

void Backend::setLedMode(int mode, int r, int g, int b) {
    QByteArray pl;
    if (mode == 0) {
        pl.append(static_cast<char>(1));
        pl.append(static_cast<char>(0));
        pl.append(static_cast<char>(0));
        pl.append(static_cast<char>(0));
    } else {
        pl.append(static_cast<char>(mode & 0xFF));
        pl.append(static_cast<char>(r & 0xFF));
        pl.append(static_cast<char>(g & 0xFF));
        pl.append(static_cast<char>(b & 0xFF));
    }
    runAsyncWrite(tr("LED lighting updated"), Gaia::kFeatCustom, 0x04, pl);
}

void Backend::setLedHall(bool enabled) {
    runAsyncWrite(tr("Hall LED updated"), Gaia::kFeatCustom, 0x06,
                  QByteArray(1, static_cast<char>(enabled ? 1 : 0)));
}

void Backend::setLedSpeed(int speed) {
    runAsyncWrite(tr("LED speed updated"), Gaia::kFeatCustom, 0x08,
                  QByteArray(1, static_cast<char>(speed & 0xFF)));
}

void Backend::setLedBrightness(int brightness) {
    runAsyncWrite(tr("LED brightness updated"), Gaia::kFeatCustom, 0x0A,
                  QByteArray(1, static_cast<char>(brightness & 0xFF)));
}

void Backend::setInEarDetection(bool enabled) {
    runAsyncWrite(enabled ? tr("In-ear detection enabled") : tr("In-ear detection disabled"),
                  Gaia::kFeatCustom, 0x11, QByteArray(1, static_cast<char>(enabled ? 1 : 0)));
}

void Backend::setMultipoint(bool enabled) {
    runAsyncWrite(enabled ? tr("Multipoint enabled") : tr("Single-point stability mode enabled"),
                  Gaia::kFeatHandset, 0x00, QByteArray(1, static_cast<char>(enabled ? 1 : 0)));
}

void Backend::setLanguage(int lang) {
    runAsyncWrite(tr("Voice prompt language updated"), Gaia::kFeatCustom, 0x0F,
                  QByteArray(1, static_cast<char>(lang & 0xFF)));
}

void Backend::applyBatterySaver() {
    if (m_inFlight.exchange(true))
        return;
    setBusy(true);
    const QString mac = m_state.mac;
    std::thread([this, mac]() {
        QByteArray ledOff;
        ledOff.append(static_cast<char>(1));
        ledOff.append(static_cast<char>(0));
        ledOff.append(static_cast<char>(0));
        ledOff.append(static_cast<char>(0));
        QByteArray normalMode;
        normalMode.append(static_cast<char>(2));
        normalMode.append(static_cast<char>(1));

        bool ok = true;
        ok = Gaia::sendCommand(mac, Gaia::kFeatCustom, 0x04, ledOff) && ok;
        ok = Gaia::sendCommand(mac, Gaia::kFeatCustom, 0x06, QByteArray(1, 0)) && ok;
        ok = Gaia::sendCommand(mac, Gaia::kFeatCustom, 0x11, QByteArray(1, 0)) && ok;
        ok = Gaia::sendCommand(mac, Gaia::kFeatHandset, 0x00, QByteArray(1, 0)) && ok;
        ok = Gaia::sendCommand(mac, Gaia::kFeatCustom, 0x02, normalMode) && ok;
        const DaoStatus next = Gaia::queryFullStatus(mac);
        QMetaObject::invokeMethod(
            this,
            [this, ok, next]() {
                m_state = next;
                m_inFlight.store(false);
                setBusy(false);
                setStatusMessage(ok ? tr("Battery Saver & Stability applied (LEDs, In-Ear, Multipoint OFF)")
                                    : tr("Partial apply — connect Bluetooth to finish"));
                emit stateChanged();
            },
            Qt::QueuedConnection);
    }).detach();
}
