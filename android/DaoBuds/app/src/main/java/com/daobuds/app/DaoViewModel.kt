package com.daobuds.app

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.roundToInt

class DaoViewModel : ViewModel() {
    private val _state = MutableStateFlow(GaiaProtocol.DaoState(statusMsg = "Tocca Aggiorna per connettere"))
    val state: StateFlow<GaiaProtocol.DaoState> = _state.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    @SuppressLint("MissingPermission")
    fun refresh(adapter: BluetoothAdapter?) {
        if (_busy.value) return
        val dev = GaiaProtocol.findPairedDaoDevice(adapter)
        if (dev == null) {
            _state.value = _state.value.copy(
                connected = false,
                statusMsg = "DAO TWS non trovato tra i dispositivi Bluetooth associati"
            )
            return
        }
        _busy.value = true
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val st = GaiaProtocol.withSession(dev) { it.readAll(dev.name ?: "DAO TWS", dev.address) }
                _state.value = st
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    connected = false,
                    statusMsg = "Errore Bluetooth: ${e.message}"
                )
            } finally {
                _busy.value = false
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun runCmd(adapter: BluetoothAdapter?, okMsg: String, block: (GaiaProtocol.Session) -> Boolean) {
        if (_busy.value) return
        val dev = GaiaProtocol.findPairedDaoDevice(adapter) ?: return
        _busy.value = true
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val st = GaiaProtocol.withSession(dev) { session ->
                    val ok = block(session)
                    val refreshed = session.readAll(dev.name ?: "DAO TWS", dev.address)
                    refreshed.copy(statusMsg = if (ok) okMsg else "Comando rifiutato dal firmware")
                }
                _state.value = st
            } catch (e: Exception) {
                _state.value = _state.value.copy(statusMsg = "Errore: ${e.message}")
            } finally {
                _busy.value = false
            }
        }
    }

    fun setModeAndCodec(adapter: BluetoothAdapter?, mode: Int, codec: Int) =
        runCmd(adapter, "Modalità aggiornata") {
            it.command(GaiaProtocol.FEAT_CUSTOM, 0x02, byteArrayOf(mode.toByte(), (if (mode == 1) 0 else codec).toByte())).first
        }

    fun setAncEnabled(adapter: BluetoothAdapter?, enabled: Boolean) =
        runCmd(adapter, if (enabled) "ANC attivato" else "ANC disattivato") {
            it.command(GaiaProtocol.FEAT_AUDIO_CURATION, 0x01, byteArrayOf(0x01, if (enabled) 1 else 0)).first
        }

    fun setAncMode(adapter: BluetoothAdapter?, mode: Int) =
        runCmd(adapter, "Modalità ANC $mode") {
            it.command(GaiaProtocol.FEAT_AUDIO_CURATION, 0x04, byteArrayOf(mode.toByte())).first
        }

    fun setTouch(adapter: BluetoothAdapter?, ld: Int, lt: Int, rd: Int, rt: Int) =
        runCmd(adapter, "Comandi touch salvati") {
            it.command(GaiaProtocol.FEAT_CUSTOM, 0x13, byteArrayOf(ld.toByte(), lt.toByte(), rd.toByte(), rt.toByte())).first
        }

    fun setEqPreset(adapter: BluetoothAdapter?, preset: Int) =
        runCmd(adapter, "Preset EQ applicato") {
            it.command(GaiaProtocol.FEAT_MUSIC_EQ, 0x03, byteArrayOf(preset.toByte())).first
        }

    fun setEqBand(adapter: BluetoothAdapter?, band: Int, db: Float) =
        runCmd(adapter, "Banda EQ aggiornata") {
            val raw = (db.coerceIn(-12f, 12f) * 60f).roundToInt().toShort()
            val pl = ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN)
                .put(band.toByte()).put(band.toByte()).putShort(raw).array()
            it.command(GaiaProtocol.FEAT_MUSIC_EQ, 0x06, pl).first
        }

    fun setLed(adapter: BluetoothAdapter?, mode: Int, r: Int, g: Int, b: Int) =
        runCmd(adapter, "LED aggiornato") {
            val pl = if (mode == 0) byteArrayOf(1, 0, 0, 0)
                     else byteArrayOf(mode.toByte(), r.toByte(), g.toByte(), b.toByte())
            it.command(GaiaProtocol.FEAT_CUSTOM, 0x04, pl).first
        }

    fun setInEar(adapter: BluetoothAdapter?, enabled: Boolean) =
        runCmd(adapter, if (enabled) "In-Ear attivato" else "In-Ear disattivato") {
            it.command(GaiaProtocol.FEAT_CUSTOM, 0x11, byteArrayOf(if (enabled) 1 else 0)).first
        }

    fun setMultipoint(adapter: BluetoothAdapter?, enabled: Boolean) =
        runCmd(adapter, if (enabled) "Multipoint attivo" else "Single-Point stabile attivo") {
            it.command(GaiaProtocol.FEAT_HANDSET, 0x00, byteArrayOf(if (enabled) 1 else 0)).first
        }

    fun applyBatterySaver(adapter: BluetoothAdapter?) =
        runCmd(adapter, "Salva-Batteria e Stabilità applicati") { s ->
            var ok = s.command(GaiaProtocol.FEAT_CUSTOM, 0x04, byteArrayOf(1, 0, 0, 0)).first
            ok = s.command(GaiaProtocol.FEAT_CUSTOM, 0x06, byteArrayOf(0)).first && ok
            ok = s.command(GaiaProtocol.FEAT_CUSTOM, 0x11, byteArrayOf(0)).first && ok
            ok = s.command(GaiaProtocol.FEAT_HANDSET, 0x00, byteArrayOf(0)).first && ok
            ok = s.command(GaiaProtocol.FEAT_CUSTOM, 0x02, byteArrayOf(2, 1)).first && ok
            ok
        }
}
