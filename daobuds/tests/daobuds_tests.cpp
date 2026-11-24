#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>
#include <QtTest>

#include "backend.h"
#include "gaia.h"
#include "theme.h"
#include "translator.h"

class DaoBudsTests : public QObject {
    Q_OBJECT

private slots:
    void gaiaFrameRoundTrip() {
        QByteArray pl;
        pl.append(static_cast<char>(1));
        pl.append(static_cast<char>(4));
        pl.append(static_cast<char>(3));
        pl.append(static_cast<char>(2));
        const QByteArray frame = Gaia::buildFrame(Gaia::kFeatCustom, 0x13, pl, Gaia::kVendorQtil, 2);
        const auto parsed = Gaia::parseFrames(frame);
        QCOMPARE(parsed.size(), 1);
        QCOMPARE(parsed[0].vendor, Gaia::kVendorQtil);
        QCOMPARE(parsed[0].feature, Gaia::kFeatCustom);
        QCOMPARE(parsed[0].pduType, static_cast<uint8_t>(2));
        QCOMPARE(parsed[0].pduId, static_cast<uint8_t>(0x13));
        QCOMPARE(parsed[0].payload, pl);
    }

    void parseMacReversesOctetsForBlueZ() {
        uint8_t ba[6]{};
        QVERIFY(Gaia::parseMacAddress("DC:F0:90:50:6C:81", ba));
        QCOMPARE(ba[0], static_cast<uint8_t>(0x81));
        QCOMPARE(ba[5], static_cast<uint8_t>(0xDC));
        QVERIFY(!Gaia::parseMacAddress("invalid", ba));
    }

    void statusJsonSerializesBatteryAndDongle() {
        DaoStatus st;
        st.btConnected = true;
        st.firmware = "9.0(released)";
        st.batteryLeft = 49;
        st.batteryRight = 61;
        st.batteryCase = 31;
        st.dongleConnected = true;
        st.dongleFirmware = "1.1 (cfg 2)";
        st.mimiSupported = true;
        st.mimiEnabled = true;
        st.mimiIntensity = 65;
        st.activeStreamCodec = "aptX Adaptive";
        st.primaryRssi = -54;
        const auto obj = QJsonDocument::fromJson(Backend::statusToJson(st)).object();
        QCOMPARE(obj["bt_connected"].toBool(), true);
        QCOMPARE(obj["battery"].toObject()["left"].toInt(), 49);
        QCOMPARE(obj["dongle"].toObject()["firmware"].toString(), QString("1.1 (cfg 2)"));
        QCOMPARE(obj["mimi"].toObject()["intensity"].toInt(), 65);
        QCOMPARE(obj["statistics"].toObject()["primary_rssi_dbm"].toInt(), -54);
    }

    void parseStatisticsCategoryDecodesRssiSnrCodecBitrate() {
        // more=0, cat=0x0001, entries:
        //   0x01 len=1 val=0x05 (aptX Adaptive)
        //   0x03 len=4 val=320000 LE (320.0 kbps)
        //   0x04 len=1 val=-58 (0xC6) dBm
        //   0x08 len=1 val=24 (0x18) dB
        const QByteArray payload = QByteArray::fromHex("000001010105030400e204000401c6080118");
        bool more = true;
        uint16_t cat = 0;
        const auto stats = Gaia::parseStatisticsCategoryPayload(payload, &more, &cat);
        QCOMPARE(more, false);
        QCOMPARE(cat, static_cast<uint16_t>(0x0001));
        QCOMPARE(stats.size(), 4);
        QCOMPARE(stats[0].name, QString("codec_type"));
        QCOMPARE(stats[0].value, QString("aptX Adaptive"));
        QCOMPARE(stats[1].name, QString("bitrate"));
        QCOMPARE(stats[1].value, QString("320.0"));
        QCOMPARE(stats[2].name, QString("primary_rssi_dbm"));
        QCOMPARE(stats[2].value, QString("-58"));
        QCOMPARE(stats[3].name, QString("primary_snr_db"));
        QCOMPARE(stats[3].value, QString("24"));
    }

    void themeFallsBackAndReadsAccent() {
        QTemporaryDir dir;
        Theme fallback(dir.path());
        QCOMPARE(fallback.accent(), QString("#FFD60A"));
        QCOMPARE(fallback.accentForeground(), QString("black"));

        QDir(dir.path()).mkpath("theme");
        write(dir.path() + "/theme/colors.toml", "accent = \"#112233\"\n");
        Theme themed(dir.path());
        QCOMPARE(themed.accent(), QString("#112233"));
        QCOMPARE(themed.accentForeground(), QString("white"));
    }

    void themeFollowsHyprlandRounding() {
        QTemporaryDir dir;
        const QString resp = dir.filePath("resp.json");
        const QString cmd = dir.filePath("hyprctl");
        write(cmd, "#!/bin/sh\ncat '" + resp.toUtf8() + "'\n");
        QVERIFY(QFile::setPermissions(cmd, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner));
        write(resp, "{\"int\":0}");

        Theme theme(dir.path(), nullptr, cmd);
        QCOMPARE(theme.radius(), 0);
        write(resp, "{\"int\":8}");
        QTRY_COMPARE(theme.radius(), 8);
    }

    void translatorLoadsItalianCatalog() {
        QTemporaryDir dir;
        write(dir.path() + "/language", "it\n");
        write(dir.path() + "/it.json", R"({"Refresh": "Aggiorna", "Touch": "Touch"})");
        Translator tr(dir.path() + "/language", dir.path());
        QCOMPARE(tr.language(), QString("it"));
        QCOMPARE(tr.translate("Main", "Refresh"), QString("Aggiorna"));
    }

private:
    static void write(const QString &path, const QByteArray &contents) {
        QFile f(path);
        QVERIFY(f.open(QIODevice::WriteOnly));
        f.write(contents);
    }
};

QTEST_MAIN(DaoBudsTests)
#include "daobuds_tests.moc"
