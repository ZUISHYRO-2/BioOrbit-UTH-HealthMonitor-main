package org.bioorbit.watchbridge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.content.Context
import android.content.Intent
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.ParcelUuid
import android.os.SystemClock
import java.util.UUID
import java.util.concurrent.CopyOnWriteArraySet

class HeartRateBleService : Service(), SensorEventListener {
    private val mainHandler = Handler(Looper.getMainLooper())
    private var sensorManager: SensorManager? = null
    private var heartRateSensor: Sensor? = null
    private var gattServer: BluetoothGattServer? = null
    private var heartRateCharacteristic: BluetoothGattCharacteristic? = null
    private var latestBpm = 0
    private var lastSensorEventMs = 0L
    private val connectedDevices = CopyOnWriteArraySet<BluetoothDevice>()
    private val subscribedDevices = CopyOnWriteArraySet<BluetoothDevice>()

    private val publisher = object : Runnable {
        override fun run() {
            if (latestBpm > 0 && SystemClock.elapsedRealtime() - lastSensorEventMs <= SENSOR_STALE_MS) {
                publishHeartRate(latestBpm)
            }
            mainHandler.postDelayed(this, 1000)
        }
    }

    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIFICATION_ID, buildNotification())
        startHeartRateSensor()
        startGattServer()
        mainHandler.post(publisher)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int =
        START_STICKY

    private fun buildNotification(): Notification {
        return buildNotification("Iniciando sensor cardíaco y servicio BLE")
    }

    private fun startHeartRateSensor() {
        val manager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        sensorManager = manager
        val sensor = manager.getDefaultSensor(Sensor.TYPE_HEART_RATE)
        if (sensor == null) {
            updateNotification("Sensor cardíaco no disponible")
            return
        }
        heartRateSensor = sensor
        manager.registerListener(this, sensor, SensorManager.SENSOR_DELAY_NORMAL)
    }

    private fun startGattServer() {
        val bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val adapter = bluetoothManager.adapter
        if (adapter == null || !adapter.isEnabled) {
            updateNotification("Activa Bluetooth en el reloj")
            return
        }
        val advertiser = adapter.bluetoothLeAdvertiser
        if (advertiser == null) {
            updateNotification("El reloj no permite anunciar BLE")
            return
        }

        val service = BluetoothGattService(HEART_RATE_SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY)
        val characteristic = BluetoothGattCharacteristic(
            HEART_RATE_MEASUREMENT,
            BluetoothGattCharacteristic.PROPERTY_NOTIFY,
            BluetoothGattCharacteristic.PERMISSION_READ
        ).apply {
            addDescriptor(
                BluetoothGattDescriptor(
                    CLIENT_CONFIGURATION,
                    BluetoothGattDescriptor.PERMISSION_READ or BluetoothGattDescriptor.PERMISSION_WRITE
                )
            )
        }
        heartRateCharacteristic = characteristic
        service.addCharacteristic(characteristic)
        gattServer = bluetoothManager.openGattServer(this, gattCallback)
        if (gattServer == null || gattServer?.addService(service) != true) {
            updateNotification("No se pudo iniciar el servicio BLE cardíaco")
            return
        }
        advertiser.startAdvertising(
            AdvertiseSettings.Builder()
                .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
                .setConnectable(true)
                .setTimeout(0)
                .build(),
            AdvertiseData.Builder()
                .addServiceUuid(ParcelUuid(HEART_RATE_SERVICE))
                .build(),
            AdvertiseData.Builder()
                .setIncludeDeviceName(true)
                .build(),
            advertiseCallback
        )
    }

    private val advertiseCallback = object : AdvertiseCallback() {
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings) {
            updateNotification("Servicio BLE cardíaco anunciado")
        }

        override fun onStartFailure(errorCode: Int) {
            updateNotification("Falló el anuncio BLE: $errorCode")
        }
    }

    private val gattCallback = object : BluetoothGattServerCallback() {
        override fun onConnectionStateChange(device: BluetoothDevice, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                connectedDevices.add(device)
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                connectedDevices.remove(device)
                subscribedDevices.remove(device)
            }
        }

        override fun onDescriptorWriteRequest(
            device: BluetoothDevice,
            requestId: Int,
            descriptor: BluetoothGattDescriptor,
            preparedWrite: Boolean,
            responseNeeded: Boolean,
            offset: Int,
            value: ByteArray
        ) {
            if (descriptor.uuid == CLIENT_CONFIGURATION && offset == 0) {
                val enabled = value.contentEquals(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                if (enabled) subscribedDevices.add(device) else subscribedDevices.remove(device)
                descriptor.value = value
                if (responseNeeded) {
                    gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, 0, value)
                }
            } else if (responseNeeded) {
                gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED, 0, null)
            }
        }
    }

    private fun publishHeartRate(bpm: Int) {
        val characteristic = heartRateCharacteristic ?: return
        val value = if (bpm <= 255) {
            byteArrayOf(0, bpm.toByte())
        } else {
            byteArrayOf(1, (bpm and 0xff).toByte(), ((bpm shr 8) and 0xff).toByte())
        }
        characteristic.value = value
        subscribedDevices.toList().forEach { device ->
            gattServer?.notifyCharacteristicChanged(device, characteristic, false)
        }
    }

    private fun updateNotification(message: String) {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification(message))
    }

    private fun buildNotification(message: String): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Puente de sensores BioOrbit", NotificationManager.IMPORTANCE_LOW)
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("BioOrbit Watch Bridge")
            .setContentText(message)
            .setSmallIcon(android.R.drawable.ic_lock_idle_low_battery)
            .setOngoing(true)
            .build()
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type == Sensor.TYPE_HEART_RATE && event.values.isNotEmpty()) {
            latestBpm = event.values[0].toInt().coerceIn(1, 255)
            lastSensorEventMs = SystemClock.elapsedRealtime()
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    override fun onDestroy() {
        mainHandler.removeCallbacks(publisher)
        sensorManager?.unregisterListener(this)
        try {
            (getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager)
                .adapter?.bluetoothLeAdvertiser?.stopAdvertising(advertiseCallback)
        } catch (_: SecurityException) {
            // Permissions can be revoked while the service is running.
        }
        try {
            connectedDevices.forEach { device ->
                gattServer?.cancelConnection(device)
            }
            gattServer?.close()
        } catch (_: SecurityException) {
            // Permissions can be revoked while the service is running.
        }
        connectedDevices.clear()
        subscribedDevices.clear()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        private const val CHANNEL_ID = "bioorbit_watch_bridge"
        private const val NOTIFICATION_ID = 24
        private const val SENSOR_STALE_MS = 5000L
        private val HEART_RATE_SERVICE = UUID.fromString("0000180d-0000-1000-8000-00805f9b34fb")
        private val HEART_RATE_MEASUREMENT = UUID.fromString("00002a37-0000-1000-8000-00805f9b34fb")
        private val CLIENT_CONFIGURATION = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
    }
}
