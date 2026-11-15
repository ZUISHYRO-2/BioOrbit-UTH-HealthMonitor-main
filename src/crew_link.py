"""
BioOrbit-UTH - Enlace del centro de control con el servidor de tripulación (crew_server/).

El servidor de tripulación (crew_server/server.py) guarda las cuentas de los astronautas y recibe el
estado de cada teléfono (pulso, cámara, reloj, alertas). Este módulo entra a él como la cuenta «control»
cada 2 s, en segundo plano, y convierte lo que ve en "dispositivos" para la pestaña Centro de control.

Configuración (todo opcional si el servidor corre en esta misma laptop):
    BIOORBIT_CREW_URL           dirección del servidor, por defecto http://127.0.0.1:8765
    BIOORBIT_CONTROL_PASSWORD   contraseña de «control»; si no existe, se lee de
                                crew_server/data/control_password.txt (la crea el servidor la primera vez)

Nunca pongas la contraseña dentro del código ni la subas a GitHub.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import fleet

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "http://127.0.0.1:8765"
PASS_FILE = ROOT / "crew_server" / "data" / "control_password.txt"
POLL_S = 2.0
TIMEOUT_S = 2.0


def read_password() -> Optional[str]:
    pw = os.getenv("BIOORBIT_CONTROL_PASSWORD")
    if pw:
        return pw
    try:
        txt = PASS_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^Contrase[ñn]a:\s*(\S+)", txt, re.M)
    return m.group(1) if m else None


def _num(v: Any) -> Optional[float]:
    return fleet._num(v) if not isinstance(v, bool) else None


def to_devices(resp: Dict[str, Any], crew_ids: Iterable[str]) -> List[Dict[str, Any]]:
    """Convierte la respuesta de /api/sync en dispositivos (un teléfono por cuenta que ya sincronizó)."""
    crew_ids = set(crew_ids)
    now_srv = float(resp.get("now") or time.time())
    local_now = time.time()
    out = []
    for c in resp.get("crew", []):
        last = c.get("last_seen")
        if last is None:
            continue                      # cuenta creada, pero su teléfono nunca se ha conectado
        st = c.get("status") or {}
        age = max(0.0, now_srv - float(last))
        callsign = str(c.get("callsign") or "").upper()
        username = str(c.get("username") or "").upper()
        crew = callsign if callsign in crew_ids else (username if username in crew_ids else None)
        watch, cam = bool(st.get("watch")), bool(st.get("cam"))
        parts = []
        if watch:
            parts.append("Reloj conectado")
        parts.append(("En cámara ✓" if st.get("present") else "No aparece en cámara") if cam else "Cámara apagada")
        if st.get("bg"):
            parts.append("App minimizada")
        if st.get("mood"):
            parts.append("Luma: " + fleet._clean_text(st.get("mood"), 20))
        out.append({
            "device_id": "tel-" + fleet._clean_text(c.get("username"), 32).replace(" ", "-"),
            "crew": crew, "kind": "phone", "source": "crew_server",
            "name": fleet._clean_text(c.get("name"), 30) or "Teléfono",
            "ts": local_now - age, "age": age, "state": fleet.state_of(age), "local": False,
            "heart_rate_bpm": _num(st.get("hr")), "spo2_pct": _num(st.get("spo2")),
            "body_temp_c": _num(st.get("temp")),
            "face_locked": bool(st.get("present")) if cam else None,
            "hr_src": fleet._clean_text(st.get("hr_src"), 20),
            # Solo un reloj conectado cuenta como pulso real; el pulso por cámara es experimental.
            "vital": watch,
            "alert": fleet._clean_text(st.get("alert"), 30),
            "detail": " · ".join(parts),
            "hrv_real": False,
        })
    return out


class _AuthError(Exception):
    pass


class CrewLink:
    def __init__(self, url: Optional[str] = None) -> None:
        self.url = (url or os.getenv("BIOORBIT_CREW_URL") or DEFAULT_URL).rstrip("/")
        self._lock = threading.Lock()
        self._devices: List[Dict[str, Any]] = []
        self._alerts: List[Dict[str, Any]] = []
        self._state, self._msg = "starting", "Conectando con el servidor de tripulación…"
        self._token: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ---------------------------------------------------------------- consulta (la usa la consola)
    def status(self) -> Tuple[str, str]:
        with self._lock:
            return self._state, self._msg

    def devices(self) -> List[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            out = [dict(d) for d in self._devices]
        for d in out:                     # la edad sigue corriendo entre consultas
            d["age"] = max(0.0, now - d["ts"])
            d["state"] = fleet.state_of(d["age"])
        return out

    def open_alerts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(a) for a in self._alerts if a.get("resolved") is None]

    # ---------------------------------------------------------------- acciones
    def resolve(self, alert_id: int) -> bool:
        """El control de misión marca una alerta como resuelta."""
        try:
            self._post("/api/alert_ack", {"id": int(alert_id), "resolve": True, "text": "Resuelta por control"},
                       self._token)
            return True
        except (urllib.error.URLError, OSError, ValueError):
            return False

    # ---------------------------------------------------------------- red
    def _post(self, path: str, body: Dict[str, Any], token: Optional[str] = None) -> Dict[str, Any]:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
        if token:
            req.add_header("Authorization", "Bearer " + token)
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8"))

    def _login(self) -> None:
        pw = read_password()
        if not pw:
            raise _AuthError("No encuentro la contraseña de «control». Arranca crew_server/server.py una vez "
                             "o define BIOORBIT_CONTROL_PASSWORD.")
        try:
            self._token = self._post("/api/login", {"username": "control", "password": pw})["token"]
        except urllib.error.HTTPError as e:
            if e.code in (401, 429):
                raise _AuthError("El servidor rechazó la contraseña de «control».") from e
            raise

    def poll_once(self, crew_ids: Iterable[str]) -> None:
        try:
            if not self._token:
                self._login()
            try:
                resp = self._post("/api/sync", {}, self._token)
            except urllib.error.HTTPError as e:
                if e.code != 401:
                    raise
                self._token = None            # sesión vencida: se vuelve a entrar una vez
                self._login()
                resp = self._post("/api/sync", {}, self._token)
            devices = to_devices(resp, crew_ids)
            with self._lock:
                self._devices, self._alerts = devices, list(resp.get("alerts", []))
                self._state = "ok"
                self._msg = f"Servidor de tripulación conectado · {len(devices)} teléfono(s) han reportado"
        except _AuthError as e:
            self._fail("auth", str(e))
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            self._fail("down", f"No encuentro el servidor de tripulación en {self.url}. "
                               "¿Está corriendo crew_server/server.py?")

    def _fail(self, state: str, msg: str) -> None:
        self._token = None
        with self._lock:
            self._devices, self._alerts, self._state, self._msg = [], [], state, msg

    def _run(self) -> None:
        import alerts  # aquí para no cargar pandas al importar este módulo en las pruebas
        crew_ids = list(alerts.ROSTER)
        while not self._stop.is_set():
            self.poll_once(crew_ids)
            self._stop.wait(POLL_S)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="crew-link")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


_LINK: Optional[CrewLink] = None
_LINK_LOCK = threading.Lock()


def get_link() -> CrewLink:
    """Un solo enlace por proceso: sobrevive a las recargas de Streamlit."""
    global _LINK
    with _LINK_LOCK:
        if _LINK is None:
            _LINK = CrewLink()
        return _LINK
