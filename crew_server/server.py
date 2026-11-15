"""
BioOrbit · Servidor de tripulación
==================================
Guarda las cuentas de los astronautas, recibe el estado de cada teléfono (pulso, cámara, alertas),
reparte el chat interno y sirve el dashboard de monitoreo para la PC.

Solo usa la biblioteca estándar de Python (3.9+): no hay que instalar nada.

    py crew_server/server.py                 # puerto 8765
    py crew_server/server.py --port 9000

Los teléfonos en la misma red Wi-Fi lo encuentran solos (anuncio UDP en el puerto 50506).
Con datos móviles: abre un túnel (ver README) y escribe en la app la dirección https que te dé.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import socket
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

VERSION = "1.0"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DB_PATH = DATA / "crew.db"
DASHBOARD = HERE / "dashboard.html"
BEACON_PORT = 50506
ONLINE_SEC = 15          # sin sincronizar en 15 s = desconectado
ROLES = ("astronauta", "control")
MAX_TEXT = 1000

_db_lock = threading.Lock()
_db: sqlite3.Connection | None = None
_login_fail: dict[str, list[float]] = {}
PUBLIC = {"url": os.environ.get("BIOORBIT_PUBLIC", "")}   # dirección https del túnel (datos móviles)


# ------------------------------------------------------------------ base de datos
def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        DATA.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
              username TEXT PRIMARY KEY, name TEXT NOT NULL, callsign TEXT NOT NULL, role TEXT NOT NULL,
              module TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'astronauta',
              salt TEXT NOT NULL, pw TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS status(
              username TEXT PRIMARY KEY, data TEXT NOT NULL, updated REAL NOT NULL, device TEXT, ip TEXT);
            CREATE TABLE IF NOT EXISTS devices(
              device TEXT PRIMARY KEY, username TEXT NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL, ip TEXT);
            CREATE TABLE IF NOT EXISTS hr_hist(username TEXT, ts REAL, hr REAL);
            CREATE TABLE IF NOT EXISTS messages(
              id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, sender TEXT NOT NULL,
              recipient TEXT NOT NULL DEFAULT '', text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS alerts(
              id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, username TEXT NOT NULL,
              kind TEXT NOT NULL, message TEXT NOT NULL, acks TEXT NOT NULL DEFAULT '[]', resolved REAL);
            CREATE INDEX IF NOT EXISTS hr_idx ON hr_hist(username, ts);
            """
        )
        _db.commit()
    return _db


def q(sql: str, args: tuple = (), one: bool = False, commit: bool = False):
    with _db_lock:
        cur = db().execute(sql, args)
        rows = cur.fetchall()
        if commit:
            db().commit()
        if one:
            return rows[0] if rows else None
        return rows


def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(username, password, name, callsign, role, module, kind="astronauta"):
    salt = secrets.token_hex(16)
    q("INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?)",
      (username, name, callsign, role, module, kind, salt, hash_pw(password, salt), time.time()), commit=True)


def new_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    q("INSERT INTO sessions VALUES(?,?,?)", (th(token), username, time.time()), commit=True)
    return token


def public_user(r) -> dict:
    return {"username": r["username"], "name": r["name"], "callsign": r["callsign"], "role": r["role"],
            "module": r["module"], "kind": r["kind"]}


def ensure_admin() -> str | None:
    """Crea la cuenta del control de misión la primera vez. Regresa la contraseña si se acaba de crear."""
    if q("SELECT 1 FROM users WHERE username='control'", one=True):
        return None
    pw = os.environ.get("BIOORBIT_ADMIN") or secrets.token_urlsafe(6)
    create_user("control", pw, "Control de misión", "CONTROL", "Control de misión", "Tierra", "control")
    (DATA / "control_password.txt").write_text(
        f"Usuario: control\nContraseña: {pw}\n(Cámbiala borrando data/crew.db o con --reset-admin)\n", encoding="utf-8")
    return pw


# ------------------------------------------------------------------ lógica
def clean(s, n=80) -> str:
    return str(s or "").strip()[:n]


def crew_snapshot() -> list[dict]:
    now = time.time()
    out = []
    for u in q("SELECT * FROM users WHERE kind='astronauta' ORDER BY callsign, name"):
        st = q("SELECT * FROM status WHERE username=?", (u["username"],), one=True)
        data = json.loads(st["data"]) if st else {}
        hist = [round(r["hr"]) for r in q(
            "SELECT hr FROM hr_hist WHERE username=? AND ts>? ORDER BY ts", (u["username"], now - 300))]
        out.append({**public_user(u), "online": bool(st and now - st["updated"] < ONLINE_SEC),
                    "last_seen": st["updated"] if st else None, "device": st["device"] if st else "", "ip": st["ip"] if st else "", "status": data, "hr_hist": hist[-60:]})
    return out


def devices_snapshot() -> list[dict]:
    now = time.time()
    out = []
    for r in q("SELECT d.*, u.name, u.callsign FROM devices d LEFT JOIN users u ON u.username=d.username "
               "WHERE d.updated>? ORDER BY d.updated DESC", (now - 7 * 86400,)):
        out.append({"device": r["device"], "username": r["username"], "name": r["name"] or r["username"],
                    "callsign": r["callsign"] or "", "ip": r["ip"] or "", "last_seen": r["updated"],
                    "online": now - r["updated"] < ONLINE_SEC, "status": json.loads(r["data"])})
    return out


def msg_dict(r) -> dict:
    return {"id": r["id"], "ts": r["ts"], "from": r["sender"], "to": r["recipient"], "text": r["text"]}


def alert_dict(r) -> dict:
    return {"id": r["id"], "ts": r["ts"], "username": r["username"], "kind": r["kind"], "message": r["message"],
            "acks": json.loads(r["acks"]), "resolved": r["resolved"]}


def visible_messages(user: str, kind: str, since: int, limit=200):
    if kind == "control":       # el control de misión ve todo el chat (también los privados)
        rows = q("SELECT * FROM messages WHERE id>? ORDER BY id DESC LIMIT ?", (since, limit))
    else:
        rows = q("SELECT * FROM messages WHERE id>? AND (recipient='' OR recipient=? OR sender=?) ORDER BY id DESC LIMIT ?",
                 (since, user, user, limit))
    return [msg_dict(r) for r in reversed(rows)]


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "BioOrbitCrew/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # sin ruido en la consola
        pass

    # --- utilidades
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")

    def reply(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def err(self, msg, code=400):
        self.reply({"ok": False, "error": msg}, code)

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 64_000:
            raise ValueError("demasiado grande")
        raw = self.rfile.read(n) if n else b"{}"
        try:
            d = json.loads(raw or b"{}")
            return d if isinstance(d, dict) else {}
        except json.JSONDecodeError:
            return {}

    def auth(self):
        h = self.headers.get("Authorization", "")
        tok = h[7:] if h.startswith("Bearer ") else ""
        if not tok:
            return None
        s = q("SELECT username FROM sessions WHERE token_hash=?", (th(tok),), one=True)
        return q("SELECT * FROM users WHERE username=?", (s["username"],), one=True) if s else None

    # --- verbos
    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/dashboard", "/index.html"):
            body = DASHBOARD.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/ping":
            self.reply({"ok": True, "app": "bioorbit-crew", "version": VERSION, "lan": lan_urls(self.server.server_port),
                        "public": PUBLIC["url"]})
        else:
            self.err("no existe", 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            d = self.body()
        except ValueError:
            return self.err("petición demasiado grande", 413)
        routes = {"/api/register": self.register, "/api/login": self.login, "/api/logout": self.logout,
                  "/api/sync": self.sync, "/api/chat": self.chat, "/api/alert": self.alert,
                  "/api/alert_ack": self.alert_ack, "/api/remove_user": self.remove_user, "/api/set_public": self.set_public}
        fn = routes.get(path)
        if not fn:
            return self.err("no existe", 404)
        try:
            fn(d)
        except Exception as e:  # noqa: BLE001 — que el servidor no se caiga por una petición rara
            print("error en", path, repr(e), file=sys.stderr)
            self.err("error del servidor", 500)

    # --- cuentas
    def register(self, d):
        user = clean(d.get("username"), 32).lower()
        pw = str(d.get("password") or "")
        name = clean(d.get("name"), 60)
        if not (3 <= len(user) <= 32) or not all(c.isalnum() or c in "._-" for c in user):
            return self.err("El usuario debe tener 3 a 32 letras o números (sin espacios).")
        if user == "control":
            return self.err("Ese usuario está reservado.")
        if len(pw) < 6:
            return self.err("La contraseña debe tener al menos 6 caracteres.")
        if not name:
            return self.err("Escribe tu nombre.")
        if q("SELECT 1 FROM users WHERE username=?", (user,), one=True):
            return self.err("Ese usuario ya existe. Inicia sesión o usa otro.", 409)
        callsign = clean(d.get("callsign"), 20).upper() or user.upper()
        create_user(user, pw, name, callsign, clean(d.get("role"), 40) or "Astronauta", clean(d.get("module"), 40) or "Hábitat")
        u = q("SELECT * FROM users WHERE username=?", (user,), one=True)
        print(f"[+] cuenta nueva: {user} ({name}, {callsign})")
        self.reply({"ok": True, "token": new_session(user), "user": public_user(u)})

    def login(self, d):
        user = clean(d.get("username"), 32).lower()
        ip = self.client_address[0]
        now = time.time()
        fails = [t for t in _login_fail.get(ip, []) if now - t < 300]
        if len(fails) >= 10:
            return self.err("Demasiados intentos. Espera unos minutos.", 429)
        u = q("SELECT * FROM users WHERE username=?", (user,), one=True)
        if not u or not hmac.compare_digest(u["pw"], hash_pw(str(d.get("password") or ""), u["salt"])):
            _login_fail[ip] = fails + [now]
            return self.err("Usuario o contraseña incorrectos.", 401)
        _login_fail.pop(ip, None)
        self.reply({"ok": True, "token": new_session(user), "user": public_user(u)})

    def logout(self, d):
        h = self.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            q("DELETE FROM sessions WHERE token_hash=?", (th(h[7:]),), commit=True)
        self.reply({"ok": True})

    def set_public(self, d):
        """tunel.py avisa aquí la dirección https del túnel. Solo desde esta misma PC."""
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            return self.err("Solo desde la PC del servidor.", 403)
        url = clean(d.get("url"), 200)
        if url and not url.startswith("https://"):
            return self.err("La dirección debe empezar con https://")
        PUBLIC["url"] = url.rstrip("/")
        print(f"[i] dirección para datos móviles: {PUBLIC['url'] or '(ninguna)'}")
        self.reply({"ok": True})

    def remove_user(self, d):
        u = self.auth()
        if not u or u["kind"] != "control":
            return self.err("Solo el control de misión.", 403)
        name = clean(d.get("username"), 32).lower()
        if name == "control":
            return self.err("No se puede borrar el control.")
        for t in ("users", "sessions", "status", "hr_hist", "devices"):
            q(f"DELETE FROM {t} WHERE username=?", (name,), commit=True)
        self.reply({"ok": True})

    # --- estado + novedades (los teléfonos y el dashboard lo llaman cada ~2 s)
    def sync(self, d):
        u = self.auth()
        if not u:
            return self.err("Sesión vencida. Vuelve a iniciar sesión.", 401)
        now = time.time()
        st = d.get("status")
        if u["kind"] == "astronauta" and isinstance(st, dict):
            st = {k: v for k, v in list(st.items())[:30] if isinstance(v, (int, float, str, bool, type(None)))}
            q("INSERT OR REPLACE INTO status VALUES(?,?,?,?,?)",
              (u["username"], json.dumps(st)[:4000], now, clean(d.get("device"), 40), self.client_address[0]), commit=True)
            dev = clean(d.get("device"), 40)
            if dev:
                q("INSERT OR REPLACE INTO devices VALUES(?,?,?,?,?)",
                  (dev, u["username"], json.dumps(st)[:4000], now, self.client_address[0]), commit=True)
            hr = st.get("hr")
            if isinstance(hr, (int, float)) and 20 <= hr <= 250:
                last = q("SELECT ts FROM hr_hist WHERE username=? ORDER BY ts DESC LIMIT 1", (u["username"],), one=True)
                if not last or now - last["ts"] >= 5:
                    q("INSERT INTO hr_hist VALUES(?,?,?)", (u["username"], now, float(hr)), commit=True)
        since_m = int(d.get("since_msg") or 0)
        since_a = int(d.get("since_alert") or 0)
        alerts = q("SELECT * FROM alerts WHERE id>? OR (resolved IS NULL AND ts>?) ORDER BY id DESC LIMIT 50",
                   (since_a, now - 3600))
        self.reply({"ok": True, "now": now, "me": public_user(u), "crew": crew_snapshot(), "devices": devices_snapshot() if u["kind"] == "control" else [], "public": PUBLIC["url"],
                    "messages": visible_messages(u["username"], u["kind"], since_m),
                    "alerts": [alert_dict(r) for r in reversed(alerts)]})

    def chat(self, d):
        u = self.auth()
        if not u:
            return self.err("Sesión vencida.", 401)
        text = str(d.get("text") or "").strip()[:MAX_TEXT]
        to = clean(d.get("to"), 32).lower()
        if not text:
            return self.err("Mensaje vacío.")
        if to and not q("SELECT 1 FROM users WHERE username=?", (to,), one=True):
            return self.err("Ese tripulante no existe.")
        q("INSERT INTO messages(ts,sender,recipient,text) VALUES(?,?,?,?)", (time.time(), u["username"], to, text), commit=True)
        r = q("SELECT * FROM messages WHERE id=last_insert_rowid()", one=True)
        self.reply({"ok": True, "message": msg_dict(r)})

    def alert(self, d):
        u = self.auth()
        if not u:
            return self.err("Sesión vencida.", 401)
        kind = clean(d.get("kind"), 20).upper() or "ALERTA"
        msg = clean(d.get("message"), 300) or f"{u['callsign']} necesita ayuda."
        if kind == "RESOLVED":   # «estoy bien»: cierra las alertas abiertas de esa persona
            q("UPDATE alerts SET resolved=? WHERE username=? AND resolved IS NULL", (time.time(), u["username"]), commit=True)
            return self.reply({"ok": True})
        q("INSERT INTO alerts(ts,username,kind,message) VALUES(?,?,?,?)", (time.time(), u["username"], kind, msg), commit=True)
        print(f"[!] ALERTA {kind}: {msg}")
        self.reply({"ok": True, "id": q("SELECT last_insert_rowid() AS i", one=True)["i"]})

    def alert_ack(self, d):
        u = self.auth()
        if not u:
            return self.err("Sesión vencida.", 401)
        r = q("SELECT * FROM alerts WHERE id=?", (int(d.get("id") or 0),), one=True)
        if not r:
            return self.err("Esa alerta no existe.", 404)
        acks = json.loads(r["acks"])
        if not any(a["username"] == u["username"] for a in acks):
            acks.append({"username": u["username"], "callsign": u["callsign"], "ts": time.time(),
                         "text": clean(d.get("text"), 60) or "Voy en camino"})
        resolved = time.time() if d.get("resolve") and u["kind"] == "control" else r["resolved"]
        q("UPDATE alerts SET acks=?, resolved=? WHERE id=?", (json.dumps(acks), resolved, r["id"]), commit=True)
        self.reply({"ok": True})


# ------------------------------------------------------------------ red
def lan_ips() -> list[str]:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def lan_urls(port: int) -> list[str]:
    return [f"http://{ip}:{port}" for ip in lan_ips()]


def beacon(port: int, stop: threading.Event):
    """Anuncia el servidor en la red local cada 2 s para que los teléfonos lo encuentren solos."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while not stop.is_set():
        for ip in lan_ips():
            msg = json.dumps({"bioorbit_server": f"http://{ip}:{port}", "version": VERSION}).encode()
            parts = ip.split(".")
            for dest in ("255.255.255.255", ".".join(parts[:3] + ["255"])):
                try:
                    s.sendto(msg, (dest, BEACON_PORT))
                except OSError:
                    pass
        stop.wait(2)


def main():
    ap = argparse.ArgumentParser(description="Servidor de tripulación BioOrbit")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--no-beacon", action="store_true", help="no anunciarse en la red local")
    ap.add_argument("--public", default="", help="dirección https del túnel, si ya la sabes")
    ap.add_argument("--reset-admin", action="store_true", help="genera una contraseña nueva para «control»")
    a = ap.parse_args()

    db()
    if a.public:
        PUBLIC["url"] = a.public.rstrip("/")
    if a.reset_admin:
        q("DELETE FROM users WHERE username='control'", commit=True)
    pw = ensure_admin()
    httpd = ThreadingHTTPServer((a.host, a.port), Handler)
    httpd.daemon_threads = True
    stop = threading.Event()
    if not a.no_beacon:
        threading.Thread(target=beacon, args=(a.port, stop), daemon=True).start()

    print("=" * 62)
    print(" BioOrbit · Servidor de tripulación", VERSION)
    print("=" * 62)
    print(f" Dashboard en esta PC:   http://localhost:{a.port}")
    for u in lan_urls(a.port):
        print(f" Teléfonos (mismo Wi-Fi): {u}")
    print(" Datos móviles: " + (PUBLIC["url"] or "abre el túnel (iniciar_tunel.bat) en otra ventana."))
    if pw:
        print(f"\n Cuenta del dashboard -> usuario: control   contraseña: {pw}")
        print(f" (guardada en {DATA / 'control_password.txt'})")
    else:
        print(f"\n Dashboard: usuario «control» (contraseña en {DATA / 'control_password.txt'})")
    print("\n Ctrl+C para detener.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()


if __name__ == "__main__":
    main()
