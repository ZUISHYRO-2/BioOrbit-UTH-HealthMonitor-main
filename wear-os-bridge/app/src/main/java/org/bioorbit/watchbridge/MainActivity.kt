package org.bioorbit.watchbridge

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class MainActivity : Activity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(28, 36, 28, 36)
        }
        status = TextView(this).apply {
            text = "Transmite tu frecuencia cardíaca al monitor BioOrbit por Bluetooth LE."
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, 12)
        }
        val startButton = Button(this).apply {
            text = "Iniciar transmisión"
            setOnClickListener { requestBridgePermissions() }
        }
        val stopButton = Button(this).apply {
            text = "Detener conexión"
            setOnClickListener {
                stopBridge()
                status.text = "Conexión detenida."
            }
        }
        val exitButton = Button(this).apply {
            text = "Salir"
            setOnClickListener {
                stopBridge()
                finishAndRemoveTask()
            }
        }
        layout.addView(status)
        layout.addView(startButton)
        layout.addView(stopButton)
        layout.addView(exitButton)

        val scrollView = ScrollView(this).apply {
            isFillViewport = true
            addView(layout)
        }
        setContentView(scrollView)
    }

    private fun requestBridgePermissions() {
        val permissions = buildList {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                add(Manifest.permission.BLUETOOTH_ADVERTISE)
                add(Manifest.permission.BLUETOOTH_CONNECT)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                add(Manifest.permission.BODY_SENSORS)
            }
            if (Build.VERSION.SDK_INT >= 33) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        val missing = permissions.filter {
            checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            requestPermissions(missing.toTypedArray(), REQUEST_PERMISSIONS)
        } else {
            startBridge()
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        val requiredPermissionsGranted = permissions.indices.all { index ->
            permissions[index] == Manifest.permission.POST_NOTIFICATIONS ||
                grantResults.getOrNull(index) == PackageManager.PERMISSION_GRANTED
        }
        if (requestCode == REQUEST_PERMISSIONS && requiredPermissionsGranted) {
            startBridge()
        } else {
            status.text = "Acepta los permisos de sensor y Bluetooth para iniciar."
        }
    }

    private fun startBridge() {
        val intent = Intent(this, HeartRateBleService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        status.text = "Puente activo. Mantén la app abierta y escanea desde la PC."
    }

    private fun stopBridge() {
        stopService(Intent(this, HeartRateBleService::class.java))
    }

    companion object {
        private const val REQUEST_PERMISSIONS = 100
    }
}
