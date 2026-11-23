#include "gaia.h"

#include <QDir>
#include <QFile>
#include <QProcess>
#include <QRegularExpression>
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

    // Use non-blocking connect with poll() so unreachable earbuds never hang the worker.
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

    // Read bcdDevice from sysfs USB parent if available (e.g. "2967" -> "29.67").
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

    // Drain the unsolicited "SPPOK" vendor 0x2828 banner sent right after connect.
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
