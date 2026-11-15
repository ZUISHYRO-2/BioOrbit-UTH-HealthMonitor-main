"""Prueba de punta a punta: crew_server real + enlace del centro de control. Ejecuta: python -m pytest tests -q"""

import json
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "crew_server"))
import crew_link  # noqa: E402
import fleet  # noqa: E402
import server  # noqa: E402  (crew_server/server.py)

CREW = ["ASTRO-01", "ASTRO-02", "ASTRO-03", "ASTRO-04"]


@pytest.fixture
def crew_server(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path)
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "crew.db")
    monkeypatch.setattr(server, "_db", None)
    monkeypatch.setenv("BIOORBIT_ADMIN", "clave-de-prueba")
    server.db()
    server.ensure_admin()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()
    monkeypatch.setattr(server, "_db", None)


def post(base, path, body, token=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read())


def phone(base, user, callsign, status):
    tok = post(base, "/api/register", {"username": user, "password": "secreto1", "name": user.title(),
                                        "callsign": callsign})["token"]
    post(base, "/api/sync", {"status": status, "device": "Pixel"}, tok)
    return tok


def test_control_ve_los_telefonos(crew_server, monkeypatch):
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "clave-de-prueba")
    phone(crew_server, "ana", "ASTRO-03", {"hr": 74, "spo2": 97, "temp": 36.7, "cam": True, "present": True,
                                            "watch": True, "hr_src": "reloj", "mood": "reposo"})
    link = crew_link.CrewLink(crew_server)
    link.poll_once(CREW)
    assert link.status()[0] == "ok"
    (d,) = link.devices()
    assert d["crew"] == "ASTRO-03" and d["kind"] == "phone" and d["state"] == "online"
    assert d["heart_rate_bpm"] == 74 and d["vital"] is True
    assert "Reloj conectado" in d["detail"] and "En cámara ✓" in d["detail"]
    # y el centro de control lo usa como pulso real de ASTRO-03
    st, data = fleet.vitals_state("ASTRO-03", link.devices())
    assert st == "live" and data["heart_rate_bpm"] == 74


def test_pulso_por_camara_no_reemplaza_signos(crew_server, monkeypatch):
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "clave-de-prueba")
    phone(crew_server, "beto", "ASTRO-04", {"hr": 140, "cam": True, "present": True, "watch": False})
    link = crew_link.CrewLink(crew_server)
    link.poll_once(CREW)
    assert fleet.vitals_state("ASTRO-04", link.devices())[0] == "off"


def test_cuenta_sin_puesto_conocido_y_alertas(crew_server, monkeypatch):
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "clave-de-prueba")
    tok = phone(crew_server, "luis", "PILOTO", {"hr": 70, "alert": "NO_VITALS"})
    post(crew_server, "/api/alert", {"kind": "NO_VITALS", "message": "LUIS sin signos vitales"}, tok)
    link = crew_link.CrewLink(crew_server)
    link.poll_once(CREW)
    assert link.devices()[0]["crew"] is None and link.devices()[0]["alert"] == "NO_VITALS"
    (a,) = link.open_alerts()
    assert link.resolve(a["id"]) and (link.poll_once(CREW) or link.open_alerts() == [])


def test_errores_claros(crew_server, monkeypatch):
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "mala")
    link = crew_link.CrewLink(crew_server)
    link.poll_once(CREW)
    assert link.status()[0] == "auth" and link.devices() == []
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "clave-de-prueba")
    link.poll_once(CREW)
    assert link.status()[0] == "ok"
    down = crew_link.CrewLink("http://127.0.0.1:1")
    down.poll_once(CREW)
    assert down.status()[0] == "down" and "crew_server/server.py" in down.status()[1]


def test_cuenta_que_nunca_sincronizo_no_es_dispositivo(crew_server, monkeypatch):
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "clave-de-prueba")
    post(crew_server, "/api/register", {"username": "eva", "password": "secreto1", "name": "Eva", "callsign": "ASTRO-01"})
    link = crew_link.CrewLink(crew_server)
    link.poll_once(CREW)
    assert link.devices() == []


def test_password_desde_archivo(tmp_path, monkeypatch):
    monkeypatch.delenv("BIOORBIT_CONTROL_PASSWORD", raising=False)
    f = tmp_path / "control_password.txt"
    f.write_text("Usuario: control\nContraseña: abc123\n(otra línea)\n", encoding="utf-8")
    monkeypatch.setattr(crew_link, "PASS_FILE", f)
    assert crew_link.read_password() == "abc123"


# ------------------------------------------------------------------ consola -> teléfonos
def wait_for(cond, s=3.0):
    t = time.time() + s
    while time.time() < t:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_chat_en_los_dos_sentidos(crew_server, monkeypatch):
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "clave-de-prueba")
    tok = phone(crew_server, "ana", "ASTRO-02", {"hr": 70})
    post(crew_server, "/api/chat", {"text": "Hola control"}, tok)
    link = crew_link.CrewLink(crew_server)
    link.poll_once(CREW)
    assert [m["text"] for m in link.messages()] == ["Hola control"]
    assert link.accounts()[0]["name"] == "Ana" and link.accounts()[0]["online"]
    # el control contesta a todos y en privado
    assert link.send_chat("Revisión a las 18:00") == (True, "")
    assert link.send_chat("Ana, ¿todo bien?", "ana")[0]
    assert link.send_chat("   ")[0] is False
    ok, err = link.send_chat("hola", "nadie")
    assert not ok and "no existe" in err
    got = post(crew_server, "/api/sync", {"since_msg": 0}, tok)["messages"]
    assert [(m["from"], m["to"], m["text"]) for m in got] == [
        ("ana", "", "Hola control"), ("control", "", "Revisión a las 18:00"), ("control", "ana", "Ana, ¿todo bien?")]
    link.poll_once(CREW)                   # sin duplicados
    assert len(link.messages()) == 3


def test_alerta_de_la_consola_llega_y_se_cierra(crew_server, monkeypatch):
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "clave-de-prueba")
    tok = phone(crew_server, "ana", "ASTRO-02", {"hr": 70})
    link = crew_link.CrewLink(crew_server)
    link.poll_once(CREW)
    link.send_alert("NO_VITALS", "ASTRO-01 (Hábitat): SIN SIGNOS VITALES.", key="ASTRO-01")
    assert wait_for(lambda: link.has_open_key("ASTRO-01"))
    al = post(crew_server, "/api/sync", {}, tok)["alerts"]
    assert [(a["kind"], a["username"], a["resolved"]) for a in al] == [("NO_VITALS", "control", None)]
    # «Enterado» de la consola en la alerta de un teléfono
    post(crew_server, "/api/alert", {"kind": "SOS", "message": "Ana pidió ayuda"}, tok)
    link.poll_once(CREW)
    sos = next(a for a in link.open_alerts() if a["kind"] == "SOS")
    assert link.ack(sos["id"])
    acks = next(a for a in post(crew_server, "/api/sync", {}, tok)["alerts"] if a["kind"] == "SOS")["acks"]
    assert acks[0]["username"] == "control" and acks[0]["text"] == "Control enterado"
    # volvieron las señales de ASTRO-01: se cierra sola en los teléfonos
    link.resolve_key("ASTRO-01")
    assert wait_for(lambda: all(a["resolved"] for a in post(crew_server, "/api/sync", {}, tok)["alerts"]
                                if a["kind"] == "NO_VITALS"))
    assert not link.has_open_key("ASTRO-01")


def test_sin_servidor_no_truena(monkeypatch):
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "x")
    down = crew_link.CrewLink("http://127.0.0.1:1")
    ok, err = down.send_chat("hola")
    assert not ok and "conexión" in err
    down.send_alert("NO_VITALS", "x", key="ASTRO-01")    # no lanza nada
    assert not down.ack(1)


def test_dispositivos_conectados(crew_server):
    tok = phone(crew_server, "ana", "ASTRO-02", {"hr": 70, "cam": True})
    post(crew_server, "/api/sync", {"status": {"hr": 72}, "device": "tablet-ana"}, tok)   # 2.º equipo, misma cuenta
    ctl = post(crew_server, "/api/login", {"username": "control", "password": "clave-de-prueba"})["token"]
    devs = post(crew_server, "/api/sync", {}, ctl)["devices"]
    assert sorted(d["device"] for d in devs) == ["Pixel", "tablet-ana"]
    assert all(d["online"] and d["name"] == "Ana" and d["callsign"] == "ASTRO-02" for d in devs)
    assert post(crew_server, "/api/sync", {}, tok)["devices"] == []        # solo el control ve la lista
    post(crew_server, "/api/remove_user", {"username": "ana"}, ctl)
    assert post(crew_server, "/api/sync", {}, ctl)["devices"] == []


def test_consola_se_recupera_si_cambia_la_base(crew_server, monkeypatch):
    monkeypatch.setenv("BIOORBIT_CONTROL_PASSWORD", "clave-de-prueba")
    tok = phone(crew_server, "ana", "ASTRO-02", {"hr": 70})
    link = crew_link.CrewLink(crew_server)
    link._since, link._msgs = 40, [{"id": 1, "ts": 1, "from": "x", "to": "", "text": "viejo"}]   # caché de otra base
    post(crew_server, "/api/chat", {"text": "nuevo"}, tok)
    link.poll_once(CREW)
    assert [m["text"] for m in link.messages()] == ["nuevo"]
    r = post(crew_server, "/api/sync", {}, tok)
    assert r["server_id"] and r["last_msg_id"] == 1
