#include "gaia.h"

#include <QDir>
#include <QFile>
#include <QProcess>
#include <QRegularExpression>
#include <QSet>
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstring>

#include <bluetooth/bluetooth.h>
#include <bluetooth/rfcomm.h>
#include <fcntl.h>
#include <linux/hidraw.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

namespace Gaia {

namespace {

int64_t readLeSigned(const QByteArray &b) {
    if (b.size() == 1) return static_cast<int8_t>(b[0]);
    if (b.size() == 2) {
        const uint16_t u = static_cast<uint8_t>(b[0]) | (static_cast<uint16_t>(static_cast<uint8_t>(b[1])) << 8);
        return static_cast<int16_t>(u);
    }
    if (b.size() == 4) {
        uint32_t u = 0;
        for (int i = 0; i < 4; ++i) u |= static_cast<uint32_t>(static_cast<uint8_t>(b[i])) << (8 * i);
        return static_cast<int32_t>(u);
    }
    return 0;
}

uint64_t readLeUnsigned(const QByteArray &b) {
    uint64_t u = 0;
    const int n = std::min<int>(b.size(), 8);
    for (int i = 0; i < n; ++i) u |= static_cast<uint64_t>(static_cast<uint8_t>(b[i])) << (8 * i);
    return u;
}

QString streamingCodecName(uint8_t id) {
    switch (id) {
        case 0: return "None";
        case 1: return "SBC";
        case 2: return "AAC";
        case 3: return "aptX";
        case 4: return "aptX HD";
        case 5: return "aptX Adaptive";
        case 6: return "aptX Lossless";
        case 7: return "LHDC / Vendor";
        case 8: return "LC3";
        default: return QString("0x%1").arg(id, 2, 16, QChar('0'));
    }
}

RadioStat decodeStat(uint16_t cat, uint8_t id, const QByteArray &raw) {
    RadioStat s;
    s.category = cat;
    s.id = id;
    s.rawHex = QString::fromLatin1(raw.toHex());
    s.name = QString("stat_0x%1").arg(id, 2, 16, QChar('0'));
    s.value = s.rawHex;

    if (cat == 0x0001 && !raw.isEmpty()) {
        switch (id) {
            case 0x01:
                s.name = "codec_type";
                s.value = streamingCodecName(static_cast<uint8_t>(raw[0]));
                return s;
            case 0x02:
                s.name = "lossless_enabled";
                s.value = (raw[0] != 0) ? "true" : "false";
                return s;
            case 0x03: {
                s.name = "bitrate";
                const uint64_t bps = readLeUnsigned(raw);
                s.value = (bps > 10000) ? QString::number(bps / 1000.0, 'f', 1) : QString::number(bps);
                s.unit = "kbps";
                return s;
            }
            case 0x04:
                s.name = "primary_rssi_dbm";
                s.value = QString::number(readLeSigned(raw));
                s.unit = "dBm";
                return s;
            case 0x05:
                s.name = "primary_link_quality";
                s.value = QString::number(readLeUnsigned(raw));
                return s;
            case 0x06: {
                s.name = "transport_type";
                const uint8_t t = static_cast<uint8_t>(raw[0]);
                s.value = (t == 1) ? "BR/EDR" : (t == 2 ? "LE" : (t == 0 ? "None" : QString::number(t)));
                return s;
            }
            case 0x07:
                s.name = "audio_format";
                s.value = QString::number(readLeUnsigned(raw));
                return s;
            case 0x08:
                s.name = "primary_snr_db";
                s.value = QString::number(readLeSigned(raw));
                s.unit = "dB";
                return s;
            case 0x09:
                s.name = "secondary_rssi_dbm";
                s.value = QString::number(readLeSigned(raw));
                s.unit = "dBm";
                return s;
            case 0x0A:
                s.name = "secondary_link_quality";
                s.value = QString::number(readLeUnsigned(raw));
                return s;
            case 0x0B:
                s.name = "primary_tx_power_dbm";
                s.value = QString::number(readLeSigned(raw));
                s.unit = "dBm";
                return s;
            case 0x0C:
                s.name = "secondary_snr_db";
                s.value = QString::number(readLeSigned(raw));
                s.unit = "dB";
                return s;
            default:
                break;
        }
    }

    if (raw.size() == 1 || raw.size() == 2 || raw.size() == 4)
        s.value = QString::number(readLeUnsigned(raw));
    return s;
}

}  // namespace

QByteArray buildFrame(uint8_t feature, uint8_t pduId, const QByteArray &payload,
                      uint16_t vendor, uint8_t pduType) {
    const uint16_t pdu = static_cast<uint16_t>(((feature & 0x7F) << 9) |
                                               ((pduType & 0x03) << 7) |
                                               (pduId & 0x7F));
    QByteArray out;
    out.reserve(8 + payload.size());
    out.append(static_cast<char>(0xFF));
    out.append(static_cast<char>(0x03));
    out.append(static_cast<char>(0x00));
    out.append(static_cast<char>(payload.size() & 0xFF));
    out.append(static_cast<char>((vendor >> 8) & 0xFF));
    out.append(static_cast<char>(vendor & 0xFF));
    out.append(static_cast<char>((pdu >> 8) & 0xFF));
    out.append(static_cast<char>(pdu & 0xFF));
    out.append(payload);
    return out;
}

QList<GaiaFrame> parseFrames(const QByteArray &buffer) {
    QList<GaiaFrame> frames;
    const auto *raw = reinterpret_cast<const uint8_t *>(buffer.constData());
    const int n = buffer.size();
    int i = 0;
    while (i < n) {
        if (raw[i] != 0xFF || i + 8 > n) {
            ++i;
            continue;
        }
        const uint8_t flags = raw[i + 2];
        const uint8_t plen = raw[i + 3];
        const uint16_t vendor = static_cast<uint16_t>((raw[i + 4] << 8) | raw[i + 5]);
        const uint16_t pdu = static_cast<uint16_t>((raw[i + 6] << 8) | raw[i + 7]);
        const int chk = (flags & 0x01) ? 1 : 0;
        const int end = i + 8 + plen + chk;
        if (end > n)
            break;
        GaiaFrame f;
        f.vendor = vendor;
        f.feature = static_cast<uint8_t>((pdu >> 9) & 0x7F);
        f.pduType = static_cast<uint8_t>((pdu >> 7) & 0x03);
        f.pduId = static_cast<uint8_t>(pdu & 0x7F);
        f.payload = buffer.mid(i + 8, plen);
        frames.append(f);
        i = end;
    }
    return frames;
}

bool parseMacAddress(const QString &mac, uint8_t out[6]) {
    const QStringList parts = mac.trimmed().split(':');
    if (parts.size() != 6)
        return false;
    for (int i = 0; i < 6; ++i) {
        bool ok = false;
        const int v = parts[i].toInt(&ok, 16);
        if (!ok || v < 0 || v > 255)
            return false;
        // BlueZ bdaddr_t stores octets in reverse (little-endian) order.
        out[5 - i] = static_cast<uint8_t>(v);
    }
    return true;
}

QList<RadioStat> parseStatisticsCategoryPayload(const QByteArray &payload,
                                                bool *moreOut,
                                                uint16_t *catOut) {
    QList<RadioStat> stats;
    if (moreOut) *moreOut = false;
    if (catOut) *catOut = 0;
    if (payload.size() < 3)
        return stats;

    const auto *b = reinterpret_cast<const uint8_t *>(payload.constData());
    if (moreOut) *moreOut = (b[0] != 0);
    const uint16_t cat = static_cast<uint16_t>((b[1] << 8) | b[2]);
    if (catOut) *catOut = cat;

    int pos = 3;
    while (pos + 2 <= payload.size()) {
        const uint8_t sid = b[pos];
        const uint8_t vlen = b[pos + 1];
        pos += 2;
        if (pos + vlen > payload.size())
            break;
        stats.append(decodeStat(cat, sid, payload.mid(pos, vlen)));
        pos += vlen;
    }
    return stats;
}

QString findDaoMac() {
    QProcess proc;
    proc.start("bluetoothctl", {"devices"});
    if (!proc.waitForFinished(2000))
        return {};
    const QString out = QString::fromUtf8(proc.readAllStandardOutput());
    for (const QString &line : out.split('\n')) {
        if (line.contains("DAO TWS", Qt::CaseInsensitive)) {
            const QStringList toks = line.simplified().split(' ');
            if (toks.size() >= 2)
                return toks[1];
        }
    }
    return {};
}

bool isBtConnected(const QString &mac) {
    if (mac.isEmpty())
        return false;
    QProcess proc;
    proc.start("bluetoothctl", {"info", mac});
    if (!proc.waitForFinished(2000))
        return false;
    return QString::fromUtf8(proc.readAllStandardOutput()).contains("Connected: yes");
}

namespace {

int connectRfcomm(const QString &mac, int timeoutMs, QString *errorOut) {
    uint8_t ba[6];
    if (!parseMacAddress(mac, ba)) {
        if (errorOut) *errorOut = "Invalid Bluetooth MAC address";
        return -1;
    }

    int fd = ::socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM);
    if (fd < 0) {
        if (errorOut) *errorOut = QString("RFCOMM socket error: %1").arg(strerror(errno));
        return -1;
    }

    const int flags = ::fcntl(fd, F_GETFL, 0);
    ::fcntl(fd, F_SETFL, flags | O_NONBLOCK);

    sockaddr_rc addr{};
    addr.rc_family = AF_BLUETOOTH;
    addr.rc_channel = static_cast<uint8_t>(kDefaultRfcommChannel);
    std::memcpy(addr.rc_bdaddr.b, ba, 6);

    int rc = ::connect(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr));
    if (rc < 0 && errno != EINPROGRESS) {
        if (errorOut) *errorOut = QString("RFCOMM connect error: %1").arg(strerror(errno));
        ::close(fd);
        return -1;
    }

    if (rc < 0) {
        pollfd pfd{fd, POLLOUT, 0};
        rc = ::poll(&pfd, 1, timeoutMs);
        if (rc <= 0) {
            if (errorOut) *errorOut = "RFCOMM connection timed out";
            ::close(fd);
            return -1;
        }
        int soErr = 0;
        socklen_t len = sizeof(soErr);
        ::getsockopt(fd, SOL_SOCKET, SO_ERROR, &soErr, &len);
        if (soErr != 0) {
            if (errorOut) *errorOut = QString("RFCOMM connect failed: %1").arg(strerror(soErr));
            ::close(fd);
            return -1;
        }
    }
    return fd;
}

QByteArray recvSome(int fd, int firstTimeoutMs = 700, int followTimeoutMs = 120) {
    QByteArray out;
    int timeout = firstTimeoutMs;
    while (true) {
        pollfd pfd{fd, POLLIN, 0};
        const int r = ::poll(&pfd, 1, timeout);
        if (r <= 0)
            break;
        char buf[1024];
        const ssize_t n = ::read(fd, buf, sizeof(buf));
        if (n <= 0)
            break;
        out.append(buf, static_cast<int>(n));
        timeout = followTimeoutMs;
    }
    return out;
}

bool xfer(int fd, uint8_t feat, uint8_t pduId, const QByteArray &payload, QByteArray *respOut) {
    const QByteArray frame = buildFrame(feat, pduId, payload);
    const ssize_t sent = ::write(fd, frame.constData(), static_cast<size_t>(frame.size()));
    if (sent != frame.size())
        return false;
    const QByteArray rx = recvSome(fd, 700, 100);
    for (const GaiaFrame &f : parseFrames(rx)) {
        if (f.vendor == kVendorQtil && f.feature == feat && f.pduId == pduId) {
            if (f.pduType == 2) {
                if (respOut) *respOut = f.payload;
                return true;
            }
            if (f.pduType == 3)
                return false;
        }
    }
    return false;
}

void queryStatistics(int fd, DaoStatus &st) {
    QList<uint16_t> categories;
    uint16_t lastCat = 0;
    QByteArray d;

    for (int page = 0; page < 16; ++page) {
        QByteArray req(2, 0);
        req[0] = static_cast<char>((lastCat >> 8) & 0xFF);
        req[1] = static_cast<char>(lastCat & 0xFF);
        if (!xfer(fd, kFeatStats, 0x00, req, &d) || d.isEmpty())
            break;
        const auto *b = reinterpret_cast<const uint8_t *>(d.constData());
        const bool more = (b[0] != 0);
        bool added = false;
        for (int i = 1; i + 1 < d.size(); i += 2) {
            const uint16_t cid = static_cast<uint16_t>((b[i] << 8) | b[i + 1]);
            if (!categories.contains(cid)) {
                categories.append(cid);
                added = true;
            }
            lastCat = cid;
        }
        if (!more || !added)
            break;
    }

    for (uint16_t cid : categories) {
        uint8_t lastSid = 0;
        QSet<uint8_t> seen;
        for (int page = 0; page < 32; ++page) {
            QByteArray req(3, 0);
            req[0] = static_cast<char>((cid >> 8) & 0xFF);
            req[1] = static_cast<char>(cid & 0xFF);
            req[2] = static_cast<char>(lastSid);
            if (!xfer(fd, kFeatStats, 0x01, req, &d) || d.size() < 3)
                break;
            bool more = false;
            const auto items = parseStatisticsCategoryPayload(d, &more);
            if (items.isEmpty())
                break;
            bool progressed = false;
            for (const RadioStat &item : items) {
                if (!seen.contains(item.id)) {
                    seen.insert(item.id);
                    st.radioStats.append(item);
                    progressed = true;
                    if (item.category == 0x0001) {
                        if (item.id == 0x01) st.activeStreamCodec = item.value;
                        else if (item.id == 0x03) st.streamBitrateKbps = static_cast<int>(std::llround(item.value.toDouble()));
                        else if (item.id == 0x04) st.primaryRssi = item.value.toInt();
                        else if (item.id == 0x05) st.primaryLinkQuality = item.value.toInt();
                        else if (item.id == 0x08) st.primarySnr = item.value.toInt();
                    }
                }
                lastSid = item.id;
            }
            if (!more || !progressed)
                break;
        }
    }
}

}  // namespace

void probeDongle(DaoStatus &status) {
    status.dongleConnected = false;
    status.dongleFirmware.clear();
    status.dongleSerial.clear();
    status.dongleHidraw.clear();
    status.donglePermissionError = false;

    // Detect 19d2:0616 purely via sysfs (zero USB HID control traffic during polling,
    // avoiding QCC3086 ETIMEDOUT stalls while audio is streaming).
    QDir dir("/sys/class/hidraw");
    const QStringList entries = dir.entryList({"hidraw*"}, QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name);
    for (const QString &entry : entries) {
        QFile uevent(dir.filePath(entry + "/device/uevent"));
        if (!uevent.open(QIODevice::ReadOnly))
            continue;
        const QString text = QString::fromUtf8(uevent.readAll());
        if (!text.contains("000019D2:00000616", Qt::CaseInsensitive))
            continue;
        status.dongleConnected = true;
        for (const QString &line : text.split('\n')) {
            if (line.startsWith("HID_UNIQ="))
                status.dongleSerial = line.mid(9).trimmed();
        }
        if (text.contains("/input1"))
            status.dongleHidraw = "/dev/" + entry;
    }

    if (!status.dongleConnected)
        return;

    QDir usbDir("/sys/bus/usb/devices");
    for (const QString &u : usbDir.entryList(QDir::Dirs | QDir::NoDotAndDotDot)) {
        QFile fv(usbDir.filePath(u + "/idVendor"));
        QFile fp(usbDir.filePath(u + "/idProduct"));
        if (!fv.open(QIODevice::ReadOnly) || !fp.open(QIODevice::ReadOnly))
            continue;
        if (QString::fromUtf8(fv.readAll()).trimmed().compare("19d2", Qt::CaseInsensitive) == 0 &&
            QString::fromUtf8(fp.readAll()).trimmed().compare("0616", Qt::CaseInsensitive) == 0) {
            QFile fb(usbDir.filePath(u + "/bcdDevice"));
            if (fb.open(QIODevice::ReadOnly)) {
                const QString bcd = QString::fromUtf8(fb.readAll()).trimmed();
                if (bcd.size() == 4)
                    status.dongleFirmware = QString("USB %1.%2").arg(bcd.left(2), bcd.right(2));
            }
            break;
        }
    }

    if (!status.dongleHidraw.isEmpty() &&
        ::access(status.dongleHidraw.toLocal8Bit().constData(), R_OK | W_OK) != 0 &&
        (errno == EACCES || errno == EPERM)) {
        status.donglePermissionError = true;
    }
}

DaoStatus queryFullStatus(const QString &macOverride) {
    DaoStatus st;
    probeDongle(st);

    const QString mac = macOverride.isEmpty() ? findDaoMac() : macOverride;
    st.mac = mac;
    if (mac.isEmpty() || !isBtConnected(mac))
        return st;

    QString err;
    const int fd = connectRfcomm(mac, 3500, &err);
    if (fd < 0) {
        st.btError = err;
        return st;
    }

    (void)recvSome(fd, 350, 80);

    st.btConnected = true;
    QByteArray d;

    if (xfer(fd, kFeatBasic, 0x05, {}, &d))
        st.firmware = QString::fromUtf8(d).remove('"');

    if (xfer(fd, kFeatEarbud, 0x00, {}, &d) && !d.isEmpty())
        st.primary = (static_cast<uint8_t>(d[0]) == 1) ? "right" : "left";

    QByteArray supBats;
    if (xfer(fd, kFeatBattery, 0x00, {}, &supBats) && !supBats.isEmpty()) {
        if (xfer(fd, kFeatBattery, 0x01, supBats, &d)) {
            for (int i = 0; i + 1 < d.size(); i += 2) {
                const uint8_t bid = static_cast<uint8_t>(d[i]);
                const uint8_t pct = static_cast<uint8_t>(d[i + 1]);
                if (bid == 1) st.batteryLeft = pct;
                else if (bid == 2) st.batteryRight = pct;
                else if (bid == 3) st.batteryCase = pct;
            }
        }
    }

    if (xfer(fd, kFeatCustom, 0x01, {}, &d) && d.size() >= 2) {
        st.modeType = static_cast<uint8_t>(d[0]);
        st.codecMode = static_cast<uint8_t>(d[1]);
    }

    if (xfer(fd, kFeatCustom, 0x03, {}, &d) && d.size() >= 4) {
        st.ledMode = static_cast<uint8_t>(d[0]);
        st.ledR = static_cast<uint8_t>(d[1]);
        st.ledG = static_cast<uint8_t>(d[2]);
        st.ledB = static_cast<uint8_t>(d[3]);
    }
    if (xfer(fd, kFeatCustom, 0x05, {}, &d) && !d.isEmpty())
        st.ledHall = (d[0] != 0);
    if (xfer(fd, kFeatCustom, 0x07, {}, &d) && !d.isEmpty())
        st.ledSpeed = static_cast<uint8_t>(d[0]);
    if (xfer(fd, kFeatCustom, 0x09, {}, &d) && !d.isEmpty())
        st.ledBrightness = static_cast<uint8_t>(d[0]);
    if (xfer(fd, kFeatCustom, 0x0E, {}, &d) && !d.isEmpty())
        st.language = static_cast<uint8_t>(d[0]);
    if (xfer(fd, kFeatCustom, 0x10, {}, &d) && !d.isEmpty())
        st.inEarDetection = (d[0] != 0);
    if (xfer(fd, kFeatCustom, 0x12, {}, &d) && d.size() >= 4) {
        st.touchLD = static_cast<uint8_t>(d[0]);
        st.touchLT = static_cast<uint8_t>(d[1]);
        st.touchRD = static_cast<uint8_t>(d[2]);
        st.touchRT = static_cast<uint8_t>(d[3]);
    }

    // Mimi Sound DSP (Feature 0x0E PDU 0x14, 0x16, 0x19, 0x1B — gracefully skipped on Global 9.0)
    if (xfer(fd, kFeatCustom, 0x14, {}, &d) && !d.isEmpty()) {
        st.mimiSupported = true;
        st.mimiEnabled = (d[0] != 0);
    }
    if (xfer(fd, kFeatCustom, 0x16, {}, &d) && !d.isEmpty()) {
        st.mimiSupported = true;
        st.mimiIntensity = static_cast<uint8_t>(d[0]);
    }
    if (xfer(fd, kFeatCustom, 0x19, {}, &d) && !d.isEmpty()) {
        st.mimiSupported = true;
        st.mimiPresetId = QString::fromLatin1(d.toHex());
    }
    if (xfer(fd, kFeatCustom, 0x1B, {}, &d) && !d.isEmpty()) {
        st.mimiSupported = true;
        st.mimiTechLevel = static_cast<uint8_t>(d[0]);
    }

    if (xfer(fd, kFeatAudioCuration, 0x00, QByteArray(1, 0x01), &d) && d.size() >= 2)
        st.ancEnabled = (d[1] != 0);
    if (xfer(fd, kFeatAudioCuration, 0x03, {}, &d) && !d.isEmpty())
        st.ancMode = static_cast<uint8_t>(d[0]);
    for (int slot = 1; slot <= 3; ++slot) {
        if (xfer(fd, kFeatAudioCuration, 0x08, QByteArray(1, static_cast<char>(slot)), &d) && d.size() >= 2) {
            const uint8_t v = static_cast<uint8_t>(d[1]);
            const int mapped = (v == 0xFF) ? -1 : static_cast<int>(v);
            if (slot == 1) st.ancToggle1 = mapped;
            else if (slot == 2) st.ancToggle2 = mapped;
            else if (slot == 3) st.ancToggle3 = mapped;
        }
    }

    if (xfer(fd, kFeatMusicEq, 0x00, {}, &d) && !d.isEmpty())
        st.eqEnabled = (d[0] != 0);
    if (xfer(fd, kFeatMusicEq, 0x02, {}, &d) && !d.isEmpty())
        st.eqPreset = static_cast<uint8_t>(d[0]);

    QByteArray eqRange;
    eqRange.append(static_cast<char>(0));
    eqRange.append(static_cast<char>(9));
    if (xfer(fd, kFeatMusicEq, 0x05, eqRange, &d) && d.size() >= 72) {
        const auto *b = reinterpret_cast<const uint8_t *>(d.constData());
        st.eqFreqs.resize(10);
        st.eqGains.resize(10);
        for (int idx = 0; idx < 10; ++idx) {
            const int off = 2 + idx * 7;
            st.eqFreqs[idx] = static_cast<int>((b[off] << 8) | b[off + 1]);
            const int16_t rawGain = static_cast<int16_t>((b[off + 5] << 8) | b[off + 6]);
            st.eqGains[idx] = std::round((rawGain / 60.0) * 10.0) / 10.0;
        }
    }

    queryStatistics(fd, st);

    ::close(fd);
    return st;
}

bool sendCommand(const QString &mac, uint8_t feature, uint8_t pduId,
                 const QByteArray &payload, QByteArray *responseOut, QString *errorOut) {
    const QString target = mac.isEmpty() ? findDaoMac() : mac;
    if (target.isEmpty()) {
        if (errorOut) *errorOut = "DAO TWS Bluetooth device not found";
        return false;
    }
    const int fd = connectRfcomm(target, 3500, errorOut);
    if (fd < 0)
        return false;
    (void)recvSome(fd, 350, 80);
    const bool ok = xfer(fd, feature, pduId, payload, responseOut);
    ::close(fd);
    if (!ok && errorOut && errorOut->isEmpty())
        *errorOut = "Command rejected or timed out";
    return ok;
}

}  // namespace Gaia
