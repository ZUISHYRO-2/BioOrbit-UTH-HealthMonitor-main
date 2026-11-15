"""Connect the desktop monitor to a Wear OS bridge over Bluetooth LE."""

import sys
import time

try:
    import msvcrt
except ImportError:
    msvcrt = None

from ble_watch import BLEAK_AVAILABLE, get_watch_manager, scan_ble_devices_sync


def _exit_requested() -> bool:
    """Return True if the user pressed Q or Esc in the Windows console."""
    if msvcrt is None or not sys.stdin or not sys.stdin.isatty():
        return False
    requested = False
    while msvcrt.kbhit():
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            if msvcrt.kbhit():
                msvcrt.getwch()
            continue
        if key.lower() == "q" or key == "\x1b":
            requested = True
    return requested


def main() -> None:
    if not BLEAK_AVAILABLE:
        raise RuntimeError("Instala las dependencias con: venv\\Scripts\\python.exe -m pip install -r requirements.txt")

    print("Escaneando dispositivos BLE cercanos durante 10 segundos...")
    discovered = scan_ble_devices_sync(timeout=10.0, include_unnamed=False)
    devices = [
        device
        for device in discovered
        if device.is_watch_candidate or device.has_hr_service
    ]
    if not devices:
        print(
            "No se encontraron relojes ni dispositivos con perfil cardíaco. "
            "Verifica Bluetooth y que BioOrbit Watch Bridge esté abierto en el reloj."
        )
        return

    for index, device in enumerate(devices):
        profile = "Heart Rate GATT" if device.has_hr_service else "sin perfil cardíaco anunciado"
        print(f"{index}: {device.name} | {device.address} | RSSI {device.rssi} dBm | {profile}")

    while True:
        choice = input("Número del Pixel Watch / BioOrbit Watch Bridge (o Q para salir): ").strip()
        if choice.lower() == "q":
            return
        if choice.isdigit() and int(choice) < len(devices):
            device = devices[int(choice)]
            break
        print("Selección inválida.")

    manager = get_watch_manager()
    manager.connect_ble(device.address, device.name)
    print("Conectando. Presiona 'Q', 'Esc' o Ctrl+C para desconectar el reloj y salir.")

    last_packet_count = -1
    last_status = ""
    try:
        while True:
            if _exit_requested():
                print("\nDesconectando reloj...")
                break
            snapshot = manager.get_snapshot()
            if snapshot.packet_count != last_packet_count:
                last_packet_count = snapshot.packet_count
                if snapshot.packet_count:
                    spo2 = f"{snapshot.spo2_pct:.1f}%" if snapshot.spo2_pct is not None else "N/D"
                    print(
                        f"{snapshot.device_name}: {snapshot.heart_rate_bpm:.0f} BPM | "
                        f"HRV {snapshot.hrv_rmssd_ms:.1f} ms ({snapshot.hrv_source}) | "
                        f"SpO2 {spo2} | batería {snapshot.battery_pct if snapshot.battery_pct is not None else 'N/D'}%"
                    )
            if snapshot.status_message != last_status:
                last_status = snapshot.status_message
                print(snapshot.status_message)
            if not snapshot.connected and snapshot.mode == "disconnected" and snapshot.status_message.startswith("Error BLE"):
                raise RuntimeError(snapshot.status_message)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nDesconectando reloj...")
    finally:
        manager.disconnect()


if __name__ == "__main__":
    main()
