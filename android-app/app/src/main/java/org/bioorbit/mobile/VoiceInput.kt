package org.bioorbit.mobile

import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import org.json.JSONObject

/**
 * Luma te escucha: reconocimiento de voz de Android en español.
 *
 * Dos modos:
 *  - Una vez (botón de micrófono): escucha una frase y termina.
 *  - Continuo (escucha permanente): al terminar cada frase vuelve a escuchar sola.
 *    Se pausa mientras Luma habla ("tts") y cuando la app pasa a segundo plano ("bg").
 *
 * Si el teléfono tiene reconocimiento en el dispositivo (Android 13+ con el paquete de español),
 * se usa ese: no hace pitidos y funciona sin internet. Si no, se usa el de Google y se silencia
 * el pitido de cada reinicio (se baja el volumen multimedia mientras escucha; Luma lo devuelve
 * antes de hablar).
 *
 * Eventos al JS: listen_state {state: listening|processing|idle|paused}, listen_level {v} (~20/s),
 *   listen_partial {text}, listen_result {text}, listen_error {code,msg}, listen_mode {continuous,ondevice}
 * Todas las llamadas deben hacerse en el hilo principal.
 */
class VoiceInput(private val ctx: Context, private val emit: (String, String) -> Unit) {

    private val audio = ctx.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
    private val main = Handler(Looper.getMainLooper())
    private var rec: SpeechRecognizer? = null
    private val pauses = mutableSetOf<String>()
    private var lastLevel = 0L
    private var fails = 0
    private var lastNetErr = 0L
    private var muted = false
    private var onDevice = Build.VERSION.SDK_INT >= 33 && safeOnDeviceAvailable()
    private var onDeviceFails = 0
    private var lastPartial = ""     // lo último que fue entendiendo en esta frase
    private var sessions = 0

    /** Fuerza el reconocimiento en línea de Google (por si el del teléfono no funciona bien). */
    fun forceOnline(on: Boolean) {
        onDevice = !on && Build.VERSION.SDK_INT >= 33 && safeOnDeviceAvailable()
        onDeviceFails = 0
        emitMode()
        if (continuous && pauses.isEmpty()) schedule(100)
    }

    var continuous = false
        private set

    /** Se puede silenciar el volumen multimedia (pitidos)? No mientras suena música. */
    var muteAllowed: () -> Boolean = { true }

    fun forceUnmute() = unmute()

    val available: Boolean get() = SpeechRecognizer.isRecognitionAvailable(ctx) || onDevice

    private fun safeOnDeviceAvailable(): Boolean = try {
        SpeechRecognizer.isOnDeviceRecognitionAvailable(ctx)
    } catch (_: Throwable) {
        false
    }

    // ------------------------------------------------------------------ control
    fun setContinuous(on: Boolean) {
        continuous = on
        fails = 0
        emitMode()
        if (on) {
            if (pauses.isEmpty()) startSession() else state("paused")
        } else {
            main.removeCallbacks(restart)
            destroyRec()
            unmute()
            state("idle")
        }
    }

    /** Una sola frase (botón de micrófono). En modo continuo no hace falta: ya está escuchando. */
    fun startOnce() {
        if (continuous) return
        pauses.remove("tts")
        startSession()
    }

    fun pause(reason: String) {
        pauses.add(reason)
        main.removeCallbacks(restart)
        destroyRec()
        unmute()
        if (continuous) state("paused") else state("idle")
    }

    fun resume(reason: String) {
        pauses.remove(reason)
        if (continuous && pauses.isEmpty()) schedule(350)
    }

    fun stop() {
        continuous = false
        pauses.clear()
        main.removeCallbacks(restart)
        destroyRec()
        unmute()
    }

    // ------------------------------------------------------------------ sesión
    private val restart = Runnable { if (continuous && pauses.isEmpty()) startSession() }

    private fun schedule(ms: Long) {
        main.removeCallbacks(restart)
        main.postDelayed(restart, ms)
    }

    private fun startSession() {
        if (pauses.isNotEmpty()) return
        if (!available) {
            error(-1, "Este teléfono no tiene reconocimiento de voz. Instala o activa la app de Google.")
            continuous = false
            emitMode()
            return
        }
        destroyRec()
        val r = try {
            if (onDevice && Build.VERSION.SDK_INT >= 33) SpeechRecognizer.createOnDeviceSpeechRecognizer(ctx)
            else SpeechRecognizer.createSpeechRecognizer(ctx)
        } catch (e: Exception) {
            onDevice = false
            SpeechRecognizer.createSpeechRecognizer(ctx)
        }
        rec = r
        sessions++
        lastPartial = ""
        r.setRecognitionListener(listener)
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-MX")
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "es-MX")
            .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        if (onDevice) intent.putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
        if (continuous && !onDevice) mute()      // el reconocedor de Google pita en cada reinicio
        try {
            r.startListening(intent)
        } catch (e: Exception) {
            destroyRec()
            if (continuous) schedule(1500) else error(-2, "No pude abrir el micrófono: ${e.message}")
        }
    }

    private fun destroyRec() {
        rec?.let {
            try {
                it.cancel()
                it.destroy()
            } catch (_: Exception) {
            }
        }
        rec = null
    }

    // ------------------------------------------------------------------ pitidos
    private fun mute() {
        if (muted || !muteAllowed()) return
        try {
            audio?.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_MUTE, 0)
            muted = true
        } catch (_: Exception) {
        }
    }

    private fun unmute() {
        if (!muted) return
        try {
            audio?.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_UNMUTE, 0)
        } catch (_: Exception) {
        }
        muted = false
    }

    // ------------------------------------------------------------------ eventos
    private fun state(s: String) = emit("listen_state", JSONObject().put("state", s).toString())

    private fun debug(ev: String, code: Int = 0) = emit(
        "listen_debug", JSONObject().put("ev", ev).put("code", code).put("ondevice", onDevice).put("sessions", sessions).toString()
    )

    private fun emitMode() = emit(
        "listen_mode", JSONObject().put("continuous", continuous).put("ondevice", onDevice).toString()
    )

    private fun error(code: Int, msg: String) {
        emit("listen_error", JSONObject().put("code", code).put("msg", msg).toString())
        if (!continuous) state("idle")
    }

    private fun firstText(b: Bundle?): String =
        b?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) = state("listening")
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {
            val now = SystemClock.elapsedRealtime()
            if (now - lastLevel < 50) return
            lastLevel = now
            val v = ((rmsdB + 2f) / 12f).coerceIn(0f, 1f)
            emit("listen_level", JSONObject().put("v", v.toDouble()).toString())
        }
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() = state("processing")

        override fun onError(error: Int) {
            destroyRec()
            // Muchos teléfonos (p. ej. Samsung) terminan con "error 7: no entendí" aunque ya fueron
            // entendiendo la frase. Si hubo texto parcial, se usa como la frase completa.
            val partial = lastPartial.trim()
            lastPartial = ""
            if (partial.isNotEmpty() && error != SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS) {
                debug("partial_as_result", error)
                deliver(partial)
                return
            }
            debug("error", error)
            // si el reconocimiento del teléfono falla seguido (no por silencio), se cambia al de Google
            if (onDevice && error != SpeechRecognizer.ERROR_NO_MATCH && error != SpeechRecognizer.ERROR_SPEECH_TIMEOUT) {
                if (++onDeviceFails >= 2) {
                    onDevice = false
                    emitMode()
                }
            }
            if (continuous) {
                when (error) {
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> {
                        fails = 0
                        schedule(80)
                    }
                    ERROR_LANGUAGE_NOT_SUPPORTED, ERROR_LANGUAGE_UNAVAILABLE -> {
                        // el reconocimiento en el teléfono no tiene español: se usa el de Google
                        onDevice = false
                        emitMode()
                        schedule(100)
                    }
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> {
                        continuous = false
                        emitMode()
                        unmute()
                        error(error, "Falta el permiso del micrófono.")
                        state("idle")
                    }
                    SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> {
                        val now = SystemClock.elapsedRealtime()
                        if (now - lastNetErr > 30_000) {
                            lastNetErr = now
                            error(error, "Sin internet para reconocer la voz. Descarga el español sin conexión en los ajustes de voz de Google.")
                        }
                        schedule(3000)
                    }
                    else -> {
                        fails++
                        schedule(if (fails > 5) 4000 else 400)
                    }
                }
                return
            }
            unmute()
            val msg = when (error) {
                SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "No te escuché. Toca el micrófono y habla de nuevo."
                SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Sin internet para reconocer tu voz. Descarga el español sin conexión en los ajustes de voz de Google."
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Falta el permiso del micrófono."
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "El micrófono está ocupado. Intenta otra vez."
                SpeechRecognizer.ERROR_AUDIO -> "Error de audio del micrófono."
                ERROR_LANGUAGE_NOT_SUPPORTED, ERROR_LANGUAGE_UNAVAILABLE -> {
                    onDevice = false
                    "El español sin conexión no está instalado; uso el reconocimiento en línea. Intenta otra vez."
                }
                else -> "No pude reconocer la voz (código $error)."
            }
            error(error, msg)
        }

        override fun onResults(results: Bundle?) {
            val text = firstText(results).ifBlank { lastPartial }.trim()
            lastPartial = ""
            destroyRec()
            debug(if (text.isBlank()) "empty" else "result")
            deliver(text)
        }

        override fun onPartialResults(partialResults: Bundle?) {
            val text = firstText(partialResults)
            if (text.isNotEmpty()) {
                lastPartial = text
                emit("listen_partial", JSONObject().put("text", text).toString())
            }
        }

        override fun onEvent(eventType: Int, params: Bundle?) {}
    }

    /** Entrega una frase al JS y, en modo continuo, vuelve a escuchar. */
    private fun deliver(text: String) {
        fails = 0
        onDeviceFails = 0
        if (text.isNotBlank()) emit("listen_result", JSONObject().put("text", text).toString())
        if (continuous) schedule(120)
        else {
            unmute()
            state("idle")
        }
    }

    companion object {
        private const val ERROR_LANGUAGE_NOT_SUPPORTED = 12
        private const val ERROR_LANGUAGE_UNAVAILABLE = 13
    }
}
