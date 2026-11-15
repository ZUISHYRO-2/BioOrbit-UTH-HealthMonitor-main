"""
BioOrbit-UTH - Enlace del centro de control con el servidor de tripulación (crew_server/).

El servidor de tripulación (crew_server/server.py) guarda las cuentas de los astronautas y recibe el
estado de cada teléfono (pulso, cámara, reloj, alertas). Este módulo entra a él como la cuenta «control»
cada 2 s, en segundo plano, y convierte lo que ve en "dispositivos" para la pestaña Centro de control.

El enlace va en los dos sentidos:
  teléfonos -> consola: estado de cada teléfono, alertas, chat de la tripulación
  consola -> teléfonos: mensajes del control de misión (a todos o privados), alertas que detecta la
                        consola (pérdida de signos, apoyo humano) y «enterado» / «resuelta» en las alertas

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
MAX_MSGS = 300


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
        self._wake = threading.Event()
        self._msgs: List[Dict[str, Any]] = []
        self._since = 0
        self._accounts: List[Dict[str, Any]] = []
        self._public = ""
        self._sent_alerts: Dict[str, int] = {}
        self._server_id = ""     # alertas que mandó la consola, por astronauta

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

    def messages(self) -> List[Dict[str, Any]]:
        """Chat de la tripulación (el control ve también los privados), del más viejo al más nuevo."""
        with self._lock:
            return [dict(m) for m in self._msgs]

    def accounts(self) -> List[Dict[str, Any]]:
        """Astronautas con cuenta: username, name, callsign, online."""
        with self._lock:
            return [dict(a) for a in self._accounts]

    def public_url(self) -> str:
        with self._lock:
            return self._public

    # ---------------------------------------------------------------- acciones
    def resolve(self, alert_id: int) -> bool:
        """El control de misión marca una alerta como resuelta."""
        return self.ack(alert_id, "Resuelta por control", resolve=True)

    def ack(self, alert_id: int, text: str = "Control enterado", resolve: bool = False) -> bool:
        """«Enterado»: los teléfonos ven que el control ya vio la alerta."""
        try:
            self._post("/api/alert_ack", {"id": int(alert_id), "resolve": bool(resolve), "text": text},
                       self._auth_token())
            self.poll_soon()
            return True
        except (urllib.error.URLError, OSError, ValueError, KeyError, _AuthError):
            return False

    def send_chat(self, text: str, to: str = "") -> Tuple[bool, str]:
        """Mensaje del control de misión: a toda la tripulación (to="") o privado a un usuario."""
        text = (text or "").strip()
        if not text:
            return False, "Mensaje vacío."
        try:
            r = self._post("/api/chat", {"text": text[:1000], "to": to or ""}, self._auth_token())
            m = r.get("message")
            if m:
                with self._lock:
                    if not any(x["id"] == m["id"] for x in self._msgs):
                        self._msgs.append(m)
                    self._since = max(self._since, int(m["id"]))
            return True, ""
        except urllib.error.HTTPError as e:
            return False, _http_error(e)
        except _AuthError as e:
            return False, str(e)
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return False, f"No hay conexión con el servidor de tripulación ({self.url})."

    def send_alert(self, kind: str, message: str, key: Optional[str] = None) -> None:
        """Manda a los teléfonos una alerta que detectó la consola (sin bloquear la pantalla).

        key (el astronauta) sirve para cerrarla después con resolve_key() cuando vuelvan las señales."""
        def work():
            try:
                r = self._post("/api/alert", {"kind": kind, "message": message[:300]}, self._auth_token())
                if key and r.get("id"):
                    with self._lock:
                        self._sent_alerts[key] = int(r["id"])
                self.poll_soon()
            except (urllib.error.URLError, OSError, ValueError, KeyError, _AuthError):
                pass                       # sin servidor: el aviso igual salió por la red local (UDP)
        threading.Thread(target=work, daemon=True, name="crew-link-alert").start()

    def resolve_key(self, key: str) -> None:
        """Cierra en los teléfonos la alerta que la consola mandó para ese astronauta (ya está bien)."""
        with self._lock:
            alert_id = self._sent_alerts.pop(key, None)
        if alert_id:
            threading.Thread(target=self.ack, args=(alert_id, "Señales recuperadas", True), daemon=True).start()

    def has_open_key(self, key: str) -> bool:
        with self._lock:
            return key in self._sent_alerts

    def poll_soon(self) -> None:
        """Pide una sincronización inmediata (después de mandar algo)."""
        self._wake.set()

    def _auth_token(self) -> str:
        if not self._token:
            self._login()
        return self._token or ""

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
            body = {"since_msg": self._since}
            try:
                resp = self._post("/api/sync", body, self._token)
            except urllib.error.HTTPError as e:
                if e.code != 401:
                    raise
                self._token = None            # sesión vencida: se vuelve a entrar una vez
                self._login()
                resp = self._post("/api/sync", body, self._token)
            sid, last = str(resp.get("server_id") or ""), int(resp.get("last_msg_id") or 0)
            stale = (self._server_id and sid and sid != self._server_id) or last < self._since
            if stale:                         # otra base de datos o se borró: se baja el chat completo
                with self._lock:
                    self._msgs, self._since, self._sent_alerts = [], 0, {}
                resp = self._post("/api/sync", {"since_msg": 0}, self._token)
            self._server_id = sid or self._server_id
            devices = to_devices(resp, crew_ids)
            accounts = [{"username": str(c.get("username", "")), "name": str(c.get("name", "")),
                         "callsign": str(c.get("callsign", "")), "online": bool(c.get("online"))}
                        for c in resp.get("crew", [])]
            with self._lock:
                self._devices, self._alerts = devices, list(resp.get("alerts", []))
                self._accounts, self._public = accounts, str(resp.get("public") or "")
                known = {m["id"] for m in self._msgs}
                for m in resp.get("messages", []):
                    if m.get("id") not in known:
                        self._msgs.append(m)
                    self._since = max(self._since, int(m.get("id") or 0))
                self._msgs = sorted(self._msgs, key=lambda m: m["id"])[-MAX_MSGS:]
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
            self._accounts = []

    def _run(self) -> None:
        import alerts  # aquí para no cargar pandas al importar este módulo en las pruebas
        crew_ids = list(alerts.ROSTER)
        while not self._stop.is_set():
            self.poll_once(crew_ids)
            self._wake.wait(POLL_S)
            self._wake.clear()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="crew-link")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()


def _http_error(e: "urllib.error.HTTPError") -> str:
    try:
        return json.loads(e.read().decode("utf-8")).get("error") or f"Error {e.code}"
    except (ValueError, OSError):
        return f"Error {e.code}"


_LINK: Optional[CrewLink] = None
_LINK_LOCK = threading.Lock()


def get_link() -> CrewLink:
    """Un solo enlace por proceso: sobrevive a las recargas de Streamlit."""
    global _LINK
    with _LINK_LOCK:
        if _LINK is None:
            _LINK = CrewLink()
        return _LINK
