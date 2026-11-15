package org.bioorbit.mobile

import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import kotlin.concurrent.thread

/**
 * IA de Luma: conversa con Gemini (Google) o con Claude (Anthropic), según la clave guardada.
 *   - Clave que empieza con "AQ." o "AIza"  -> Gemini (generativelanguage.googleapis.com)
 *   - Clave que empieza con "sk-ant-"       -> Claude (api.anthropic.com)
 *
 * La clave la escribe la persona una sola vez en la app y se guarda solo en este teléfono
 * (almacenamiento privado de la app). No va dentro del código ni del APK, y el JS no la vuelve a leer.
 * Sin clave o sin internet, la interfaz usa las respuestas básicas de Luma.
 * Se envía: los últimos mensajes del chat y un resumen de la telemetría.
 *
 * Eventos al JS: ai_reply {id, text} · ai_error {id, msg}
 */
class LumaAI(ctx: Context, private val emit: (String, String) -> Unit) {

    private val prefs = ctx.getSharedPreferences("bioorbit_ai", Context.MODE_PRIVATE)
    private val main = Handler(Looper.getMainLooper())

    private fun key(): String = prefs.getString(KEY, null).orEmpty()

    fun hasKey(): Boolean = key().isNotBlank()

    fun setKey(k: String) {
        prefs.edit().putString(KEY, k.trim()).remove(GEMINI_OK_MODEL).apply()
    }

    fun clearKey() {
        prefs.edit().remove(KEY).remove(GEMINI_OK_MODEL).apply()
    }

    private fun isClaude(k: String) = k.startsWith("sk-ant-")

    /** Nombre para mostrar en la app, p. ej. "Gemini · gemini-3.5-flash-lite". */
    fun label(): String {
        val k = key()
        if (k.isBlank()) return ""
        return if (isClaude(k)) "Claude · $CLAUDE_MODEL"
        else "Gemini · " + (prefs.getString(GEMINI_OK_MODEL, null) ?: GEMINI_MODELS.first())
    }

    /** messagesJson: [{"role":"user"|"assistant","content":"..."}], empieza con "user". */
    fun chat(id: String, system: String, messagesJson: String) {
        val k = key()
        if (k.isBlank()) return fail(id, "No hay clave de IA configurada.")
        thread(name = "luma-ai", isDaemon = true) {
            try {
                val msgs = JSONArray(messagesJson)
                val text = if (isClaude(k)) claude(k, system, msgs) else gemini(k, system, msgs)
                if (text.isBlank()) fail(id, "La IA no devolvió texto.")
                else main.post { emit("ai_reply", JSONObject().put("id", id).put("text", text.trim()).toString()) }
            } catch (e: AiException) {
                fail(id, e.message ?: "Error de la IA.")
            } catch (e: Exception) {
                fail(id, "Sin conexión con la IA (${e.javaClass.simpleName}). Uso respuestas básicas.")
            }
        }
    }

    // ------------------------------------------------------------------ Gemini
    private fun gemini(k: String, system: String, msgs: JSONArray): String {
        val contents = JSONArray()
        for (i in 0 until msgs.length()) {
            val m = msgs.optJSONObject(i) ?: continue
            val role = if (m.optString("role") == "assistant") "model" else "user"
            contents.put(JSONObject().put("role", role).put("parts", JSONArray().put(JSONObject().put("text", m.optString("content")))))
        }
        // Los modelos nuevos de Gemini no aceptan temperature/top_p: no se mandan.
        val body = JSONObject()
            .put("systemInstruction", JSONObject().put("parts", JSONArray().put(JSONObject().put("text", system))))
            .put("contents", contents)
            .toString()

        // Prueba primero el modelo que ya funcionó; si un modelo no existe para esta clave, usa el siguiente.
        val remembered = prefs.getString(GEMINI_OK_MODEL, null)
        val order = (listOfNotNull(remembered) + GEMINI_MODELS).distinct()
        var lastError = "La IA no respondió."
        for (model in order) {
            val (code, text) = post(
                "$geminiBase/v1beta/models/$model:generateContent",
                body, mapOf("x-goog-api-key" to k)   // clave AQ./AIza: en este encabezado, nunca como Bearer
            )
            if (code in 200..299) {
                if (remembered != model) prefs.edit().putString(GEMINI_OK_MODEL, model).apply()
                return geminiText(text)
            }
            val apiMsg = errorMessage(text)
            if (code == 404) {
                lastError = "Ningún modelo de Gemini está disponible para esta clave. $apiMsg"
                continue
            }
            lastError = when {
                code == 400 && apiMsg.contains("API key", true) -> "La clave de Gemini no es válida. Revísala en la pestaña Luma."
                code == 401 || code == 403 -> "Google rechazó la clave de Gemini ($code). Revisa que sea de Google AI Studio y que la API de Gemini esté activa. $apiMsg"
                code == 429 -> "Se acabó la cuota gratuita de Gemini por ahora. Intenta en un minuto."
                else -> "Gemini respondió con error $code. $apiMsg"
            }
            throw AiException(lastError.trim())
        }
        throw AiException(lastError.trim())
    }

    private fun geminiText(json: String): String {
        val root = JSONObject(json)
        val cand = root.optJSONArray("candidates")?.optJSONObject(0)
            ?: throw AiException("Gemini bloqueó la respuesta (${root.optJSONObject("promptFeedback")?.optString("blockReason") ?: "sin candidatos"}).")
        val parts = cand.optJSONObject("content")?.optJSONArray("parts")
        val out = StringBuilder()
        if (parts != null) {
            for (i in 0 until parts.length()) {
                val p = parts.optJSONObject(i) ?: continue
                if (p.optBoolean("thought")) continue          // se omite el razonamiento interno
                out.append(p.optString("text"))
            }
        }
        if (out.isBlank()) throw AiException("Gemini no devolvió texto (${cand.optString("finishReason")}).")
        return out.toString()
    }

    // ------------------------------------------------------------------ Claude
    private fun claude(k: String, system: String, msgs: JSONArray): String {
        val body = JSONObject()
            .put("model", CLAUDE_MODEL)
            .put("max_tokens", 300)
            .put("system", system)
            .put("messages", msgs)
            .toString()
        val (code, text) = post(
            "https://api.anthropic.com/v1/messages", body,
            mapOf("x-api-key" to k, "anthropic-version" to "2023-06-01")
        )
        if (code !in 200..299) {
            val apiMsg = errorMessage(text)
            throw AiException(
                when (code) {
                    401 -> "La clave de Claude no es válida. Revísala en la pestaña Luma."
                    402, 403 -> "La cuenta de Claude no tiene saldo o permiso. $apiMsg"
                    429 -> "La IA está saturada o se acabó el saldo. Intenta en un momento."
                    else -> "Claude respondió con error $code. $apiMsg"
                }.trim()
            )
        }
        val content = JSONObject(text).optJSONArray("content")
        val out = StringBuilder()
        if (content != null) {
            for (i in 0 until content.length()) {
                val part = content.optJSONObject(i) ?: continue
                if (part.optString("type") == "text") out.append(part.optString("text"))
            }
        }
        return out.toString()
    }

    // ------------------------------------------------------------------ HTTP
    private fun post(url: String, body: String, headers: Map<String, String>): Pair<Int, String> {
        val conn = URI(url).toURL().openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 10_000
            conn.readTimeout = 30_000
            conn.doOutput = true
            conn.setRequestProperty("content-type", "application/json")
            for ((h, v) in headers) conn.setRequestProperty(h, v)
            conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            return code to stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
        } finally {
            conn.disconnect()
        }
    }

    private fun errorMessage(text: String): String = try {
        JSONObject(text).optJSONObject("error")?.optString("message").orEmpty().take(160)
    } catch (_: Exception) {
        ""
    }

    private fun fail(id: String, msg: String) {
        main.post { emit("ai_error", JSONObject().put("id", id).put("msg", msg).toString()) }
    }

    private class AiException(msg: String) : Exception(msg)

    companion object {
        private const val KEY = "ai_api_key"
        private const val GEMINI_OK_MODEL = "gemini_ok_model"
        const val CLAUDE_MODEL = "claude-haiku-5-5"
        // Rápidos y económicos; si el primero no existe para la clave, se usa el siguiente.
        val GEMINI_MODELS = listOf("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash")
        @JvmStatic var geminiBase = "https://generativelanguage.googleapis.com"   // solo se cambia en pruebas
    }
}
