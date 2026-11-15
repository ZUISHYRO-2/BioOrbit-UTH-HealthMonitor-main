package org.bioorbit.mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder

/**
 * Servicio en primer plano: mantiene a BioOrbit funcionando en segundo plano con una notificación
 * fija. Gracias a él Android deja que el micrófono (escucha permanente) y la música sigan con la app
 * minimizada o la pantalla apagada. Lo inicia y lo detiene MainActivity.
 */
class BioService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_EXIT) {
            onExit?.invoke()
            stopSelf()
            return START_NOT_STICKY
        }
        val n = build(this, text)
        try {
            if (Build.VERSION.SDK_INT >= 30) {
                val mic = checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
                val type = ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK or
                    (if (mic) ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE else 0)
                startForeground(ID, n, type)
            } else if (Build.VERSION.SDK_INT >= 29) {
                startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
            } else {
                startForeground(ID, n)
            }
        } catch (e: Exception) {
            // p. ej. Android 14 no deja iniciarlo desde segundo plano: se intenta solo como reproductor
            try {
                if (Build.VERSION.SDK_INT >= 29) startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
            } catch (_: Exception) {
                stopSelf()
            }
        }
        running = true
        return START_NOT_STICKY
    }

    // si cierras la app desde recientes, todo se detiene
    override fun onTaskRemoved(rootIntent: Intent?) {
        onExit?.invoke()
        stopSelf()
    }

    override fun onDestroy() {
        running = false
        super.onDestroy()
    }

    companion object {
        private const val ID = 7
        private const val CHANNEL = "bioorbit_service"
        private const val ACTION_EXIT = "org.bioorbit.mobile.EXIT"
        @Volatile var running = false
            private set
        private var text = "Luma te escucha"
        /** MainActivity lo usa para cerrar todo cuando tocas «Salir» en la notificación. */
        var onExit: (() -> Unit)? = null

        fun start(ctx: Context) {
            val i = Intent(ctx, BioService::class.java)
            try {
                if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
            } catch (_: Exception) {
            }
        }

        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, BioService::class.java))
            running = false
        }

        /** Cambia el texto de la notificación (p. ej. la canción que suena). */
        fun update(ctx: Context, newText: String) {
            text = newText
            if (!running) return
            ctx.getSystemService(NotificationManager::class.java)?.notify(ID, build(ctx, newText))
        }

        private fun build(ctx: Context, body: String): Notification {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            nm?.createNotificationChannel(
                NotificationChannel(CHANNEL, "BioOrbit en segundo plano", NotificationManager.IMPORTANCE_LOW).apply {
                    description = "Mantiene a Luma escuchando y la música sonando con la app minimizada"
                    setShowBadge(false)
                }
            )
            val open = PendingIntent.getActivity(
                ctx, 1, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            val exit = PendingIntent.getService(
                ctx, 2, Intent(ctx, BioService::class.java).setAction(ACTION_EXIT),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            return Notification.Builder(ctx, CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_alert)
                .setContentTitle("BioOrbit · Luma")
                .setContentText(body)
                .setOngoing(true)
                .setContentIntent(open)
                .addAction(Notification.Action.Builder(null, "Salir", exit).build())
                .build()
        }
    }
}
