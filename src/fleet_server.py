"""
Receptor de dispositivos de BioOrbit-UTH (centro de control).

    python src/fleet_server.py

Déjalo corriendo en la laptop del centro de control, junto a `streamlit run src/app.py`.
Otras laptops (HUD de cámara) y teléfonos le mandan su estado:

    POST http://<ip-de-esta-laptop>:8766/report        (JSON, ver docs/fleet_api.md)
    GET  http://<ip-de-esta-laptop>:8766/health

Si defines BIOORBIT_FLEET_TOKEN antes de arrancar, todos los reportes deben traer
el mismo valor en el encabezado X-BioOrbit-Token (si no, responde 401).
Solo acepta tripulantes que existan en alerts.ROSTER.

PROTOTIPO educativo: úsalo en una red local de confianza, sin exponerlo a internet.
"""

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import alerts
import fleet


def make_handler(token=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BioOrbitFleet/1.0"

        def _send(self, code, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            # La app móvil corre como página web dentro del teléfono: necesita CORS.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-BioOrbit-Token")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self):
            if not token:
                return True
            return hmac.compare_digest(self.headers.get("X-BioOrbit-Token", ""), token)

        def do_OPTIONS(self):  # noqa: N802
            self._send(204, {})

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._send(200, {"ok": True, "crew": list(alerts.ROSTER)})
            else:
                self._send(404, {"error": "no existe"})

        def do_POST(self):  # noqa: N802
            if self.path != "/report":
                return self._send(404, {"error": "no existe"})
            if not self._authorized():
                return self._send(401, {"error": "token inválido"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = -1
            if n <= 0 or n > fleet.MAX_BYTES:
                return self._send(413, {"error": f"cuerpo vacío o mayor a {fleet.MAX_BYTES} bytes"})
            try:
                payload = json.loads(self.rfile.read(n).decode("utf-8"))
                if str(payload.get("crew", "")) not in alerts.ROSTER:
                    raise fleet.FleetError(f"crew desconocido; usa uno de {list(alerts.ROSTER)}")
                rep = fleet.report(payload)
            except (ValueError, UnicodeDecodeError, AttributeError) as e:  # FleetError hereda de ValueError
                return self._send(400, {"error": str(e)})
            except OSError as e:
                return self._send(500, {"error": f"no se pudo guardar: {e}"})
            self._send(200, {"ok": True, "device_id": rep["device_id"]})

        def log_message(self, fmt, *args):  # sin ruido en la terminal
            pass

    return Handler


def main():
    token = os.getenv("BIOORBIT_FLEET_TOKEN") or None
    srv = ThreadingHTTPServer(("0.0.0.0", fleet.PORT), make_handler(token))
    ip = fleet.lan_ip()
    print(f"[BioOrbit] Receptor de dispositivos en http://{ip}:{fleet.PORT}  (Ctrl+C para salir)")
    print(f"[BioOrbit] Otras laptops: set BIOORBIT_FLEET_URL=http://{ip}:{fleet.PORT}")
    print("[BioOrbit] Con token: " + ("sí (BIOORBIT_FLEET_TOKEN)" if token else "NO — solo para redes de confianza"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
