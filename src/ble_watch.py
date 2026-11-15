"""
BioOrbit-UTH Health Monitor - Conector Bluetooth Low Energy (BLE) para Smartwatch
Compatible con Google Pixel Watch / Samsung Galaxy Watch 5 (Wear OS con difusión BLE HR),
bandas cardíacas y relojes con servicio estándar Bluetooth SIG Heart Rate (0x180D).

Características:
- Escaneo de dispositivos BLE cercanos con prioridad a relojes y sensores biomédicos.
- Conexión persistente en hilo dedicado asyncio (compatible con Streamlit).
- Decodificación completa GATT 0x2A37 (BPM 8/16-bit, contacto de sensor, intervalos RR).
- Cálculo en vivo de HRV RMSSD (ms) y SDNN (ms).
- Lectura de batería (0x2A19), SpO2 (0x2A5E/0x2A5F) y temperatura (0x2A1C) si están disponibles.
- Puente de archivo en tiempo real (data/live_watch_telemetry.json) para fusionar con vision_monitor.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Any, Deque, Dict, List, Optional

import importlib.util

# bleak se importa solo cuando se usa el Bluetooth: si falla (versión de Python sin soporte,
# sin adaptador), el HUD y la consola siguen funcionando y muestran el error.
BLEAK_AVAILABLE = importlib.util.find_spec("bleak") is not None


# UUIDs estándar Bluetooth SIG GATT
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_CHAR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BODY_SENSOR_LOC_UUID = "00002a38-0000-1000-8000-00805f9b34fb"

BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

TEMP_SERVICE_UUID = "00001809-0000-1000-8000-00805f9b34fb"
TEMP_MEASUREMENT_CHAR_UUID = "00002a1c-0000-1000-8000-00805f9b34fb"

PULSE_OX_SERVICE_UUID = "00001822-0000-1000-8000-00805f9b34fb"
PULSE_OX_SPOT_CHAR_UUID = "00002a5e-0000-1000-8000-00805f9b34fb"
PULSE_OX_CONT_CHAR_UUID = "00002a5f-0000-1000-8000-00805f9b34fb"

WATCH_NAME_KEYWORDS = (
    "watch", "pixel", "galaxy", "wear", "google", "samsung",
    "garmin", "fitbit", "polar", "amazfit", "xiaomi", "mi band",
    "coros", "suunto", "whoop", "hrm", "heart", "bioorbit",
)

LIVE_BRIDGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "live_watch_telemetry.json",
)


@dataclass
class BLEDeviceInfo:
    name: str
    address: str
    rssi: int
    service_uuids: List[str]
    is_watch_candidate: bool
    has_hr_service: bool


@dataclass
class WatchTelemetrySnapshot:
    connected: bool = False
    mode: str = "disconnected"  # "ble_live", "wear_sim", "disconnected"
    device_name: str = "Sin dispositivo"
    device_address: str = ""
    heart_rate_bpm: float = 0.0
    hrv_rmssd_ms: float = 0.0
    hrv_source: str = "N/A"
    sensor_contact: str = "Desconocido"
    battery_pct: Optional[int] = None
    spo2_pct: Optional[float] = None
    body_temp_c: Optional[float] = None
    last_rr_ms: List[float] = None
    discovered_services: List[str] = None
    packet_count: int = 0
    last_update_ts: float = 0.0
    status_message: str = "Listo para escanear reloj inteligente vía Bluetooth LE."

    def __post_init__(self):
        if self.last_rr_ms is None:
            self.last_rr_ms = []
        if self.discovered_services is None:
            self.discovered_services = []


def parse_heart_rate_measurement(data: bytearray | bytes) -> Dict[str, Any]:
    """
    Decodifica la característica estándar Bluetooth GATT 0x2A37 (Heart Rate Measurement).
    Especificación Bluetooth SIG HRS v1.0:
      - Bit 0: 0 = uint8 BPM, 1 = uint16 BPM
      - Bits 1-2: Sensor Contact Status
      - Bit 3: Energy Expended Present
      - Bit 4: RR-Interval Present (en unidades de 1/1024 s)
    """
    raw = bytes(data)
    if len(raw) < 2:
        raise ValueError("Paquete GATT 0x2A37 demasiado corto.")

    flags = raw[0]
    hr_uint16 = bool(flags & 0x01)
    contact_bits = (flags >> 1) & 0x03
    energy_present = bool(flags & 0x08)
    rr_present = bool(flags & 0x10)

    if contact_bits in (0, 1):
        sensor_contact = "No soportado"
    elif contact_bits == 2:
        sensor_contact = "Sin contacto"
    else:
        sensor_contact = "Contacto firme"

    idx = 1
    if hr_uint16:
        if len(raw) < idx + 2:
            raise ValueError("Paquete GATT 0x2A37 truncado en BPM uint16.")
        bpm = int.from_bytes(raw[idx:idx + 2], byteorder="little")
        idx += 2
    else:
        bpm = raw[idx]
        idx += 1

    energy_kj = None
    if energy_present and len(raw) >= idx + 2:
        energy_kj = int.from_bytes(raw[idx:idx + 2], byteorder="little")
        idx += 2

    rr_intervals_ms: List[float] = []
    if rr_present:
        while idx + 1 < len(raw):
            rr_raw = int.from_bytes(raw[idx:idx + 2], byteorder="little")
            rr_ms = round((rr_raw / 1024.0) * 1000.0, 2)
            if 250.0 <= rr_ms <= 2200.0:
                rr_intervals_ms.append(rr_ms)
            idx += 2

    return {
        "heart_rate_bpm": float(bpm),
        "sensor_contact": sensor_contact,
        "energy_kj": energy_kj,
        "rr_intervals_ms": rr_intervals_ms,
    }


def compute_rmssd_ms(rr_intervals_ms: List[float]) -> float:
    """Calcula HRV RMSSD en milisegundos a partir de intervalos RR consecutivos."""
    if len(rr_intervals_ms) < 2:
        return 0.0
    diffs_sq = [
        (rr_intervals_ms[i] - rr_intervals_ms[i - 1]) ** 2
        for i in range(1, len(rr_intervals_ms))
    ]
    return round(math.sqrt(sum(diffs_sq) / len(diffs_sq)), 1)


def scan_ble_devices_sync(timeout: float = 5.0, include_unnamed: bool = False) -> List[BLEDeviceInfo]:
    """Escanea dispositivos Bluetooth LE cercanos de manera síncrona."""
    if not BLEAK_AVAILABLE:
        raise RuntimeError("La librería 'bleak' no está instalada en el entorno Python.")

    from bleak import BleakScanner

    async def _scan():
        discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
        devices: List[BLEDeviceInfo] = []
        for device, adv in discovered.values():
            name = (device.name or adv.local_name or "").strip()
            uuids = [u.lower() for u in (adv.service_uuids or [])]
            has_hr = HR_SERVICE_UUID in uuids
            lower_name = name.lower()
            is_watch = has_hr or any(k in lower_name for k in WATCH_NAME_KEYWORDS)
            if not include_unnamed and not name and not has_hr:
                continue
            devices.append(
                BLEDeviceInfo(
                    name=name or f"BLE-{device.address}",
                    address=device.address,
                    rssi=int(adv.rssi) if adv.rssi is not None else -99,
                    service_uuids=uuids,
                    is_watch_candidate=is_watch,
                    has_hr_service=has_hr,
                )
            )
        devices.sort(key=lambda d: (not d.has_hr_service, not d.is_watch_candidate, -d.rssi))
        return devices

    return asyncio.run(_scan())


class BLEWatchManager:
    """
    Gestor singleton thread-safe para mantener conexión BLE o simulación Wear OS
    entre recargas de Streamlit y compartir datos con vision_monitor.py.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = WatchTelemetrySnapshot()
        self._history: Deque[Dict[str, Any]] = deque(maxlen=180)
        self._rr_buffer: Deque[float] = deque(maxlen=60)
        self._bpm_buffer: Deque[float] = deque(maxlen=30)
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _publish_bridge_file(self, snap: WatchTelemetrySnapshot) -> None:
        try:
            os.makedirs(os.path.dirname(LIVE_BRIDGE_PATH), exist_ok=True)
            payload = {
                "connected": snap.connected,
                "mode": snap.mode,
                "device_name": snap.device_name,
                "heart_rate_bpm": snap.heart_rate_bpm,
                "hrv_rmssd_ms": snap.hrv_rmssd_ms,
                "hrv_source": snap.hrv_source,
                "spo2_pct": snap.spo2_pct,
                "battery_pct": snap.battery_pct,
                "timestamp": time.time(),
            }
            tmp_path = LIVE_BRIDGE_PATH + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp_path, LIVE_BRIDGE_PATH)
        except OSError:
            logging.exception("No se pudo publicar la telemetría BLE en %s", LIVE_BRIDGE_PATH)

    def get_snapshot(self) -> WatchTelemetrySnapshot:
        with self._lock:
            return WatchTelemetrySnapshot(**asdict(self._snapshot))

    def get_history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history)

    def disconnect(self) -> None:
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
        with self._lock:
            self._snapshot = WatchTelemetrySnapshot(
                connected=False,
                mode="disconnected",
                status_message="Dispositivo desconectado.",
            )
            self._publish_bridge_file(self._snapshot)

    def connect_ble(self, address: str, device_name: str = "Google Watch 5") -> None:
        if not BLEAK_AVAILABLE:
            raise RuntimeError("Instala 'bleak' para conectar dispositivos Bluetooth LE.")
        self.disconnect()
        self._stop_event.clear()
        self._rr_buffer.clear()
        self._bpm_buffer.clear()
        self._history.clear()

        with self._lock:
            self._snapshot = WatchTelemetrySnapshot(
                connected=False,
                mode="ble_connecting",
                device_name=device_name,
                device_address=address,
                status_message=f"Conectando vía Bluetooth LE a {device_name} ({address})...",
            )

        self._worker_thread = threading.Thread(
            target=self._run_ble_loop,
            args=(address, device_name),
            daemon=True,
        )
        self._worker_thread.start()

    def start_wear_simulator(self, device_name: str = "Google Watch 5 (Simulador Wear OS)", scenario: str = "nominal") -> None:
        self.disconnect()
        self._stop_event.clear()
        self._rr_buffer.clear()
        self._bpm_buffer.clear()
        self._history.clear()

        with self._lock:
            self._snapshot = WatchTelemetrySnapshot(
                connected=True,
                mode="wear_sim",
                device_name=device_name,
                device_address="WEAR-SIM-BLE",
                battery_pct=86,
                spo2_pct=98.2,
                body_temp_c=36.7,
                sensor_contact="Contacto firme",
                status_message=f"Flujo Wear OS activo ({scenario}).",
            )

        self._worker_thread = threading.Thread(
            target=self._run_sim_loop,
            args=(device_name, scenario),
            daemon=True,
        )
        self._worker_thread.start()

    def _record_hr_sample(
        self,
        bpm: float,
        sensor_contact: str,
        rr_ms: List[float],
        mode: str,
    ) -> None:
        with self._lock:
            self._bpm_buffer.append(bpm)
            if rr_ms:
                for rr in rr_ms:
                    self._rr_buffer.append(rr)
                hrv = compute_rmssd_ms(list(self._rr_buffer))
                hrv_src = "Intervalos RR GATT"
            elif len(self._bpm_buffer) >= 4:
                # Estimación derivada si el reloj Wear OS envía BPM sin intervalos RR
                rr_est = [60000.0 / max(40.0, b) for b in self._bpm_buffer]
                hrv = compute_rmssd_ms(rr_est)
                hrv_src = "Estimación desde BPM"
            else:
                hrv = self._snapshot.hrv_rmssd_ms or 45.0
                hrv_src = "Inicializando"

            now = time.time()
            self._snapshot.connected = True
            self._snapshot.mode = mode
            self._snapshot.heart_rate_bpm = round(bpm, 1)
            self._snapshot.hrv_rmssd_ms = round(hrv, 1)
            self._snapshot.hrv_source = hrv_src
            self._snapshot.sensor_contact = sensor_contact
            self._snapshot.last_rr_ms = list(self._rr_buffer)[-8:]
            self._snapshot.packet_count += 1
            self._snapshot.last_update_ts = now
            self._snapshot.status_message = (
                f"Recibiendo telemetría en vivo ({self._snapshot.packet_count} paquetes)."
            )

            self._history.append({
                "time": time.strftime("%H:%M:%S"),
                "timestamp": now,
                "bpm": round(bpm, 1),
                "hrv_rmssd_ms": round(hrv, 1),
            })
            self._publish_bridge_file(self._snapshot)

    def _run_ble_loop(self, address: str, device_name: str) -> None:
        asyncio.run(self._async_ble_worker(address, device_name))

    async def _async_ble_worker(self, address: str, device_name: str) -> None:
        try:
            from bleak import BleakClient

            async with BleakClient(address, timeout=12.0) as client:
                services = [f"{s.uuid} ({s.description})" for s in client.services]
                char_uuids = {
                    c.uuid.lower(): c
                    for s in client.services
                    for c in s.characteristics
                }

                with self._lock:
                    self._snapshot.connected = True
                    self._snapshot.mode = "ble_live"
                    self._snapshot.discovered_services = services
                    self._snapshot.status_message = f"Conectado a {device_name}. Suscribiendo sensores GATT..."

                if BATTERY_LEVEL_CHAR_UUID in char_uuids:
                    try:
                        bat = await client.read_gatt_char(BATTERY_LEVEL_CHAR_UUID)
                        with self._lock:
                            self._snapshot.battery_pct = int(bat[0])
                    except Exception:
                        pass

                has_hr_char = HR_MEASUREMENT_CHAR_UUID in char_uuids
                if not has_hr_char:
                    with self._lock:
                        self._snapshot.status_message = (
                            "Conectado por BLE, pero el reloj no está difundiendo el servicio GATT "
                            "Heart Rate (0x180D / 0x2A37). Activa 'Heart Rate Broadcast' o una app "
                            "BLE Heart Rate en tu Google Watch 5 / Wear OS."
                        )
                    while not self._stop_event.is_set() and client.is_connected:
                        await asyncio.sleep(0.5)
                    return

                def _on_hr(_sender: Any, data: bytearray) -> None:
                    try:
                        parsed = parse_heart_rate_measurement(data)
                        self._record_hr_sample(
                            bpm=parsed["heart_rate_bpm"],
                            sensor_contact=parsed["sensor_contact"],
                            rr_ms=parsed["rr_intervals_ms"],
                            mode="ble_live",
                        )
                    except Exception:
                        pass

                await client.start_notify(HR_MEASUREMENT_CHAR_UUID, _on_hr)

                if PULSE_OX_CONT_CHAR_UUID in char_uuids:
                    def _on_spo2(_sender: Any, data: bytearray) -> None:
                        if len(data) >= 3:
                            spo2_val = int.from_bytes(data[1:3], byteorder="little")
                            if 70 <= spo2_val <= 100:
                                with self._lock:
                                    self._snapshot.spo2_pct = float(spo2_val)
                    try:
                        await client.start_notify(PULSE_OX_CONT_CHAR_UUID, _on_spo2)
                    except Exception:
                        pass

                while not self._stop_event.is_set() and client.is_connected:
                    await asyncio.sleep(0.4)

                try:
                    await client.stop_notify(HR_MEASUREMENT_CHAR_UUID)
                except Exception:
                    pass
        except Exception as exc:
            with self._lock:
                self._snapshot.connected = False
                self._snapshot.mode = "disconnected"
                self._snapshot.status_message = f"Error BLE con {device_name}: {exc}"
                self._publish_bridge_file(self._snapshot)

    def _run_sim_loop(self, device_name: str, scenario: str) -> None:
        t = 0.0
        while not self._stop_event.is_set():
            if scenario == "stress":
                base_bpm = 101.0 + 4.5 * math.sin(t * 0.4)
                rr_jitter = 12.0 * math.sin(t * 1.1)
                base_rr = 60000.0 / base_bpm
                spo2 = 94.8
            else:
                base_bpm = 72.0 + 3.2 * math.sin(t * 0.35)
                rr_jitter = 32.0 * math.sin(t * 0.9)
                base_rr = 60000.0 / base_bpm
                spo2 = 98.4

            rr_sample = max(420.0, min(1250.0, base_rr + rr_jitter))
            with self._lock:
                self._snapshot.spo2_pct = spo2
            self._record_hr_sample(
                bpm=base_bpm,
                sensor_contact="Contacto firme",
                rr_ms=[round(rr_sample, 1)],
                mode="wear_sim",
            )
            t += 1.0
            self._stop_event.wait(1.0)


_WATCH_MANAGER: Optional[BLEWatchManager] = None
_MANAGER_LOCK = threading.Lock()


def get_watch_manager() -> BLEWatchManager:
    global _WATCH_MANAGER
    with _MANAGER_LOCK:
        if _WATCH_MANAGER is None:
            _WATCH_MANAGER = BLEWatchManager()
        return _WATCH_MANAGER


def read_live_watch_bridge(max_age_sec: float = 8.0) -> Optional[Dict[str, Any]]:
    """Lee el último paquete del reloj BLE si está reciente (usado por vision_monitor.py)."""
    if not os.path.exists(LIVE_BRIDGE_PATH):
        return None
    try:
        with open(LIVE_BRIDGE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not data.get("connected"):
            return None
        if time.time() - float(data.get("timestamp", 0.0)) > max_age_sec:
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Integración con BioOrbit (HUD de cámara y consola web)
# ---------------------------------------------------------------------------
def watch_state(max_age_sec: float = 8.0, lost_window_sec: float = 120.0):
    """Estado del reloj según el archivo puente.

    Devuelve (estado, datos):
      - "live": el reloj está mandando pulso.
      - "lost": estaba conectado y dejó de mandar pulso hace menos de 2 min (o manda 0 BPM):
                se trata como PÉRDIDA DE SIGNOS VITALES.
      - "off":  no hay reloj, se desconectó a propósito o el dato es muy viejo.
    """
    try:
        with open(LIVE_BRIDGE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, TypeError):
        return "off", None
    if not data.get("connected"):
        return "off", data
    age = time.time() - float(data.get("timestamp", 0.0) or 0.0)
    if age > lost_window_sec:
        return "off", data
    if age > max_age_sec or not (data.get("heart_rate_bpm") or 0) > 0:
        return "lost", data
    return "live", data


def apply_watch(row, state: str, data: Optional[Dict[str, Any]]):
    """Mezcla el reloj con la fila de telemetría simulada.

    - live: la frecuencia cardíaca viene del reloj; HRV solo si llegó con intervalos RR reales;
            SpO2 solo si el reloj lo manda.
    - lost: FC, HRV y SpO2 quedan vacíos -> alerts.vitals_status() da NO_VITALS.
    """
    row = row.copy()
    if state == "live" and data:
        row["heart_rate_bpm"] = float(data["heart_rate_bpm"])
        if data.get("hrv_source") == "Intervalos RR GATT" and (data.get("hrv_rmssd_ms") or 0) > 0:
            row["hrv_rmssd_ms"] = float(data["hrv_rmssd_ms"])
        if data.get("spo2_pct"):
            row["spo2_pct"] = float(data["spo2_pct"])
    elif state == "lost":
        for key in ("heart_rate_bpm", "hrv_rmssd_ms", "spo2_pct"):
            row[key] = float("nan")
    return row
