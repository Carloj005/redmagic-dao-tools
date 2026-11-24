package com.daobuds.app

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import kotlin.math.roundToInt

/**
 * Qualcomm GAIA v3 (Vendor 0x001D) + Redmagic Custom Feature 0x0E over Bluetooth Classic SPP/RFCOMM.
 */
object GaiaProtocol {
    val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")

    const val VENDOR_QTIL = 0x001D
    const val FEAT_BASIC = 0x00
    const val FEAT_EARBUD = 0x01
    const val FEAT_MUSIC_EQ = 0x05
    const val FEAT_HANDSET = 0x07
    const val FEAT_AUDIO_CURATION = 0x08
    const val FEAT_STATS = 0x0C
    const val FEAT_BATTERY = 0x0D
    const val FEAT_CUSTOM = 0x0E

    data class Frame(
        val vendor: Int,
        val feature: Int,
        val pduType: Int, // 0=CMD, 1=NOTIF, 2=RESP, 3=ERR
        val pduId: Int,
        val payload: ByteArray
    )

    data class DaoState(
        val connected: Boolean = false,
        val deviceName: String = "",
        val mac: String = "",
        val firmware: String = "",
        val primary: String = "",
        val batteryLeft: Int = -1,
        val batteryRight: Int = -1,
        val batteryCase: Int = -1,
        val modeType: Int = 2,       // 1=Game, 2=Music
        val codecMode: Int = 1,      // 1=Normal, 2=LHDC, 3=aptX Lossless
        val ancEnabled: Boolean = false,
        val ancMode: Int = 1,
        val ledMode: Int = 0,        // 0=Off, 1=Static, 2=Breath, 3=Rainbow
        val ledR: Int = 0,
        val ledG: Int = 255,
        val ledB: Int = 255,
        val ledHall: Boolean = false,
        val inEarDetection: Boolean = false,
        val language: Int = 1,
        val touchLD: Int = 1,
        val touchLT: Int = 4,
        val touchRD: Int = 3,
        val touchRT: Int = 2,
        val eqPreset: Int = 0,
        val eqGains: List<Float> = List(10) { 0f },
        val mimiSupported: Boolean = false,
        val mimiEnabled: Boolean = false,
        val mimiIntensity: Int = 0,
        val mimiPresetId: String = "",
        val radioStats: List<String> = emptyList(),
        val statusMsg: String = "",
        val alertMsg: String = ""
    )

    fun buildFrame(feature: Int, pduId: Int, payload: ByteArray = ByteArray(0)): ByteArray {
        val pdu = ((feature and 0x7F) shl 9) or (pduId and 0x7F)
        val out = ByteArray(8 + payload.size)
        out[0] = 0xFF.toByte()
        out[1] = 0x03
        out[2] = 0x00
        out[3] = (payload.size and 0xFF).toByte()
        out[4] = ((VENDOR_QTIL shr 8) and 0xFF).toByte()
        out[5] = (VENDOR_QTIL and 0xFF).toByte()
        out[6] = ((pdu shr 8) and 0xFF).toByte()
        out[7] = (pdu and 0xFF).toByte()
        System.arraycopy(payload, 0, out, 8, payload.size)
        return out
    }

    fun parseFrames(buf: ByteArray): List<Frame> {
        val list = mutableListOf<Frame>()
        var i = 0
        while (i < buf.size) {
            if ((buf[i].toInt() and 0xFF) != 0xFF || i + 8 > buf.size) {
                i++
                continue
            }
            val flags = buf[i + 2].toInt() and 0xFF
            val plen = buf[i + 3].toInt() and 0xFF
            val vendor = ((buf[i + 4].toInt() and 0xFF) shl 8) or (buf[i + 5].toInt() and 0xFF)
            val pdu = ((buf[i + 6].toInt() and 0xFF) shl 8) or (buf[i + 7].toInt() and 0xFF)
            val chk = if ((flags and 0x01) != 0) 1 else 0
            val end = i + 8 + plen + chk
            if (end > buf.size) break
            list.add(
                Frame(
                    vendor = vendor,
                    feature = (pdu shr 9) and 0x7F,
                    pduType = (pdu shr 7) and 0x03,
                    pduId = pdu and 0x7F,
                    payload = buf.copyOfRange(i + 8, i + 8 + plen)
                )
            )
            i = end
        }
        return list
    }

    @SuppressLint("MissingPermission")
    fun findPairedDaoDevice(adapter: BluetoothAdapter?): BluetoothDevice? {
        return adapter?.bondedDevices?.firstOrNull {
            it.name?.contains("DAO TWS", ignoreCase = true) == true
        }
    }

    @SuppressLint("MissingPermission")
    fun <T> withSession(device: BluetoothDevice, block: (Session) -> T): T {
        val sock = device.createRfcommSocketToServiceRecord(SPP_UUID)
        sock.connect()
        return sock.use { s ->
            val session = Session(s)
            session.drain(350) // Discard unsolicited "SPPOK" vendor 0x2828 banner
            block(session)
        }
    }

    class Session(private val sock: BluetoothSocket) {
        private val input = sock.inputStream
        private val output = sock.outputStream

        fun drain(waitMs: Long) {
            val end = System.currentTimeMillis() + waitMs
            val buf = ByteArray(1024)
            while (System.currentTimeMillis() < end) {
                if (input.available() > 0) {
                    input.read(buf, 0, minOf(buf.size, input.available()))
                } else {
                    Thread.sleep(25)
                }
            }
        }

        fun command(feature: Int, pduId: Int, payload: ByteArray = ByteArray(0)): Pair<Boolean, ByteArray> {
            output.write(buildFrame(feature, pduId, payload))
            output.flush()
            val rx = ByteArrayOutputStream()
            val deadline = System.currentTimeMillis() + 800
            val tmp = ByteArray(1024)
            while (System.currentTimeMillis() < deadline) {
                val avail = input.available()
                if (avail > 0) {
                    val n = input.read(tmp, 0, minOf(tmp.size, avail))
                    if (n > 0) rx.write(tmp, 0, n)
                    for (f in parseFrames(rx.toByteArray())) {
                        if (f.vendor == VENDOR_QTIL && f.feature == feature && f.pduId == pduId) {
                            if (f.pduType == 2) return true to f.payload
                            if (f.pduType == 3) return false to f.payload
                        }
                    }
                } else {
                    Thread.sleep(20)
                }
            }
            return false to ByteArray(0)
        }

        fun readAll(name: String, mac: String): DaoState {
            var st = DaoState(connected = true, deviceName = name, mac = mac)
            command(FEAT_BASIC, 0x05).let { (ok, d) ->
                if (ok) st = st.copy(firmware = String(d, Charsets.UTF_8).replace("\"", ""))
            }
            command(FEAT_EARBUD, 0x00).let { (ok, d) ->
                if (ok && d.isNotEmpty()) st = st.copy(primary = if (d[0].toInt() == 1) "Right" else "Left")
            }
            val (okSup, sup) = command(FEAT_BATTERY, 0x00)
            if (okSup && sup.isNotEmpty()) {
                val (okLv, lv) = command(FEAT_BATTERY, 0x01, sup)
                if (okLv) {
                    var bl = -1; var br = -1; var bc = -1
                    var idx = 0
                    while (idx + 1 < lv.size) {
                        val id = lv[idx].toInt() and 0xFF
                        val pct = lv[idx + 1].toInt() and 0xFF
                        when (id) { 1 -> bl = pct; 2 -> br = pct; 3 -> bc = pct }
                        idx += 2
                    }
                    st = st.copy(batteryLeft = bl, batteryRight = br, batteryCase = bc)
                }
            }
            command(FEAT_CUSTOM, 0x01).let { (ok, d) ->
                if (ok && d.size >= 2) st = st.copy(modeType = d[0].toInt() and 0xFF, codecMode = d[1].toInt() and 0xFF)
            }
            command(FEAT_CUSTOM, 0x03).let { (ok, d) ->
                if (ok && d.size >= 4) st = st.copy(
                    ledMode = d[0].toInt() and 0xFF,
                    ledR = d[1].toInt() and 0xFF,
                    ledG = d[2].toInt() and 0xFF,
                    ledB = d[3].toInt() and 0xFF
                )
            }
            command(FEAT_CUSTOM, 0x05).let { (ok, d) -> if (ok && d.isNotEmpty()) st = st.copy(ledHall = d[0].toInt() != 0) }
            command(FEAT_CUSTOM, 0x0E).let { (ok, d) -> if (ok && d.isNotEmpty()) st = st.copy(language = d[0].toInt() and 0xFF) }
            command(FEAT_CUSTOM, 0x10).let { (ok, d) -> if (ok && d.isNotEmpty()) st = st.copy(inEarDetection = d[0].toInt() != 0) }
            command(FEAT_CUSTOM, 0x12).let { (ok, d) ->
                if (ok && d.size >= 4) st = st.copy(
                    touchLD = d[0].toInt() and 0xFF,
                    touchLT = d[1].toInt() and 0xFF,
                    touchRD = d[2].toInt() and 0xFF,
                    touchRT = d[3].toInt() and 0xFF
                )
            }
            command(FEAT_AUDIO_CURATION, 0x00, byteArrayOf(0x01)).let { (ok, d) ->
                if (ok && d.size >= 2) st = st.copy(ancEnabled = d[1].toInt() != 0)
            }
            command(FEAT_AUDIO_CURATION, 0x03).let { (ok, d) ->
                if (ok && d.isNotEmpty()) st = st.copy(ancMode = d[0].toInt() and 0xFF)
            }
            command(FEAT_MUSIC_EQ, 0x02).let { (ok, d) ->
                if (ok && d.isNotEmpty()) st = st.copy(eqPreset = d[0].toInt() and 0xFF)
            }
            command(FEAT_MUSIC_EQ, 0x05, byteArrayOf(0, 9)).let { (ok, d) ->
                if (ok && d.size >= 72) {
                    val gains = MutableList(10) { 0f }
                    val bb = ByteBuffer.wrap(d).order(ByteOrder.BIG_ENDIAN)
                    for (band in 0 until 10) {
                        val raw = bb.getShort(2 + band * 7 + 5).toInt()
                        gains[band] = ((raw / 60.0f) * 10f).roundToInt() / 10f
                    }
                    st = st.copy(eqGains = gains)
                }
            }
            // Mimi Sound DSP (Feature 0x0E PDU 0x14, 0x16, 0x19)
            command(FEAT_CUSTOM, 0x14).let { (ok, d) ->
                if (ok && d.isNotEmpty()) st = st.copy(mimiSupported = true, mimiEnabled = d[0].toInt() != 0)
            }
            command(FEAT_CUSTOM, 0x16).let { (ok, d) ->
                if (ok && d.isNotEmpty()) st = st.copy(mimiSupported = true, mimiIntensity = d[0].toInt() and 0xFF)
            }
            command(FEAT_CUSTOM, 0x19).let { (ok, d) ->
                if (ok && d.isNotEmpty()) {
                    st = st.copy(mimiSupported = true, mimiPresetId = d.joinToString("") { "%02x".format(it) })
                }
            }
            // Live Radio Telemetry (Feature 0x0C STATISTICS)
            val statsOut = mutableListOf<String>()
            command(FEAT_STATS, 0x00, byteArrayOf(0x00, 0x00)).let { (ok, cats) ->
                if (ok && cats.size >= 3) {
                    var ci = 1
                    while (ci + 1 < cats.size) {
                        val cid = ((cats[ci].toInt() and 0xFF) shl 8) or (cats[ci + 1].toInt() and 0xFF)
                        ci += 2
                        command(FEAT_STATS, 0x01, byteArrayOf(((cid shr 8) and 0xFF).toByte(), (cid and 0xFF).toByte(), 0x00)).let { (ok2, sd) ->
                            if (ok2 && sd.size >= 3) {
                                var pos = 3
                                while (pos + 2 <= sd.size) {
                                    val sid = sd[pos].toInt() and 0xFF
                                    val vlen = sd[pos + 1].toInt() and 0xFF
                                    pos += 2
                                    if (pos + vlen > sd.size) break
                                    val hex = sd.copyOfRange(pos, pos + vlen).joinToString("") { "%02x".format(it) }
                                    pos += vlen
                                    statsOut.add("0x%04x:0x%02x = %s".format(cid, sid, hex))
                                }
                            }
                        }
                    }
                }
            }
            st = st.copy(radioStats = statsOut)
            val alert = when {
                (st.batteryLeft >= 0) != (st.batteryRight >= 0) ->
                    "Solo un auricolare connesso — controlla i contatti pogo-pin nel case"
                st.batteryLeft >= 0 && st.batteryRight >= 0 && kotlin.math.abs(st.batteryLeft - st.batteryRight) >= 20 ->
                    "Sbilanciamento batteria: L ${st.batteryLeft}% vs R ${st.batteryRight}%"
                else -> ""
            }
            return st.copy(statusMsg = "Connesso (${st.firmware})", alertMsg = alert)
        }
    }
}
