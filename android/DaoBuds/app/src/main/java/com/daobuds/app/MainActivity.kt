package com.daobuds.app

import android.Manifest
import android.bluetooth.BluetoothManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    private val vm: DaoViewModel by viewModels()

    private val permLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {
        val adapter = getSystemService(BluetoothManager::class.java)?.adapter
        vm.refresh(adapter)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val adapter = getSystemService(BluetoothManager::class.java)?.adapter

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permLauncher.launch(arrayOf(Manifest.permission.BLUETOOTH_CONNECT))
        } else {
            vm.refresh(adapter)
        }

        setContent {
            val darkScheme = darkColorScheme(
                primary = Color(0xFF00E5FF),
                secondary = Color(0xFFFF2E63),
                background = Color(0xFF0E0E10),
                surface = Color(0xFF16161B)
            )
            MaterialTheme(colorScheme = darkScheme) {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    DaoBudsScreen(vm = vm, adapter = adapter)
                }
            }
        }
    }
}

private val TOUCH_LABELS = listOf("Off", "Play/Pausa", "Prec.", "Succ.", "ANC", "Game")
private val EQ_LABELS = listOf("31", "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k")

@Composable
fun DaoBudsScreen(vm: DaoViewModel, adapter: android.bluetooth.BluetoothAdapter?) {
    val st by vm.state.collectAsState()
    val busy by vm.busy.collectAsState()
    var tab by remember { mutableIntStateOf(0) }

    var ld by remember(st.touchLD) { mutableIntStateOf(st.touchLD) }
    var lt by remember(st.touchLT) { mutableIntStateOf(st.touchLT) }
    var rd by remember(st.touchRD) { mutableIntStateOf(st.touchRD) }
    var rt by remember(st.touchRT) { mutableIntStateOf(st.touchRT) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.weight(1f)) {
                Text("DAO Buds", style = MaterialTheme.typography.headlineSmall)
                Text(st.statusMsg, style = MaterialTheme.typography.bodySmall, color = Color(0xFFA0A0B0))
            }
            Button(onClick = { vm.applyBatterySaver(adapter) }, enabled = st.connected && !busy) {
                Text("Eco")
            }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(onClick = { vm.refresh(adapter) }, enabled = !busy) {
                Text("Aggiorna")
            }
        }

        if (st.alertMsg.isNotEmpty()) {
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF332211))) {
                Text(st.alertMsg, color = Color(0xFFFFD666), modifier = Modifier.padding(12.dp))
            }
        }

        // Battery Row
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            BatteryCard("Sinistro", st.batteryLeft, Modifier.weight(1f))
            BatteryCard("Destro", st.batteryRight, Modifier.weight(1f))
            BatteryCard("Case", st.batteryCase, Modifier.weight(1f))
        }

        TabRow(selectedTabIndex = tab) {
            listOf("Audio", "Touch", "EQ", "Hardware").forEachIndexed { idx, title ->
                Tab(selected = tab == idx, onClick = { tab = idx }, text = { Text(title) })
            }
        }

        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            when (tab) {
                0 -> {
                    Text("Modalità & Codec", style = MaterialTheme.typography.titleMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(
                            selected = st.modeType == 2,
                            onClick = { vm.setModeAndCodec(adapter, 2, st.codecMode.coerceAtLeast(1)) },
                            label = { Text("Musica") }
                        )
                        FilterChip(
                            selected = st.modeType == 1,
                            onClick = { vm.setModeAndCodec(adapter, 1, 0) },
                            label = { Text("Game") }
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(1 to "Normale", 2 to "LHDC 5.0", 3 to "aptX Lossless").forEach { (id, lbl) ->
                            FilterChip(
                                selected = st.modeType == 2 && st.codecMode == id,
                                onClick = { vm.setModeAndCodec(adapter, 2, id) },
                                label = { Text(lbl) }
                            )
                        }
                    }
                    HorizontalDivider()
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        Text("ANC Attivo (Mode ${st.ancMode})", modifier = Modifier.weight(1f))
                        Switch(checked = st.ancEnabled, onCheckedChange = { vm.setAncEnabled(adapter, it) })
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf(1, 2, 5, 6).forEach { m ->
                            OutlinedButton(onClick = { vm.setAncMode(adapter, m) }) { Text("M$m") }
                        }
                    }
                }
                1 -> {
                    Text("Rimappatura Touch (Feature 0x0E)", style = MaterialTheme.typography.titleMedium)
                    TouchSelector("Sinistro Doppio Tocco", ld) { ld = it }
                    TouchSelector("Sinistro Triplo Tocco", lt) { lt = it }
                    TouchSelector("Destro Doppio Tocco", rd) { rd = it }
                    TouchSelector("Destro Triplo Tocco", rt) { rt = it }
                    Button(
                        onClick = { vm.setTouch(adapter, ld, lt, rd, rt) },
                        enabled = st.connected && !busy,
                        modifier = Modifier.fillMaxWidth()
                    ) { Text("Salva Mappatura Touch") }
                }
                2 -> {
                    Text("Equalizzatore 10 Bande", style = MaterialTheme.typography.titleMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(onClick = { vm.setEqPreset(adapter, 0) }) { Text("Default") }
                        OutlinedButton(onClick = { vm.setEqPreset(adapter, 0x3F) }) { Text("User EQ") }
                    }
                    st.eqGains.forEachIndexed { idx, gain ->
                        var sliderVal by remember(gain) { mutableFloatStateOf(gain) }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("${EQ_LABELS[idx]}Hz", modifier = Modifier.width(48.dp))
                            Slider(
                                value = sliderVal,
                                onValueChange = { sliderVal = it },
                                onValueChangeFinished = { vm.setEqBand(adapter, idx, sliderVal) },
                                valueRange = -12f..12f,
                                modifier = Modifier.weight(1f)
                            )
                            Text("${"%.1f".format(sliderVal)}dB", modifier = Modifier.width(52.dp))
                        }
                    }
                }
                3 -> {
                    Text("LED RGB", style = MaterialTheme.typography.titleMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(0 to "Off", 1 to "Fisso", 2 to "Respiro", 3 to "Rainbow").forEach { (id, lbl) ->
                            FilterChip(
                                selected = st.ledMode == id,
                                onClick = { vm.setLed(adapter, id, 0, 255, 255) },
                                label = { Text(lbl) }
                            )
                        }
                    }
                    HorizontalDivider()
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        Text("Rilevamento Indossamento (In-Ear)", modifier = Modifier.weight(1f))
                        Switch(checked = st.inEarDetection, onCheckedChange = { vm.setInEar(adapter, it) })
                    }
                    Text("Multipoint Bluetooth", style = MaterialTheme.typography.titleMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { vm.setMultipoint(adapter, false) }) { Text("Single-Point (Stabile)") }
                        OutlinedButton(onClick = { vm.setMultipoint(adapter, true) }) { Text("Multipoint ON") }
                    }
                }
            }
        }
    }
}

@Composable
private fun BatteryCard(label: String, pct: Int, modifier: Modifier) {
    Card(modifier = modifier) {
        Column(modifier = Modifier.padding(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(label, style = MaterialTheme.typography.labelSmall, color = Color(0xFFA0A0B0))
            Text(if (pct >= 0) "$pct%" else "--", style = MaterialTheme.typography.titleLarge)
        }
    }
}

@Composable
private fun TouchSelector(label: String, current: Int, onSelect: (Int) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            TOUCH_LABELS.forEachIndexed { idx, name ->
                FilterChip(selected = current == idx, onClick = { onSelect(idx) }, label = { Text(name) })
            }
        }
    }
}
