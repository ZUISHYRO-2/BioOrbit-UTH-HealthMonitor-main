package org.bioorbit.mobile

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.SocketAddress
import kotlin.concurrent.thread

/**
 * Alertas a tripulantes cercanos por la red Wi-Fi (difusión UDP, puerto 50505).
 * Mismo formato JSON que src/alerts.py: las laptops con src/alert_listener.py reciben los avisos
 * del teléfono, y el teléfono recibe los de la consola de escritorio y de otros teléfonos.
 */
class NearbyAlerts(
    ctx: Context,
    private val deviceId: String,
    private val onAlert: (from: String, payload: JSONObject) -> Unit,
) {
    private val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    private val main = Handler(Looper.getMainLooper())
    private var lock: WifiManager.MulticastLock? = null
    @Volatile private var socket: DatagramSocket? = null
    @Volatile private var running = false

    fun start() {
        if (running) return
        running = true
        lock = wifi?.createMulticastLock("bioorbit-alerts")?.apply {
            setReferenceCounted(false)
            acquire()
        }
        thread(name = "bioorbit-udp", isDaemon = true) {
            try {
                val s = DatagramSocket(null as SocketAddress?).apply {
                    reuseAddress = true
                    broadcast = true
                    bind(InetSocketAddress(PORT))
                }
                socket = s
                val buf = ByteArray(8192)
                while (running) {
                    val pkt = DatagramPacket(buf, buf.size)
                    s.receive(pkt)
                    val text = String(pkt.data, 0, pkt.length, Charsets.UTF_8)
                    val payload = try { JSONObject(text) } catch (_: Exception) { continue }
                    if (payload.optString("origin") == deviceId) continue      // nuestro propio aviso
                    val from = pkt.address?.hostAddress.orEmpty()
                    main.post { onAlert(from, payload) }
                }
            } catch (_: Exception) {
                // socket cerrado al salir o red no disponible
            }
        }
    }

    fun stop() {
        running = false
        try { socket?.close() } catch (_: Exception) { }
        socket = null
        try { lock?.release() } catch (_: Exception) { }
    }

    /** Envía la alerta a toda la red local (dirección general y la de la subred Wi-Fi). */
    fun send(json: String, done: (ok: Boolean, msg: String) -> Unit) {
        thread(name = "bioorbit-udp-send", isDaemon = true) {
            val data = json.toByteArray(Charsets.UTF_8)
            var ok = false
            var err = ""
            for (addr in targets()) {
                try {
                    DatagramSocket().use { s ->
                        s.broadcast = true
                        s.send(DatagramPacket(data, data.size, addr, PORT))
                    }
                    ok = true
                } catch (e: Exception) {
                    err = e.message ?: e.javaClass.simpleName
                }
            }
            main.post {
                done(ok, if (ok) "Alerta enviada a la red local." else "No se pudo enviar por la red ($err). ¿Estás en Wi-Fi?")
            }
        }
    }

    private fun targets(): List<InetAddress> {
        val out = mutableListOf(InetAddress.getByName("255.255.255.255"))
        try {
            @Suppress("DEPRECATION")
            val dhcp = wifi?.dhcpInfo
            if (dhcp != null && dhcp.ipAddress != 0 && dhcp.netmask != 0) {
                val bc = (dhcp.ipAddress and dhcp.netmask) or dhcp.netmask.inv()
                val bytes = ByteArray(4) { k -> (bc shr (k * 8)).toByte() }   // dhcpInfo viene en little-endian
                out.add(InetAddress.getByAddress(bytes))
            }
        } catch (_: Exception) {
        }
        return out.distinct()
    }

    companion object {
        const val PORT = 50505
    }
}
