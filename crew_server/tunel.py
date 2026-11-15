"""
Abre un túnel https gratis con Cloudflare para que los teléfonos con datos móviles lleguen al servidor,
y le avisa al servidor la dirección para que los teléfonos la aprendan solos.

    py crew_server/tunel.py            (con el servidor ya corriendo en otra ventana)

Necesita cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
(en Windows: winget install --id Cloudflare.cloudflared). No hace falta cuenta.
La dirección cambia cada vez que lo abres; los teléfonos la aprenden en cuanto se conectan por Wi-Fi
o puedes escribirla a mano en la app (Tripulación → Servidor).
"""
import json
import re
import shutil
import subprocess
import sys
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765


def tell_server(url: str) -> None:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/set_public", data=json.dumps({"url": url}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5).read()
        print("   El servidor ya la conoce: los teléfonos la guardan solos al sincronizar.")
    except Exception as e:  # noqa: BLE001
        print("   (No pude avisarle al servidor:", e, "— ¿está corriendo server.py?)")


def main():
    exe = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
    if not exe:
        print("No encontré cloudflared. Instálalo con:\n   winget install --id Cloudflare.cloudflared\n"
              "y vuelve a abrir esta ventana.")
        sys.exit(1)
    print(f"Abriendo túnel a http://localhost:{PORT} … (Ctrl+C para cerrar)")
    p = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{PORT}"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    found = False
    try:
        for line in p.stdout:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m and not found:
                found = True
                print("\n" + "=" * 60 + f"\n Dirección para datos móviles:\n   {m.group(0)}\n" + "=" * 60)
                tell_server(m.group(0))
    except KeyboardInterrupt:
        pass
    finally:
        p.terminate()
        try:
            tell_server("")
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
