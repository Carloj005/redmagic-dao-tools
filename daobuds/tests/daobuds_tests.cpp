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
        const auto obj = QJsonDocument::fromJson(Backend::statusToJson(st)).object();
        QCOMPARE(obj["bt_connected"].toBool(), true);
        QCOMPARE(obj["battery"].toObject()["left"].toInt(), 49);
        QCOMPARE(obj["dongle"].toObject()["firmware"].toString(), QString("1.1 (cfg 2)"));
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
