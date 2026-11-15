package org.bioorbit.mobile

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * Cliente Bluetooth LE del reloj: busca dispositivos con el perfil estándar Heart Rate (0x180D),
 * se conecta y recibe la medición 0x2A37 (BPM + intervalos RR). Mismo protocolo que src/ble_watch.py,
 * así que funciona con BioOrbit Watch Bridge (Pixel Watch / Wear OS) y con bandas Polar, Garmin, etc.
 *
 * Eventos al JS: watch_devices, watch_status, watch_hr.
 */
@SuppressLint("MissingPermission") // MainActivity pide los permisos antes de llamar aquí
class WatchBle(private val ctx: Context, private val emit: (String, String) -> Unit) {

    private val adapter = (ctx.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter
    private val main = Handler(Looper.getMainLooper())
    private val found = LinkedHashMap<String, JSONObject>()
    private var gatt: BluetoothGatt? = null
    private var deviceName = "Reloj"
    private var scanning = false
    private var manualDisconnect = false

    // ------------------------------------------------------------------ escaneo
    fun scan() {
        val a = adapter ?: return status("error", "Este teléfono no tiene Bluetooth.")
        if (!a.isEnabled) return status("error", "Activa el Bluetooth del teléfono.")
        val scanner = a.bluetoothLeScanner ?: return status("error", "Bluetooth LE no disponible.")
        if (scanning) return
        found.clear()
        try {
            scanner.startScan(null, ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), scanCallback)
        } catch (e: SecurityException) {
            return status("error", "Falta el permiso de Bluetooth.")
        }
        scanning = true
        status("scanning", "Buscando relojes por Bluetooth (10 s)…")
        main.postDelayed({
            stopScan()
            val list = found.values.sortedWith(compareByDescending<JSONObject> { it.optBoolean("hr") }.thenByDescending { it.optInt("rssi") })
            emit("watch_devices", JSONArray(list).toString())
        }, SCAN_MS)
    }

    private fun stopScan() {
        if (!scanning) return
        scanning = false
        try {
            adapter?.bluetoothLeScanner?.stopScan(scanCallback)
        } catch (_: Exception) {
        }
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val record = result.scanRecord
            val name = (record?.deviceName ?: safeName(result.device)).orEmpty().trim()
            val hr = record?.serviceUuids?.any { it.uuid == HR_SERVICE } == true
            val watchLike = hr || KEYWORDS.any { name.lowercase().contains(it) }
            if (!watchLike) return
            val addr = result.device.address
            found[addr] = JSONObject()
                .put("name", name.ifEmpty { "BLE-$addr" })
                .put("address", addr)
                .put("rssi", result.rssi)
                .put("hr", hr)
        }

        override fun onScanFailed(errorCode: Int) {
            scanning = false
            status("error", "Falló la búsqueda Bluetooth (código $errorCode).")
        }
    }

    private fun safeName(d: BluetoothDevice): String? = try {
        d.name
    } catch (_: SecurityException) {
        null
    }

    // ------------------------------------------------------------------ conexión
    fun connect(address: String) {
        stopScan()
        closeGatt()
        val a = adapter ?: return status("error", "Este teléfono no tiene Bluetooth.")
        deviceName = found[address]?.optString("name") ?: "Reloj"
        manualDisconnect = false
        try {
            val device = a.getRemoteDevice(address)
            gatt = device.connectGatt(ctx, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
            status("connecting", "Conectando a $deviceName…")
        } catch (e: Exception) {
            status("error", "No pude conectar: ${e.message}")
        }
    }

    fun disconnect(silent: Boolean = false) {
        manualDisconnect = true
        stopScan()
        closeGatt()
        if (!silent) status("off", "Reloj desconectado.")
    }

    private fun closeGatt() {
        val g = gatt ?: return
        gatt = null
        try {
            g.disconnect()
            g.close()
        } catch (_: Exception) {
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, st: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                status("connected", "Conectado a $deviceName. Suscribiendo pulso…")
                main.post { try { g.discoverServices() } catch (_: SecurityException) { } }
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                try { g.close() } catch (_: Exception) { }
                if (gatt == g) gatt = null
                if (!manualDisconnect) status("lost", "Se perdió la conexión con $deviceName.")
            }
        }

        override fun onServicesDiscovered(g: BluetoothGatt, st: Int) {
            val ch = g.getService(HR_SERVICE)?.getCharacteristic(HR_MEASUREMENT)
            if (ch == null) {
                status("error", "$deviceName no anuncia el perfil cardíaco. Abre BioOrbit Watch Bridge en el reloj.")
                return
            }
            try {
                g.setCharacteristicNotification(ch, true)
                val cccd = ch.getDescriptor(CCCD) ?: return
                if (Build.VERSION.SDK_INT >= 33) {
                    g.writeDescriptor(cccd, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                } else {
                    @Suppress("DEPRECATION")
                    cccd.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    @Suppress("DEPRECATION")
                    g.writeDescriptor(cccd)
                }
            } catch (e: SecurityException) {
                status("error", "Falta el permiso de Bluetooth.")
            }
        }

        // Android 13+
        override fun onCharacteristicChanged(g: BluetoothGatt, ch: BluetoothGattCharacteristic, value: ByteArray) {
            if (ch.uuid == HR_MEASUREMENT) handle(value)
        }

        // Android 8–12
        @Deprecated("Deprecated in Java")
        override fun onCharacteristicChanged(g: BluetoothGatt, ch: BluetoothGattCharacteristic) {
            @Suppress("DEPRECATION")
            val v = ch.value ?: return
            if (ch.uuid == HR_MEASUREMENT) handle(v)
        }
    }

    private fun handle(value: ByteArray) {
        val m = parseHeartRate(value) ?: return
        emit("watch_hr", JSONObject().put("bpm", m.bpm).put("rr", JSONArray(m.rrMs)).put("contact", m.contact).toString())
    }

    private fun status(state: String, msg: String) =
        emit("watch_status", MainActivity.status(state, msg, deviceName.takeIf { state != "scanning" }))

    data class HeartRate(val bpm: Int, val rrMs: List<Double>, val contact: String)

    companion object {
        private const val SCAN_MS = 10_000L
        val HR_SERVICE: UUID = UUID.fromString("0000180d-0000-1000-8000-00805f9b34fb")
        val HR_MEASUREMENT: UUID = UUID.fromString("00002a37-0000-1000-8000-00805f9b34fb")
        val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        private val KEYWORDS = listOf(
            "watch", "pixel", "galaxy", "wear", "google", "samsung", "garmin", "fitbit", "polar",
            "amazfit", "xiaomi", "mi band", "coros", "suunto", "whoop", "hrm", "heart", "bioorbit"
        )

        /** Decodifica la característica 0x2A37 (Bluetooth SIG Heart Rate Measurement). */
        fun parseHeartRate(raw: ByteArray): HeartRate? {
            if (raw.size < 2) return null
            val flags = raw[0].toInt() and 0xff
            var i = 1
            val bpm: Int
            if (flags and 0x01 != 0) {
                if (raw.size < 3) return null
                bpm = (raw[1].toInt() and 0xff) or ((raw[2].toInt() and 0xff) shl 8)
                i = 3
            } else {
                bpm = raw[1].toInt() and 0xff
                i = 2
            }
            val contact = when ((flags shr 1) and 0x03) {
                2 -> "Sin contacto"
                3 -> "Contacto firme"
                else -> "No soportado"
            }
            if (flags and 0x08 != 0) i += 2
            val rr = mutableListOf<Double>()
            if (flags and 0x10 != 0) {
                while (i + 1 < raw.size) {
                    val v = (raw[i].toInt() and 0xff) or ((raw[i + 1].toInt() and 0xff) shl 8)
                    val ms = v / 1024.0 * 1000.0
                    if (ms in 250.0..2200.0) rr.add(Math.round(ms * 100) / 100.0)
                    i += 2
                }
            }
            return HeartRate(bpm, rr, contact)
        }
    }
}
