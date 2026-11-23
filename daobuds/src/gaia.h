#pragma once

#include <QByteArray>
#include <QList>
#include <QString>
#include <QVector>
#include <cstdint>

struct GaiaFrame {
    uint16_t vendor = 0;
    uint8_t feature = 0;
    uint8_t pduType = 0;  // 0=CMD, 1=NOTIF, 2=RESP, 3=ERR
    uint8_t pduId = 0;
    QByteArray payload;
};

struct DaoStatus {
    bool btConnected = false;
    QString mac;
    QString btError;
    QString firmware;
    QString primary;  // "left", "right", "unknown"

    int batteryLeft = -1;
    int batteryRight = -1;
    int batteryCase = -1;

    int modeType = 2;     // 1=Game, 2=Music
    int codecMode = 1;    // 0=Empty, 1=Normal, 2=LHDC, 3=aptX Lossless

    bool ancEnabled = false;
    int ancMode = 1;
    int ancToggle1 = 1;
    int ancToggle2 = 5;
    int ancToggle3 = -1;  // -1 = off (0xFF)

    int ledMode = 0;      // 0=off, 1=static, 2=breath, 3=rainbow
    int ledR = 0;
    int ledG = 255;
    int ledB = 255;
    bool ledHall = false;
    int ledSpeed = 3;
    int ledBrightness = 6;

    bool inEarDetection = false;
    int language = 1;

    int touchLD = 1;
    int touchLT = 4;
    int touchRD = 3;
    int touchRT = 2;

    bool eqEnabled = true;
    int eqPreset = 0;     // 0..9 or 0x3F (63) for User
    QVector<int> eqFreqs = {31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000};
    QVector<double> eqGains = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

    bool dongleConnected = false;
    QString dongleFirmware;
    QString dongleSerial;
    QString dongleHidraw;
    bool donglePermissionError = false;
};

namespace Gaia {

constexpr uint16_t kVendorQtil = 0x001D;
constexpr uint8_t kFeatBasic = 0x00;
constexpr uint8_t kFeatEarbud = 0x01;
constexpr uint8_t kFeatMusicEq = 0x05;
constexpr uint8_t kFeatHandset = 0x07;
constexpr uint8_t kFeatAudioCuration = 0x08;
constexpr uint8_t kFeatBattery = 0x0D;
constexpr uint8_t kFeatCustom = 0x0E;
constexpr int kDefaultRfcommChannel = 11;

QByteArray buildFrame(uint8_t feature, uint8_t pduId, const QByteArray &payload = {},
                      uint16_t vendor = kVendorQtil, uint8_t pduType = 0);
QList<GaiaFrame> parseFrames(const QByteArray &buffer);
bool parseMacAddress(const QString &mac, uint8_t out[6]);

QString findDaoMac();
bool isBtConnected(const QString &mac);

// Read-only USB HID (19d2:0616) probe via Qualcomm qc-s5gen2 protocol.
void probeDongle(DaoStatus &status);

// Full Bluetooth + USB dongle snapshot (blocking; run on worker thread).
DaoStatus queryFullStatus(const QString &macOverride = {});

// Single Bluetooth GAIA v3 command helper (blocking; run on worker thread).
bool sendCommand(const QString &mac, uint8_t feature, uint8_t pduId,
                 const QByteArray &payload, QByteArray *responseOut = nullptr,
                 QString *errorOut = nullptr);

}  // namespace Gaia
