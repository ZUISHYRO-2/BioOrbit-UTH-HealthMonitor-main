package org.bioorbit.mobile

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetSocketAddress
import java.net.SocketAddress
import kotlin.concurrent.thread

/**
 * Encuentra solo el servidor de tripulación (crew_server/server.py) en la misma red Wi-Fi:
 * el servidor anuncia su dirección cada 2 s por UDP (puerto 50506) y aquí se escucha.
 */
class ServerFinder(ctx: Context, private val onFound: (url: String) -> Unit) {
    private val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    private val main = Handler(Looper.getMainLooper())
    private var lock: WifiManager.MulticastLock? = null
    @Volatile private var socket: DatagramSocket? = null
    @Volatile private var running = false
    private var lastUrl = ""
    private var lastAt = 0L

    fun start() {
        if (running) return
        running = true
        lock = wifi?.createMulticastLock("bioorbit-finder")?.apply {
            setReferenceCounted(false)
            acquire()
        }
        thread(name = "bioorbit-finder", isDaemon = true) {
            try {
                val s = DatagramSocket(null as SocketAddress?).apply {
                    reuseAddress = true
                    broadcast = true
                    bind(InetSocketAddress(PORT))
                }
                socket = s
                val buf = ByteArray(2048)
                while (running) {
                    val pkt = DatagramPacket(buf, buf.size)
                    s.receive(pkt)
                    val url = try {
                        JSONObject(String(pkt.data, 0, pkt.length, Charsets.UTF_8)).optString("bioorbit_server")
                    } catch (_: Exception) { "" }
                    if (!url.startsWith("http")) continue
                    val now = System.currentTimeMillis()
                    if (url == lastUrl && now - lastAt < 10_000) continue     // no repetir cada 2 s
                    lastUrl = url
                    lastAt = now
                    main.post { onFound(url) }
                }
            } catch (_: Exception) {
                // socket cerrado al salir o sin red
            }
        }
    }

    fun stop() {
        running = false
        try { socket?.close() } catch (_: Exception) { }
        socket = null
        try { lock?.release() } catch (_: Exception) { }
    }

    companion object {
        const val PORT = 50506
    }
}
