package org.bioorbit.mobile

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.SearchManager
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.MediaStore
import android.provider.Settings
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.webkit.WebViewAssetLoader
import org.json.JSONObject
import java.util.UUID

/**
 * BioOrbit móvil.
 *
 * La interfaz (HUD, Luma, chat, alertas) vive en assets/ como HTML/JS y se muestra en un WebView.
 * Esta actividad le da al JS lo que solo el teléfono puede hacer, mediante window.Android:
 *   - Bluetooth LE para el reloj (WatchBle)
 *   - Alertas a tripulantes cercanos por la red Wi-Fi (NearbyAlerts, compatible con src/alert_listener.py)
 *   - Notificaciones y vibración (Notifier)
 * Kotlin responde al JS con BioNative.emit(evento, json).
 */
class MainActivity : Activity() {

    private lateinit var web: WebView
    private lateinit var watch: WatchBle
    private lateinit var alerts: NearbyAlerts
    private lateinit var finder: ServerFinder
    @Volatile private var foundServer = ""
    private lateinit var notifier: Notifier
    private lateinit var speaker: Speaker
    private lateinit var voice: VoiceInput
    private lateinit var ai: LumaAI
    private lateinit var music: MusicPlayer
    private var pendingMusic: MusicReq? = null
    private var resumed = false
    private val bgMode get() = getSharedPreferences("bioorbit", MODE_PRIVATE).getBoolean("background", true)
    private var pendingListen = false
    private var wantContinuous = false
    private var permsInFlight = false
    private val ui = Handler(Looper.getMainLooper())
    private val resumeAfterSpeech = Runnable { voice.resume("tts") }
    private lateinit var deviceId: String
    private var pendingCamera: PermissionRequest? = null
    private var pendingScan = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val prefs = getSharedPreferences("bioorbit", MODE_PRIVATE)
        deviceId = prefs.getString("device_id", null) ?: ("android-" + UUID.randomUUID().toString().take(8)).also {
            prefs.edit().putString("device_id", it).apply()
        }

        notifier = Notifier(this)
        speaker = Speaker(this) { event, json ->
            emit(event, json)
            // cuando Luma termina de hablar, el micrófono vuelve a escuchar (escucha permanente)
            if (!JSONObject(json).optBoolean("speaking")) runOnUiThread {
                voice.resume("tts")
                music.duck(false)      // la música vuelve a su volumen cuando Luma termina
            }
        }
        voice = VoiceInput(this) { event, json -> emit(event, json) }
        ai = LumaAI(this) { event, json -> emit(event, json) }
        music = MusicPlayer(this) { event, json -> emit(event, json) }
        music.onChange = { m ->
            if (m.isActive()) {
                voice.forceUnmute()    // con música no se silencia el volumen multimedia
                ensureService()
            }
            BioService.update(this, if (m.isActive()) "♪ ${m.title}" + (if (m.playing) "" else " (en pausa)") else "Luma te escucha")
        }
        voice.muteAllowed = { !music.isActive() }
        BioService.onExit = { runOnUiThread { finishAndRemoveTask() } }
        watch = WatchBle(this) { event, json -> emit(event, json) }
        finder = ServerFinder(this) { url ->
            foundServer = url
            emit("server_found", JSONObject().put("url", url).toString())
        }
        alerts = NearbyAlerts(this, deviceId) { from, payload ->
            emit("alert_received", JSONObject().put("from", from).put("payload", payload).toString())
            notifier.show("BioOrbit · alerta cercana", payload.optString("message", "Alerta BioOrbit"), urgent = true)
            notifier.vibrate(1200)
        }

        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        web = WebView(this).apply {
            setBackgroundColor(BG)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            // el servidor de tripulación en la red local es http:// (la página es https://appassets…)
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                    loader.shouldInterceptRequest(request.url)

                // la app no navega fuera de sus propios archivos
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                    request.url.host != HOST
            }
            webChromeClient = object : WebChromeClient() {
                override fun onPermissionRequest(request: PermissionRequest) {
                    runOnUiThread { handleCameraRequest(request) }
                }
            }
            addJavascriptInterface(Bridge(), "Android")
            // que Android no detenga la interfaz cuando la app está en segundo plano
            setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, false)
        }

        val root = FrameLayout(this).apply {
            setBackgroundColor(BG)
            addView(web, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        }
        applySystemBarPadding(root)
        setContentView(root)

        alerts.start()
        finder.start()
        web.loadUrl("https://$HOST/assets/index.html")
        askStartupPermissions()
    }

    // ------------------------------------------------------------------ puente JS
    inner class Bridge {
        @JavascriptInterface
        fun deviceId(): String = deviceId

        @JavascriptInterface
        fun watchScan() = runOnUiThread {
            if (hasAll(blePermissions())) watch.scan()
            else {
                pendingScan = true
                requestPermissions(blePermissions(), REQ_BLE)
            }
        }

        @JavascriptInterface
        fun watchConnect(address: String) = runOnUiThread {
            if (hasAll(blePermissions())) watch.connect(address)
            else emit("watch_status", status("error", "Falta el permiso de Bluetooth."))
        }

        @JavascriptInterface
        fun watchDisconnect() = runOnUiThread { watch.disconnect() }

        @JavascriptInterface
        fun sendAlert(json: String) {
            alerts.send(json) { ok, msg ->
                emit("alert_sent", JSONObject().put("ok", ok).put("msg", msg).toString())
            }
        }

        @JavascriptInterface
        fun showNotification(title: String, text: String, urgent: Boolean) = notifier.show(title, text, urgent)

        @JavascriptInterface
        fun vibrate(ms: Int) = notifier.vibrate(ms.toLong())

        /** Patrón "espera,vibra,espera,vibra…" en milisegundos, p. ej. "0,400,200,400". */
        @JavascriptInterface
        fun vibratePattern(csv: String) {
            val pattern = csv.split(',').mapNotNull { it.trim().toLongOrNull()?.coerceIn(0, 3000) }.take(20)
            if (pattern.size >= 2) notifier.vibratePattern(pattern.toLongArray())
        }

        @JavascriptInterface
        fun speak(text: String, urgent: Boolean) = runOnUiThread {
            voice.pause("tts")        // no escucharse a sí misma y devolver el volumen antes de hablar
            music.duck(true)          // baja la música mientras Luma habla
            speaker.speak(text.take(400), urgent)
            // por si el motor de voz no avisa que terminó: el micrófono vuelve a escuchar de todos modos
            ui.removeCallbacks(resumeAfterSpeech)
            ui.postDelayed(resumeAfterSpeech, 2500L + text.length.coerceAtMost(400) * 110L)
        }

        @JavascriptInterface
        fun stopSpeaking() = runOnUiThread {
            speaker.stop()
            voice.resume("tts")
        }

        // ---- servidor de tripulación
        /** Último servidor anunciado en la red Wi-Fi ("" si ninguno). */
        @JavascriptInterface
        fun serverFound(): String = foundServer

        // ---- música
        /** query: lo que pidió · station: id de radio para géneros ("" si no) · generic: «pon música» sin más */
        @JavascriptInterface
        fun musicPlay(query: String, station: String, generic: Boolean) = runOnUiThread { playMusic(MusicReq(query, station, generic)) }

        /** opts: {app:"spotify"|"youtube"|"" , focus:"artist"|"any", preferApp:true} */
        @JavascriptInterface
        fun musicPlay2(query: String, station: String, generic: Boolean, opts: String) = runOnUiThread {
            val o = try { JSONObject(opts) } catch (_: Exception) { JSONObject() }
            playMusic(MusicReq(query, station, generic, o.optString("app"), o.optString("focus", "any"), o.optBoolean("preferApp", true)))
        }

        @JavascriptInterface
        fun musicControl(cmd: String) = runOnUiThread {
            when (cmd) {
                "pause" -> music.pause()
                "resume" -> music.resume()
                "next" -> music.next()
                "stop" -> music.stop()
                "up" -> music.volume(true)
                "down" -> music.volume(false)
            }
        }

        @JavascriptInterface
        fun musicDuck(on: Boolean) = runOnUiThread { music.duck(on) }

        @JavascriptInterface
        fun musicStations(): String =
            org.json.JSONArray(MusicPlayer.STATIONS.map { JSONObject().put("id", it.id).put("name", it.name).put("desc", it.desc) }).toString()

        // ---- segundo plano
        @JavascriptInterface
        fun setBackground(on: Boolean) = runOnUiThread {
            getSharedPreferences("bioorbit", MODE_PRIVATE).edit().putBoolean("background", on).apply()
            if (on) ensureService() else if (!music.isActive()) BioService.stop(this@MainActivity)
        }

        @JavascriptInterface
        fun backgroundInfo(): String = JSONObject()
            .put("on", bgMode).put("service", BioService.running)
            .put("battery", (getSystemService(POWER_SERVICE) as PowerManager).isIgnoringBatteryOptimizations(packageName))
            .toString()

        /** Pide quitar la optimización de batería para que Android no duerma la app. */
        @JavascriptInterface
        fun openBatterySettings() = runOnUiThread {
            try {
                @Suppress("BatteryLife")
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
            } catch (_: Exception) {
                try { startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) } catch (_: Exception) { }
            }
        }

        // ---- escuchar (micrófono)
        @JavascriptInterface
        fun listenAvailable(): Boolean = true

        @JavascriptInterface
        fun listenStart() = runOnUiThread {
            speaker.stop()
            if (hasMic()) voice.startOnce()
            else {
                pendingListen = true
                requestMic()
            }
        }

        @JavascriptInterface
        fun listenStop() = runOnUiThread {
            voice.stop()
            wantContinuous = false
            emit("listen_state", JSONObject().put("state", "idle").toString())
        }

        @JavascriptInterface
        fun listenForceOnline(on: Boolean) = runOnUiThread { voice.forceOnline(on) }

        @JavascriptInterface
        fun micGranted(): Boolean = hasMic()

        /** Escucha permanente: el micrófono queda escuchando mientras la app está abierta. */
        @JavascriptInterface
        fun listenContinuous(on: Boolean) = runOnUiThread {
            wantContinuous = on
            if (!on) voice.setContinuous(false)
            else if (hasMic()) { voice.setContinuous(true); ensureService() }
            else requestMic()
        }

        // ---- IA (Claude)
        @JavascriptInterface
        fun aiHasKey(): Boolean = ai.hasKey()

        @JavascriptInterface
        fun aiSetKey(key: String) = ai.setKey(key)

        @JavascriptInterface
        fun aiClearKey() = ai.clearKey()

        @JavascriptInterface
        fun aiModel(): String = ai.label()

        @JavascriptInterface
        fun aiChat(id: String, system: String, messagesJson: String) = ai.chat(id, system, messagesJson)
    }

    private fun emit(event: String, json: String) = runOnUiThread {
        if (!isDestroyed) {
            web.evaluateJavascript(
                "window.BioNative && BioNative.emit(${JSONObject.quote(event)}, ${JSONObject.quote(json)})", null
            )
        }
    }

    // ------------------------------------------------------------------ permisos
    private fun handleCameraRequest(request: PermissionRequest) {
        if (PermissionRequest.RESOURCE_VIDEO_CAPTURE !in request.resources) {
            request.deny()
            return
        }
        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            request.grant(arrayOf(PermissionRequest.RESOURCE_VIDEO_CAPTURE))
        } else {
            pendingCamera = request
            // si ya está abierto el diálogo de permisos de inicio, se resuelve cuando conteste
            if (!permsInFlight) requestPermissions(arrayOf(Manifest.permission.CAMERA), REQ_CAMERA)
        }
    }

    private fun hasMic() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun requestMic() {
        if (!permsInFlight) requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
    }

    /** Después de cualquier respuesta de permisos: atiende lo que quedó pendiente. */
    private fun resolvePending() {
        pendingCamera?.let {
            if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
                it.grant(arrayOf(PermissionRequest.RESOURCE_VIDEO_CAPTURE))
            else it.deny()
        }
        pendingCamera = null
        pendingMusic?.let { pendingMusic = null; playMusic(it, askedAlready = true) }
        if (hasMic()) {
            if (wantContinuous) { voice.setContinuous(true); ensureService() }
            else if (pendingListen) voice.startOnce()
        } else if (wantContinuous || pendingListen) {
            emit("listen_error", JSONObject().put("code", -3).put("msg", "Sin permiso del micrófono no puedo escucharte.").toString())
        }
        pendingListen = false
    }

    private fun blePermissions(): Array<String> =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        else arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)

    private fun hasAll(perms: Array<String>) =
        perms.all { checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }

    /** Todos los permisos de inicio en un solo diálogo (Android solo atiende una solicitud a la vez). */
    private fun askStartupPermissions() {
        val perms = mutableListOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33) perms.add(Manifest.permission.POST_NOTIFICATIONS)
        val missing = perms.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) {
            permsInFlight = true
            requestPermissions(missing.toTypedArray(), REQ_STARTUP)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        val granted = grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }
        when (requestCode) {
            REQ_STARTUP, REQ_CAMERA, REQ_MIC, REQ_AUDIO_FILES -> {
                permsInFlight = false
                resolvePending()
            }
            REQ_BLE -> {
                if (pendingScan && granted) watch.scan()
                else if (!granted) emit("watch_status", status("error", "Sin permiso de Bluetooth no puedo buscar el reloj."))
                pendingScan = false
            }
        }
    }

    // ------------------------------------------------------------------ pantalla
    private fun applySystemBarPadding(root: View) {
        @Suppress("DEPRECATION")
        run {
            window.statusBarColor = BG
            window.navigationBarColor = BG
        }
        root.setOnApplyWindowInsetsListener { v, insets ->
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.ime())
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            } else {
                @Suppress("DEPRECATION")
                v.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                    insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            }
            insets
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        // regresa a la pestaña Monitor; ahí, «atrás» minimiza la app (sigue en segundo plano) en vez de cerrarla
        web.evaluateJavascript(
            "(function(){var b=document.querySelector('.tabs button.active');" +
                "if(b&&b.dataset.view!=='monitor'){document.querySelector('.tabs button[data-view=monitor]').click();return 1}return 0})()"
        ) { r ->
            if (r == "1") return@evaluateJavascript
            if (bgMode) moveTaskToBack(true) else @Suppress("DEPRECATION") super.onBackPressed()
        }
    }

    // ------------------------------------------------------------------ segundo plano y música
    private fun ensureService() {
        if ((bgMode || music.isActive()) && !BioService.running) BioService.start(this)
    }

    private fun audioPermission() =
        if (Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_AUDIO else Manifest.permission.READ_EXTERNAL_STORAGE

    data class MusicReq(
        val query: String, val station: String, val generic: Boolean,
        val app: String = "", val focus: String = "any", val preferApp: Boolean = true
    )

    private fun playMusic(r: MusicReq, askedAlready: Boolean = false) {
        val query = r.query
        fun result(source: String, count: Int = 0, app: String = "") = emit(
            "music_result",
            JSONObject().put("source", source).put("count", count).put("query", query)
                .put("station", r.station).put("app", app).toString()
        )
        if (r.station.isNotBlank()) {                     // género o ambiente -> radio
            music.playRadio(r.station)
            return result("radio")
        }
        // «pon X en Spotify» o, con «buscar en Spotify primero», cualquier artista/canción
        if (!r.generic && (r.app.isNotBlank() || (r.preferApp && musicApp(r.app) != null))) return openExternal(r, ::result)
        val canRead = checkSelfPermission(audioPermission()) == PackageManager.PERMISSION_GRANTED
        if (!canRead && !askedAlready) {                  // primero pedir permiso para la música del teléfono
            pendingMusic = r
            if (!permsInFlight) {
                permsInFlight = true
                requestPermissions(arrayOf(audioPermission()), REQ_AUDIO_FILES)
            }
            return
        }
        val n = if (canRead) music.playLocal(if (r.generic) "" else query) else 0
        if (n > 0) return result("local", n)
        if (r.generic) {                                   // no hay música guardada -> radio relajante
            music.playRadio("groovesalad")
            return result("radio_fallback")
        }
        openExternal(r, ::result)
    }

    private fun installed(pkg: String) = try {
        packageManager.getLaunchIntentForPackage(pkg) != null
    } catch (_: Exception) {
        false
    }

    /** Qué app de música usar: la pedida, si no Spotify, si no YouTube Music. */
    private fun musicApp(wanted: String): Pair<String, String>? {
        val apps = listOf("spotify" to (SPOTIFY to "Spotify"), "youtube" to (YT_MUSIC to "YouTube Music"))
        apps.firstOrNull { it.first == wanted && installed(it.second.first) }?.let { return it.second }
        return apps.firstOrNull { installed(it.second.first) }?.second
    }

    private fun searchIntent(query: String, focus: String, pkg: String?) =
        Intent(MediaStore.INTENT_ACTION_MEDIA_PLAY_FROM_SEARCH)
            .putExtra(SearchManager.QUERY, query)
            .putExtra(MediaStore.EXTRA_MEDIA_FOCUS, if (focus == "artist") "vnd.android.cursor.item/artist" else "vnd.android.cursor.item/*")
            .apply {
                if (focus == "artist") putExtra(MediaStore.EXTRA_MEDIA_ARTIST, query)
                if (pkg != null) setPackage(pkg)
            }
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    /**
     * Abre Spotify / YouTube Music con la búsqueda. Spotify a veces solo muestra los resultados sin
     * dar play: a los 5 s revisa si ya suena algo y avisa al JS (music_check) para que Luma lo diga.
     * Con la app minimizada Android no deja abrir otra app: manda una notificación para tocarla.
     */
    private fun openExternal(r: MusicReq, result: (String, Int, String) -> Unit) {
        val app = musicApp(r.app)
        val intent = when {
            app != null -> searchIntent(r.query, r.focus, app.first)
            else -> searchIntent(r.query, r.focus, null).takeIf { it.resolveActivity(packageManager) != null }
        }
        val name = app?.second ?: "tu app de música"
        if (intent == null) return result(if (r.app.isNotBlank()) "app_missing" else "none", 0, r.app)
        if (!resumed) {
            notifier.showIntent("Toca para poner «${r.query}»", "Se abrirá en $name.", intent)
            return result("tap_notification", 0, name)
        }
        val wasPlaying = audioManager().isMusicActive
        var opened = try { startActivity(intent); true } catch (_: Exception) { false }
        if (!opened && app?.first == SPOTIFY) {             // respaldo: abrir la búsqueda de Spotify
            opened = try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("spotify:search:" + Uri.encode(r.query)))
                    .setPackage(SPOTIFY).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); true
            } catch (_: Exception) { false }
        }
        if (!opened) return result("open_failed", 0, name)
        music.markExternal(r.query)
        result("external", 0, name)
        ui.postDelayed({
            val playing = audioManager().isMusicActive
            emit("music_check", JSONObject().put("app", name).put("playing", playing).put("wasPlaying", wasPlaying).toString())
        }, 5000)
    }

    private fun audioManager() = getSystemService(AUDIO_SERVICE) as AudioManager

    // Con «Seguir en segundo plano» el micrófono no se pausa al minimizar (el servicio lo mantiene vivo)
    override fun onPause() {
        super.onPause()
        resumed = false
        if (bgMode && BioService.running) return
        voice.pause("bg")
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        voice.resume("bg")
    }

    override fun onDestroy() {
        music.release()
        BioService.onExit = null
        BioService.stop(this)
        watch.disconnect(silent = true)
        alerts.stop()
        finder.stop()
        speaker.shutdown()
        voice.stop()
        web.destroy()
        super.onDestroy()
    }

    companion object {
        const val HOST = "appassets.androidplatform.net"
        private val BG = Color.rgb(7, 10, 31)
        private const val REQ_CAMERA = 11
        private const val REQ_BLE = 12
        private const val REQ_STARTUP = 13
        private const val REQ_MIC = 14
        private const val REQ_AUDIO_FILES = 15
        private const val SPOTIFY = "com.spotify.music"
        private const val YT_MUSIC = "com.google.android.apps.youtube.music"

        fun status(state: String, msg: String, name: String? = null): String =
            JSONObject().put("state", state).put("msg", msg).apply { if (name != null) put("name", name) }.toString()
    }
}
