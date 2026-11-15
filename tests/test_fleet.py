"""Pruebas del registro de dispositivos y del receptor HTTP. Ejecuta:  python -m pytest tests -q"""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import fleet  # noqa: E402
import fleet_server  # noqa: E402


@pytest.fixture(autouse=True)
def fleet_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet, "FLEET_DIR", tmp_path / "fleet")
    return tmp_path / "fleet"


def test_report_valida_y_limpia():
    r = fleet.report({"device_id": "movil-1", "crew": "ASTRO-02", "kind": "phone", "name": "Pixel <b>7</b>",
                      "heart_rate_bpm": "72", "spo2_pct": float("nan"), "battery_pct": 55, "kind_x": 1})
    assert r["heart_rate_bpm"] == 72.0 and "spo2_pct" not in r
    assert "<" not in r["name"] and ">" not in r["name"]
    assert (fleet.FLEET_DIR / "movil-1.json").exists()


@pytest.mark.parametrize("bad", [
    {"crew": "ASTRO-01"}, {"device_id": "../x", "crew": "ASTRO-01"}, {"device_id": "a b", "crew": "ASTRO-01"},
    {"device_id": "ok", "crew": ""}, [], "texto",
])
def test_report_rechaza_invalidos(bad):
    with pytest.raises(fleet.FleetError):
        fleet.report(bad)


def test_el_tipo_sim_no_se_puede_falsear():
    assert fleet.report({"device_id": "x", "crew": "ASTRO-01", "kind": "sim"})["kind"] == "other"


def test_estados_por_edad():
    assert fleet.state_of(2) == "online" and fleet.state_of(20) == "stale" and fleet.state_of(300) == "offline"


def test_vitals_state_live_lost_off():
    now = time.time()
    fleet.report({"device_id": "w", "crew": "ASTRO-01", "kind": "phone", "heart_rate_bpm": 70}, now=now - 2)
    st, data = fleet.vitals_state("ASTRO-01", fleet.read_all(now))
    assert st == "live" and data["heart_rate_bpm"] == 70
    fleet.report({"device_id": "w", "crew": "ASTRO-01", "kind": "phone", "heart_rate_bpm": 70}, now=now - 30)
    assert fleet.vitals_state("ASTRO-01", fleet.read_all(now))[0] == "lost"
    fleet.report({"device_id": "w", "crew": "ASTRO-01", "kind": "phone", "heart_rate_bpm": 70}, now=now - 600)
    assert fleet.vitals_state("ASTRO-01", fleet.read_all(now))[0] == "off"
    assert fleet.vitals_state("ASTRO-02", fleet.read_all(now))[0] == "off"


def test_pulso_cero_es_perdida_de_signos():
    fleet.report({"device_id": "w", "crew": "ASTRO-01", "kind": "watch", "heart_rate_bpm": 0})
    assert fleet.vitals_state("ASTRO-01", fleet.read_all())[0] == "lost"


def test_la_camara_no_reemplaza_signos_vitales():
    fleet.report({"device_id": "h", "crew": "ASTRO-01", "kind": "camera", "heart_rate_bpm": 140})
    assert fleet.vitals_state("ASTRO-01", fleet.read_all())[0] == "off"


def test_hrv_solo_si_es_real():
    fleet.report({"device_id": "w", "crew": "ASTRO-01", "kind": "watch", "heart_rate_bpm": 70, "hrv_rmssd_ms": 30})
    assert fleet.vitals_state("ASTRO-01", fleet.read_all())[1]["hrv_source"] == ""
    fleet.report({"device_id": "w", "crew": "ASTRO-01", "kind": "watch", "heart_rate_bpm": 70,
                  "hrv_rmssd_ms": 30, "hrv_real": True})
    assert fleet.vitals_state("ASTRO-01", fleet.read_all())[1]["hrv_source"] == "Intervalos RR GATT"


def _post(port, body, token=None, raw=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/report", data=raw or json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("X-BioOrbit-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), fleet_server.make_handler(token="secreto"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def test_servidor_token_y_validaciones(server):
    ok = {"device_id": "tel-1", "crew": "ASTRO-02", "kind": "phone", "heart_rate_bpm": 75}
    assert _post(server, ok) == 401
    assert _post(server, ok, token="malo") == 401
    assert _post(server, ok, token="secreto") == 200
    assert _post(server, {**ok, "crew": "ASTRO-99"}, token="secreto") == 400
    assert _post(server, {}, token="secreto", raw=b"no es json") == 400
    assert _post(server, {}, token="secreto", raw=b"x" * (fleet.MAX_BYTES + 1)) == 413
    assert fleet.read_all()[0]["device_id"] == "tel-1"
