"""
Receptor de alertas BioOrbit. Ejecútalo en el equipo (o laptop) de cada tripulante cercano:

    python src/alert_listener.py

Escucha los avisos UDP que envía la consola cuando se pierden los signos vitales
de alguien y los muestra en pantalla con un pitido de terminal.
"""

import json
import socket

from alerts import UDP_PORT


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", UDP_PORT))
        print(f"[BioOrbit] Escuchando alertas en el puerto {UDP_PORT}. Ctrl+C para salir.")
        while True:
            data, addr = s.recvfrom(4096)
            try:
                a = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            print("\a" + "=" * 60)
            print(f"  ALERTA ({a.get('kind')}) desde {addr[0]}")
            print(f"  {a.get('message')}")
            print("=" * 60)


if __name__ == "__main__":
    main()
