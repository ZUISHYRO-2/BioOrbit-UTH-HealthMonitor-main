package org.bioorbit.mobile

import android.content.ContentUris
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.net.Uri
import android.os.PowerManager
import android.os.SystemClock
import android.provider.MediaStore
import android.view.KeyEvent
import org.json.JSONObject
import java.text.Normalizer

/**
 * Música por voz para Luma. Tres fuentes:
 *  1. Música guardada en el teléfono (MediaStore): busca por canción, artista o álbum.
 *  2. Radio por internet (SomaFM, sin comerciales) para géneros y ambientes.
 *  3. Otra app de música (Spotify, YouTube Music…): la abre MainActivity y aquí se controla
 *     con las teclas multimedia del sistema (pausa, siguiente).
 * Sigue sonando con la app en segundo plano (BioService la mantiene viva).
 *
 * Eventos al JS: music_state {active, playing, mode, title, station, event, query}
 */
class MusicPlayer(private val ctx: Context, private val emit: (String, String) -> Unit) {

    data class Track(val uri: Uri, val title: String, val artist: String, val album: String)
    data class Station(val id: String, val name: String, val desc: String)

    private val audio = ctx.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
    private var player: MediaPlayer? = null
    private var queue: List<Track> = emptyList()
    private var index = 0
    private var station: Station? = null
    private var urlTry = 0
    private var ducked = false

    var mode = "none"            // none | local | radio | external
        private set
    var playing = false
        private set
    var title = ""
        private set

    /** Hay música (sonando o en pausa) que controlar. */
    fun isActive() = mode != "none"

    // ------------------------------------------------------------------ teléfono
    /** Busca en la música del teléfono. Devuelve cuántas canciones encontró (0 = nada). */
    fun playLocal(query: String): Int {
        val all = scan()
        if (all.isEmpty()) return 0
        val words = norm(query).split(" ").filter { it.length > 1 && it !in STOP }
        val found = if (words.isEmpty()) all.shuffled() else {
            val scored = all.map { t ->
                val hay = norm("${t.title} ${t.artist} ${t.album}")
                t to words.count { hay.contains(it) }
            }
            val best = scored.maxOf { it.second }
            if (best == 0) return 0
            scored.filter { it.second == best }.map { it.first }.shuffled()
        }
        stopInternal()
        queue = found
        index = 0
        mode = "local"
        startTrack()
        return found.size
    }

    private fun scan(): List<Track> {
        val out = mutableListOf<Track>()
        val cols = arrayOf(
            MediaStore.Audio.Media._ID, MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST, MediaStore.Audio.Media.ALBUM
        )
        try {
            ctx.contentResolver.query(
                MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, cols,
                "${MediaStore.Audio.Media.IS_MUSIC} != 0", null, null
            )?.use { c ->
                while (c.moveToNext()) {
                    val id = c.getLong(0)
                    out.add(
                        Track(
                            ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, id),
                            c.getString(1).orEmpty(), c.getString(2).orEmpty().replace("<unknown>", ""), c.getString(3).orEmpty()
                        )
                    )
                }
            }
        } catch (_: SecurityException) {
        } catch (_: Exception) {
        }
        return out
    }

    private fun startTrack() {
        val t = queue.getOrNull(index) ?: return stop()
        title = if (t.artist.isNotBlank()) "${t.title} · ${t.artist}" else t.title
        prepare(t.uri.toString(), isUri = true)
    }

    // ------------------------------------------------------------------ radio
    fun playRadio(id: String) {
        val st = STATIONS.firstOrNull { it.id == id } ?: STATIONS.first()
        stopInternal()
        station = st
        mode = "radio"
        title = "Radio ${st.name}"
        urlTry = 0
        prepare(radioUrl(st, 0), isUri = false)
    }

    // https primero; si falla, el otro servidor por http (permitido solo para somafm.com)
    private fun radioUrl(st: Station, n: Int) = when (n) {
        0 -> "https://ice1.somafm.com/${st.id}-128-mp3"
        1 -> "http://ice2.somafm.com/${st.id}-128-mp3"
        else -> "http://ice1.somafm.com/${st.id}-128-aac"
    }

    // ------------------------------------------------------------------ otra app
    /** MainActivity abrió Spotify/YouTube Music: desde aquí se controla con teclas multimedia. */
    fun markExternal(query: String) {
        stopInternal()
        mode = "external"
        playing = true
        title = query
        state("external")
    }

    private fun mediaKey(code: Int) {
        val a = audio ?: return
        val t = SystemClock.uptimeMillis()
        a.dispatchMediaKeyEvent(KeyEvent(t, t, KeyEvent.ACTION_DOWN, code, 0))
        a.dispatchMediaKeyEvent(KeyEvent(t, t, KeyEvent.ACTION_UP, code, 0))
    }

    // ------------------------------------------------------------------ reproducción
    private fun prepare(src: String, isUri: Boolean) {
        val mp = MediaPlayer()
        player = mp
        try {
            mp.setAudioAttributes(
                AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build()
            )
            mp.setWakeMode(ctx, PowerManager.PARTIAL_WAKE_LOCK)
            if (isUri) mp.setDataSource(ctx, Uri.parse(src)) else mp.setDataSource(src)
            mp.setOnPreparedListener {
                if (player !== it) return@setOnPreparedListener
                applyVolume()
                it.start()
                playing = true
                state("started")
            }
            mp.setOnCompletionListener {
                if (player !== it) return@setOnCompletionListener
                if (mode == "local") next() else if (mode == "radio") station?.let { s -> playRadio(s.id) }
            }
            mp.setOnErrorListener { it, _, _ ->
                if (player === it) onPlayError()
                true
            }
            mp.prepareAsync()
            playing = false
            state("loading")
        } catch (e: Exception) {
            onPlayError()
        }
    }

    private var failedMode = ""

    private fun onPlayError() {
        releasePlayer()
        failedMode = mode
        when (mode) {
            "radio" -> {
                val st = station
                if (st != null && ++urlTry <= 2) prepare(radioUrl(st, urlTry), isUri = false)
                else { mode = "none"; playing = false; state("error") }
            }
            "local" -> if (index + 1 < queue.size) next() else { mode = "none"; playing = false; state("error") }
            else -> { mode = "none"; playing = false; state("error") }
        }
    }

    // ------------------------------------------------------------------ controles
    fun pause() {
        when (mode) {
            "external" -> mediaKey(KeyEvent.KEYCODE_MEDIA_PAUSE)
            else -> try { player?.pause() } catch (_: Exception) { }
        }
        playing = false
        state("paused")
    }

    fun resume() {
        when (mode) {
            "external" -> mediaKey(KeyEvent.KEYCODE_MEDIA_PLAY)
            "none" -> return
            else -> try { player?.start() } catch (_: Exception) { }
        }
        playing = true
        state("resumed")
    }

    fun next() {
        when (mode) {
            "external" -> { mediaKey(KeyEvent.KEYCODE_MEDIA_NEXT); state("next") }
            "local" -> {
                releasePlayer()
                index = (index + 1) % queue.size.coerceAtLeast(1)
                startTrack()
            }
            "radio" -> {   // en la radio, «siguiente» cambia de estación
                val i = STATIONS.indexOfFirst { it.id == station?.id }
                playRadio(STATIONS[(i + 1) % STATIONS.size].id)
            }
        }
    }

    fun stop() {
        if (mode == "external") mediaKey(KeyEvent.KEYCODE_MEDIA_PAUSE)
        stopInternal()
        state("stopped")
    }

    fun volume(up: Boolean) {
        audio?.adjustStreamVolume(
            AudioManager.STREAM_MUSIC,
            if (up) AudioManager.ADJUST_RAISE else AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI
        )
        state("volume")
    }

    /** Baja la música mientras Luma habla o te escucha. */
    fun duck(on: Boolean) {
        ducked = on
        applyVolume()
    }

    private fun applyVolume() {
        val v = if (ducked) 0.2f else 1f
        try { player?.setVolume(v, v) } catch (_: Exception) { }
    }

    private fun stopInternal() {
        releasePlayer()
        queue = emptyList()
        station = null
        mode = "none"
        playing = false
        title = ""
    }

    private fun releasePlayer() {
        player?.let {
            try {
                it.stop()
            } catch (_: Exception) {
            }
            it.release()
        }
        player = null
    }

    fun release() = stopInternal()

    private fun state(event: String) {
        if (event != "error") failedMode = ""
        emit(
            "music_state", JSONObject()
                .put("event", event).put("active", isActive()).put("playing", playing)
                .put("mode", mode).put("title", title)
                .put("station", station?.id ?: "").put("failed", failedMode).toString()
        )
        onChange?.invoke(this)
    }

    /** Aviso para actualizar la notificación del servicio. */
    var onChange: ((MusicPlayer) -> Unit)? = null

    companion object {
        // Estaciones de SomaFM (radio por internet sin comerciales, sostenida por sus oyentes)
        val STATIONS = listOf(
            Station("groovesalad", "Groove Salad", "música relajante"),
            Station("dronezone", "Drone Zone", "ambiente tranquilo para dormir o meditar"),
            Station("deepspaceone", "Deep Space One", "música espacial"),
            Station("missioncontrol", "Mission Control", "música espacial con audios de la NASA"),
            Station("spacestation", "Space Station Soma", "electrónica espacial"),
            Station("indiepop", "Indie Pop Rocks", "pop e indie"),
            Station("poptron", "PopTron", "electropop para bailar"),
            Station("bagel", "BAGeL Radio", "rock alternativo"),
            Station("u80s", "Underground 80s", "música de los ochenta"),
            Station("seventies", "Left Coast 70s", "música de los setenta"),
            Station("sonicuniverse", "Sonic Universe", "jazz"),
            Station("folkfwd", "Folk Forward", "folk y acústica"),
            Station("secretagent", "Secret Agent", "música de misterio"),
            Station("dubstep", "Dub Step Beyond", "dubstep"),
        )

        private val STOP = setOf(
            "de", "la", "el", "los", "las", "un", "una", "a", "y", "con", "mi", "por", "favor",
            "musica", "cancion", "canciones", "algo", "poco", "rola", "rolas", "disco", "album", "playlist"
        )

        fun norm(s: String): String =
            Normalizer.normalize(s.lowercase(), Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "")
                .replace(Regex("[^a-z0-9ñ ]"), " ").replace(Regex("\\s+"), " ").trim()
    }
}
