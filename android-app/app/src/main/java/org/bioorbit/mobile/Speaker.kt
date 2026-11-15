package org.bioorbit.mobile

import android.content.Context
import android.media.AudioAttributes
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import org.json.JSONObject
import java.util.Locale

/**
 * Voz de Luma con el motor de texto a voz del teléfono (Google TTS u otro instalado).
 * El WebView no trae voz propia, por eso se hace en Kotlin.
 * Los avisos urgentes salen por el canal de alarma para que se escuchen aunque el volumen
 * multimedia esté bajo.
 */
class Speaker(ctx: Context, private val emit: (String, String) -> Unit) {

    private var ready = false
    private var pending: Pair<String, Boolean>? = null
    private var n = 0
    private val tts: TextToSpeech = TextToSpeech(ctx.applicationContext) { status ->
        if (status == TextToSpeech.SUCCESS) {
            ready = true
            pickSpanish()
            listenProgress()
            pending?.let { (text, urgent) -> speak(text, urgent) }
            pending = null
        }
    }

    // avisa al JS cuando Luma termina de hablar (para escuchar justo después, sin captar su propia voz)
    private fun listenProgress() {
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {
                emit("speak_state", JSONObject().put("speaking", true).toString())
            }
            override fun onDone(utteranceId: String?) {
                emit("speak_state", JSONObject().put("speaking", false).put("done", true).toString())
            }
            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                emit("speak_state", JSONObject().put("speaking", false).toString())
            }
            override fun onStop(utteranceId: String?, interrupted: Boolean) {
                emit("speak_state", JSONObject().put("speaking", false).toString())
            }
        })
    }

    private fun pickSpanish() {
        for (loc in listOf("es-MX", "es-US", "es-ES", "es").map(Locale::forLanguageTag)) {
            val r = tts.setLanguage(loc)
            if (r != TextToSpeech.LANG_MISSING_DATA && r != TextToSpeech.LANG_NOT_SUPPORTED) return
        }
    }

    fun speak(text: String, urgent: Boolean) {
        if (!ready) {
            pending = text to urgent
            return
        }
        tts.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(if (urgent) AudioAttributes.USAGE_ALARM else AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
        )
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "luma-${n++}")
    }

    fun stop() {
        if (ready) tts.stop()
        pending = null
    }

    fun shutdown() {
        try {
            tts.stop()
            tts.shutdown()
        } catch (_: Exception) {
        }
    }
}
