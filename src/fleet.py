"""
BioOrbit-UTH - Registro de dispositivos (centro de control).

Cada dispositivo (reloj, HUD de cámara de otra laptop, app móvil...) manda un
"reporte" con su astronauta y sus lecturas. El centro de control los junta para
mostrar a toda la tripulación a la vez.

Cómo llegan los reportes:
  - Misma laptop: el reloj BLE y el HUD de cámara ya escriben archivos; aquí se leen.
  - Otras laptops / teléfonos: POST http://<ip-de-la-consola>:8766/report
    (lo recibe src/fleet_server.py y lo guarda en data/fleet/<device_id>.json).

Seguridad: si defines BIOORBIT_FLEET_TOKEN, el servidor exige ese token en el
encabezado X-BioOrbit-Token. Nunca pongas el token dentro del código.

PROTOTIPO: no es un dispositivo médico certificado.
"""

import json
import math
import os
import re
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PORT = 8766
FLEET_DIR = Path(os.getenv("BIOORBIT_FLEET_DIR") or Path(__file__).resolve().parent.parent / "data" / "fleet")

ONLINE_S = 10.0    # dato más nuevo que esto = en línea
STALE_S = 45.0     # entre ONLINE_S y STALE_S = retrasado; más = sin señal
LOST_S = 120.0     # un dispositivo con pulso que callo hace menos de esto = pérdida de signos

KINDS = {
    "watch": ("⌚", "Reloj"),
    "camera": ("📷", "Cámara HUD"),
    "phone": ("📱", "App móvil"),
    "sim": ("🧪", "Simulado"),
    "other": ("🔌", "Otro"),
}
# Solo estos tipos pueden reemplazar los signos vitales simulados. La cámara (rPPG) es
# experimental: se muestra, pero no dispara alertas.
VITAL_KINDS = ("watch", "phone", "other")
NUM_FIELDS = ("heart_rate_bpm", "hrv_rmssd_ms", "spo2_pct", "body_temp_c", "battery_pct", "quality")
MAX_BYTES = 4096

_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,48}$")
_TEXT_RE = re.compile(r"[^\w .,:()·\-áéíóúüñÁÉÍÓÚÜÑ]")


class FleetError(ValueError):
    """Reporte inválido (se responde 400 en el servidor)."""


def _clean_text(v: Any, limit: int = 40) -> str:
    return _TEXT_RE.sub("", str(v or ""))[:limit].strip()


def _num(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def build_report(payload: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    """Valida y limpia un reporte. Lanza FleetError si no sirve."""
    if not isinstance(payload, dict):
        raise FleetError("el reporte debe ser un objeto JSON")
    device_id = str(payload.get("device_id", ""))
    if not _ID_RE.match(device_id):
        raise FleetError("device_id inválido (letras, números, . _ - ; máx. 48)")
    crew = str(payload.get("crew", ""))
    if not _ID_RE.match(crew):
        raise FleetError("crew inválido")
    kind = str(payload.get("kind", "other"))
    if kind not in KINDS or kind == "sim":
        kind = "other"
    rep: Dict[str, Any] = {
        "device_id": device_id,
        "crew": crew,
        "kind": kind,
        "name": _clean_text(payload.get("name")) or device_id,
        "ts": now if now is not None else time.time(),
    }
    for k in NUM_FIELDS:
        x = _num(payload.get(k))
        if x is not None:
            rep[k] = x
    if "face_locked" in payload:
        rep["face_locked"] = bool(payload["face_locked"])
    # HRV "real" solo si el dispositivo asegura que viene de intervalos RR medidos
    rep["hrv_real"] = bool(payload.get("hrv_real", False))
    return rep


def report(payload: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    """Guarda el reporte de un dispositivo (escritura atómica)."""
    rep = build_report(payload, now)
    FLEET_DIR.mkdir(parents=True, exist_ok=True)
    path = FLEET_DIR / f"{rep['device_id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return rep


def state_of(age: float) -> str:
    return "online" if age <= ONLINE_S else "stale" if age <= STALE_S else "offline"


def read_all(now: Optional[float] = None, max_age: float = 86400.0) -> List[Dict[str, Any]]:
    """Dispositivos registrados en disco, con su edad y estado."""
    now = now if now is not None else time.time()
    out = []
    for p in sorted(FLEET_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            d["age"] = max(0.0, now - float(d["ts"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if d["age"] > max_age or d.get("kind") not in KINDS:
            continue
        d["state"] = state_of(d["age"])
        d["local"] = False
        out.append(d)
    return out


def local_devices(watch_crew: Optional[str], now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Reloj BLE y HUD de cámara que corren en ESTA laptop (usan archivos puente)."""
    now = now if now is not None else time.time()
    out: List[Dict[str, Any]] = []
    try:
        import ble_watch
        wstate, wdata = ble_watch.watch_state()
        if wstate != "off" and wdata and watch_crew:
            age = max(0.0, now - float(wdata.get("timestamp", now)))
            out.append({
                "device_id": "reloj-local", "crew": watch_crew, "kind": "watch",
                "name": _clean_text(wdata.get("device_name")) or "Reloj local",
                "ts": now - age, "age": age, "state": state_of(age), "local": True,
                "heart_rate_bpm": wdata.get("heart_rate_bpm"),
                "hrv_rmssd_ms": wdata.get("hrv_rmssd_ms"), "spo2_pct": wdata.get("spo2_pct"),
                "battery_pct": wdata.get("battery_pct"),
                "hrv_real": wdata.get("hrv_source") == "Intervalos RR GATT",
            })
    except Exception:  # noqa: BLE001  (sin bleak o sin archivo: no pasa nada)
        pass
    try:
        import companion
        cam = companion.read_vision_status(max_age=60.0)
        if cam:
            age = max(0.0, now - float(cam.get("ts", now)))
            out.append({
                "device_id": "hud-local", "crew": cam.get("crew"), "kind": "camera",
                "name": "HUD de cámara", "ts": now - age, "age": age, "state": state_of(age),
                "local": True, "heart_rate_bpm": cam.get("bpm"),
                "face_locked": bool(cam.get("face_locked")), "quality": cam.get("quality"),
            })
    except Exception:  # noqa: BLE001
        pass
    return out


def snapshot(watch_crew: Optional[str], now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Todos los dispositivos (remotos + locales), sin duplicar el HUD local."""
    now = now if now is not None else time.time()
    local = local_devices(watch_crew, now)
    remote = [d for d in read_all(now) if d["device_id"] not in {x["device_id"] for x in local}]
    try:                                # teléfonos que reportan al servidor de tripulación (crew_server)
        import crew_link
        phones = crew_link.get_link().devices()
    except Exception:  # noqa: BLE001
        phones = []
    return remote + local + phones


def vitals_state(crew: str, devices: List[Dict[str, Any]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Igual que ble_watch.watch_state() pero para dispositivos reportados.
      live: llega pulso reciente        -> reemplaza la FC simulada
      lost: tenía pulso y se calló (<2 min) o manda 0 -> pérdida de signos vitales
      off:  nada que decir
    Devuelve (estado, datos) con las claves que espera ble_watch.apply_watch().
    """
    best: Optional[Dict[str, Any]] = None
    for d in devices:
        if d.get("crew") != crew or d.get("kind") not in VITAL_KINDS or d.get("heart_rate_bpm") is None:
            continue
        if d.get("vital") is False:     # p. ej. un teléfono cuyo pulso viene de la cámara (experimental)
            continue
        if best is None or d["age"] < best["age"]:
            best = d
    if best is None or best["age"] > LOST_S:
        return "off", None
    data = {
        "device_name": best.get("name"),
        "heart_rate_bpm": best.get("heart_rate_bpm") or 0.0,
        "hrv_rmssd_ms": best.get("hrv_rmssd_ms") or 0.0,
        "hrv_source": "Intervalos RR GATT" if best.get("hrv_real") else "",
        "spo2_pct": best.get("spo2_pct"),
        "battery_pct": best.get("battery_pct"),
        "timestamp": best["ts"],
    }
    if best["age"] > ONLINE_S or not data["heart_rate_bpm"] > 0:
        return "lost", data
    return "live", data


# ---------------------------------------------------------------- envío a otra consola
_push_lock = threading.Lock()
_push_busy = False


def push(url: str, payload: Dict[str, Any], token: Optional[str] = None, timeout: float = 1.5) -> None:
    """Manda un reporte a una consola remota sin bloquear (descarta si el envío anterior sigue en curso)."""
    global _push_busy
    with _push_lock:
        if _push_busy:
            return
        _push_busy = True

    def run():
        global _push_busy
        try:
            req = urllib.request.Request(url.rstrip("/") + "/report",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            if token:
                req.add_header("X-BioOrbit-Token", token)
            urllib.request.urlopen(req, timeout=timeout).close()
        except Exception:  # noqa: BLE001  (sin red: se reintenta en el siguiente reporte)
            pass
        finally:
            with _push_lock:
                _push_busy = False

    threading.Thread(target=run, daemon=True).start()


def push_from_env(payload: Dict[str, Any]) -> None:
    """Si defines BIOORBIT_FLEET_URL (p. ej. http://192.168.1.20:8766), manda el reporte ahí."""
    url = os.getenv("BIOORBIT_FLEET_URL")
    if url:
        push(url, payload, os.getenv("BIOORBIT_FLEET_TOKEN"))


def lan_ip() -> str:
    """IP de esta laptop en la red local (para decirle al teléfono a dónde mandar)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
