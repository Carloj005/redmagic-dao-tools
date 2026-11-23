#pragma once

#include <QObject>
#include <QTimer>
#include <QVariantList>
#include <atomic>

#include "gaia.h"

class Backend : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(bool btConnected READ btConnected NOTIFY stateChanged)
    Q_PROPERTY(QString mac READ mac NOTIFY stateChanged)
    Q_PROPERTY(QString firmware READ firmware NOTIFY stateChanged)
    Q_PROPERTY(QString primary READ primary NOTIFY stateChanged)
    Q_PROPERTY(QString statusMessage READ statusMessage NOTIFY statusMessageChanged)
    Q_PROPERTY(QString alertMessage READ alertMessage NOTIFY stateChanged)

    Q_PROPERTY(int batteryLeft READ batteryLeft NOTIFY stateChanged)
    Q_PROPERTY(int batteryRight READ batteryRight NOTIFY stateChanged)
    Q_PROPERTY(int batteryCase READ batteryCase NOTIFY stateChanged)

    Q_PROPERTY(bool dongleConnected READ dongleConnected NOTIFY stateChanged)
    Q_PROPERTY(QString dongleFirmware READ dongleFirmware NOTIFY stateChanged)
    Q_PROPERTY(QString dongleSerial READ dongleSerial NOTIFY stateChanged)
    Q_PROPERTY(bool donglePermissionError READ donglePermissionError NOTIFY stateChanged)

    Q_PROPERTY(int modeType READ modeType NOTIFY stateChanged)
    Q_PROPERTY(int codecMode READ codecMode NOTIFY stateChanged)

    Q_PROPERTY(bool ancEnabled READ ancEnabled NOTIFY stateChanged)
    Q_PROPERTY(int ancMode READ ancMode NOTIFY stateChanged)
    Q_PROPERTY(int ancToggle1 READ ancToggle1 NOTIFY stateChanged)
    Q_PROPERTY(int ancToggle2 READ ancToggle2 NOTIFY stateChanged)
    Q_PROPERTY(int ancToggle3 READ ancToggle3 NOTIFY stateChanged)

    Q_PROPERTY(int ledMode READ ledMode NOTIFY stateChanged)
    Q_PROPERTY(int ledR READ ledR NOTIFY stateChanged)
    Q_PROPERTY(int ledG READ ledG NOTIFY stateChanged)
    Q_PROPERTY(int ledB READ ledB NOTIFY stateChanged)
    Q_PROPERTY(bool ledHall READ ledHall NOTIFY stateChanged)
    Q_PROPERTY(int ledSpeed READ ledSpeed NOTIFY stateChanged)
    Q_PROPERTY(int ledBrightness READ ledBrightness NOTIFY stateChanged)

    Q_PROPERTY(bool inEarDetection READ inEarDetection NOTIFY stateChanged)
    Q_PROPERTY(int language READ language NOTIFY stateChanged)

    Q_PROPERTY(int touchLD READ touchLD NOTIFY stateChanged)
    Q_PROPERTY(int touchLT READ touchLT NOTIFY stateChanged)
    Q_PROPERTY(int touchRD READ touchRD NOTIFY stateChanged)
    Q_PROPERTY(int touchRT READ touchRT NOTIFY stateChanged)

    Q_PROPERTY(bool eqEnabled READ eqEnabled NOTIFY stateChanged)
    Q_PROPERTY(int eqPreset READ eqPreset NOTIFY stateChanged)
    Q_PROPERTY(QVariantList eqFreqs READ eqFreqs NOTIFY stateChanged)
    Q_PROPERTY(QVariantList eqGains READ eqGains NOTIFY stateChanged)

public:
    explicit Backend(bool autoPoll = true, QObject *parent = nullptr);

    bool busy() const { return m_busy; }
    bool btConnected() const { return m_state.btConnected; }
    QString mac() const { return m_state.mac; }
    QString firmware() const { return m_state.firmware; }
    QString primary() const { return m_state.primary; }
    QString statusMessage() const { return m_statusMessage; }
    QString alertMessage() const;

    int batteryLeft() const { return m_state.batteryLeft; }
    int batteryRight() const { return m_state.batteryRight; }
    int batteryCase() const { return m_state.batteryCase; }

    bool dongleConnected() const { return m_state.dongleConnected; }
    QString dongleFirmware() const { return m_state.dongleFirmware; }
    QString dongleSerial() const { return m_state.dongleSerial; }
    bool donglePermissionError() const { return m_state.donglePermissionError; }

    int modeType() const { return m_state.modeType; }
    int codecMode() const { return m_state.codecMode; }

    bool ancEnabled() const { return m_state.ancEnabled; }
    int ancMode() const { return m_state.ancMode; }
    int ancToggle1() const { return m_state.ancToggle1; }
    int ancToggle2() const { return m_state.ancToggle2; }
    int ancToggle3() const { return m_state.ancToggle3; }

    int ledMode() const { return m_state.ledMode; }
    int ledR() const { return m_state.ledR; }
    int ledG() const { return m_state.ledG; }
    int ledB() const { return m_state.ledB; }
    bool ledHall() const { return m_state.ledHall; }
    int ledSpeed() const { return m_state.ledSpeed; }
    int ledBrightness() const { return m_state.ledBrightness; }

    bool inEarDetection() const { return m_state.inEarDetection; }
    int language() const { return m_state.language; }

    int touchLD() const { return m_state.touchLD; }
    int touchLT() const { return m_state.touchLT; }
    int touchRD() const { return m_state.touchRD; }
    int touchRT() const { return m_state.touchRT; }

    bool eqEnabled() const { return m_state.eqEnabled; }
    int eqPreset() const { return m_state.eqPreset; }
    QVariantList eqFreqs() const;
    QVariantList eqGains() const;

    // Headless JSON summary (used by CLI mode and unit tests).
    static QByteArray statusToJson(const DaoStatus &st);

    Q_INVOKABLE void refresh();
    Q_INVOKABLE void setModeAndCodec(int modeType, int codecMode);
    Q_INVOKABLE void setAncEnabled(bool enabled);
    Q_INVOKABLE void setAncMode(int mode);
    Q_INVOKABLE void setAncToggleSlot(int slot, int modeOrNegOne);
    Q_INVOKABLE void setTouchControls(int ld, int lt, int rd, int rt);
    Q_INVOKABLE void setEqPreset(int preset);
    Q_INVOKABLE void setEqBand(int band, double gainDb);
    Q_INVOKABLE void resetEqFlat();
    Q_INVOKABLE void setLedMode(int mode, int r, int g, int b);
    Q_INVOKABLE void setLedHall(bool enabled);
    Q_INVOKABLE void setLedSpeed(int speed);
    Q_INVOKABLE void setLedBrightness(int brightness);
    Q_INVOKABLE void setInEarDetection(bool enabled);
    Q_INVOKABLE void setMultipoint(bool enabled);
    Q_INVOKABLE void setLanguage(int lang);
    Q_INVOKABLE void applyBatterySaver();

signals:
    void busyChanged();
    void stateChanged();
    void statusMessageChanged();

private:
    void setBusy(bool b);
    void setStatusMessage(const QString &msg);
    void runAsyncWrite(const QString &okMsg, uint8_t feat, uint8_t pduId, const QByteArray &payload);

    DaoStatus m_state;
    bool m_busy = false;
    std::atomic<bool> m_inFlight{false};
    QString m_statusMessage;
    QTimer m_pollTimer;
};
