package org.bioorbit.mobile

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

/** Notificaciones del sistema y vibración para las alertas de BioOrbit. */
class Notifier(private val ctx: Context) {

    private val nm = ctx.getSystemService(NotificationManager::class.java)
    private var nextId = 100

    init {
        nm.createNotificationChannel(
            NotificationChannel(CH_ALERT, "Alertas de signos vitales", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Pérdida de signos vitales y avisos de tripulantes cercanos"
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 600, 250, 600, 250, 600)
            }
        )
        nm.createNotificationChannel(
            NotificationChannel(CH_INFO, "Avisos de BioOrbit", NotificationManager.IMPORTANCE_DEFAULT)
        )
    }

    fun show(title: String, text: String, urgent: Boolean) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val open = PendingIntent.getActivity(
            ctx, 0,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val n = Notification.Builder(ctx, if (urgent) CH_ALERT else CH_INFO)
            .setSmallIcon(R.drawable.ic_stat_alert)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text))
            .setCategory(if (urgent) Notification.CATEGORY_ALARM else Notification.CATEGORY_STATUS)
            .setColor(0xFFFF4D6D.toInt())
            .setAutoCancel(true)
            .setContentIntent(open)
            .build()
        nm.notify(nextId++, n)
    }

    /** Aviso que al tocarlo abre otra app (por ejemplo Spotify con la búsqueda). */
    fun showIntent(title: String, text: String, target: Intent) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val pi = PendingIntent.getActivity(ctx, 7, target, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val nb = Notification.Builder(ctx, CH_INFO)
            .setSmallIcon(R.drawable.ic_stat_alert)
            .setContentTitle(title)
            .setContentText(text)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()
        nm.notify(77, nb)
    }

    fun vibrate(ms: Long) {
        val v: Vibrator? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ctx.getSystemService(VibratorManager::class.java)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
        if (v == null || !v.hasVibrator()) return
        v.vibrate(VibrationEffect.createOneShot(ms.coerceIn(20, 3000), VibrationEffect.DEFAULT_AMPLITUDE))
    }

    fun vibratePattern(pattern: LongArray) {
        val v = vibrator() ?: return
        v.vibrate(VibrationEffect.createWaveform(pattern, -1))
    }

    private fun vibrator(): Vibrator? {
        val v: Vibrator? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ctx.getSystemService(VibratorManager::class.java)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
        return if (v != null && v.hasVibrator()) v else null
    }

    companion object {
        private const val CH_ALERT = "bioorbit_alerts"
        private const val CH_INFO = "bioorbit_info"
    }
}
