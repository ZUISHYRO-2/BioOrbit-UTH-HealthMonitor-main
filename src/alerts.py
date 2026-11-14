"""
BioOrbit-UTH - Alertas por pérdida de signos vitales.

Flujo (pensado para evitar falsas alarmas):
  OK -> CONFIRMING (cuenta regresiva para que la persona diga "estoy bien")
     -> DUE (se agotó la cuenta) -> SENT (se avisó a los tripulantes cercanos)

Canales de aviso (todos opcionales y sin credenciales por defecto):
  - Registro local  data/alerts_log.jsonl
  - Difusión UDP en la red local (la recibe src/alert_listener.py en otros equipos)
  - Notificación push con ntfy.sh si defines BIOORBIT_NTFY_TOPIC

PROTOTIPO: no es un dispositivo médico certificado.
"""

import json
import os
import socket
import time
from dataclasses import dataclass
from math import hypot
from pathlib import Path

import pandas as pd

UDP_PORT = 50505
LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "alerts_log.jsonl"

# Tripulación y posición aproximada (metros) dentro de la nave/estación.
# En un sistema real saldría de balizas BLE/UWB; aquí es configuración editable.
ROSTER = {
    "ASTRO-01": {"role": "Comandante", "module": "Hábitat", "pos": (0.0, 0.0)},
    "ASTRO-02": {"role": "Ingeniera de vuelo", "module": "Laboratorio", "pos": (9.0, 4.0)},
    "ASTRO-03": {"role": "Especialista médico", "module": "Laboratorio", "pos": (12.0, 6.0)},
    "ASTRO-04": {"role": "Especialista de carga", "module": "Almacén", "pos": (38.0, 2.0)},
}

FIRST_RESPONSE = [
    "Llega hasta la persona y háblale fuerte; toca su hombro. ¿Responde?",
    "Si no responde ni respira con normalidad: pide ayuda y trae el desfibrilador (DEA).",
    "Inicia compresiones torácicas al centro del pecho, firmes y continuas, hasta que llegue apoyo.",
    "Avisa al cirujano de vuelo / control de misión y sigue sus indicaciones.",
]


def _missing(v) -> bool:
    return v is None or pd.isna(v) or v <= 0


def vitals_status(row) -> str:
    """OK, SENSOR_FAULT (falta una señal) o NO_VITALS (faltan FC y SpO2 a la vez)."""
    hr_bad = _missing(row.get("heart_rate_bpm"))
    sp_bad = _missing(row.get("spo2_pct"))
    if hr_bad and sp_bad:
        return "NO_VITALS"
    if hr_bad or sp_bad:
        return "SENSOR_FAULT"
    return "OK"


@dataclass
class Emergency:
    phase: str = "OK"  # OK | CONFIRMING | DUE | SENT
    missing: int = 0
    deadline: float = 0.0
    ack_until: float = 0.0


def step(em: Emergency, status: str, now: float, ticks_needed: int = 3,
         confirm_s: float = 10.0) -> str:
    """Avanza la máquina de estados. Devuelve 'DUE' cuando toca avisar, 'RECOVERED' al volver las señales."""
    if status != "NO_VITALS":
        recovered = em.phase in ("CONFIRMING", "SENT")
        em.phase, em.missing = "OK", 0
        return "RECOVERED" if recovered else ""
    if now < em.ack_until:  # la persona dijo "estoy bien"; se espera antes de volver a evaluar
        return ""
    em.missing += 1
    if em.phase == "OK" and em.missing >= ticks_needed:
        em.phase, em.deadline = "CONFIRMING", now + confirm_s
    elif em.phase == "CONFIRMING" and now >= em.deadline:
        em.phase = "DUE"
        return "DUE"
    return ""


def acknowledge(em: Emergency, now: float, snooze_s: float = 60.0) -> None:
    em.phase, em.missing, em.ack_until = "OK", 0, now + snooze_s


def nearby_crew(crew_id: str, radius_m: float = 20.0):
    """Tripulantes dentro del radio, del más cercano al más lejano."""
    x0, y0 = ROSTER[crew_id]["pos"]
    out = []
    for cid, info in ROSTER.items():
        if cid == crew_id:
            continue
        d = hypot(info["pos"][0] - x0, info["pos"][1] - y0)
        if d <= radius_m:
            out.append((cid, info, d))
    return sorted(out, key=lambda t: t[2])


def broadcast(kind: str, crew_id: str, radius_m: float = 20.0) -> dict:
    """Envía el aviso por todos los canales disponibles y devuelve un resumen."""
    near = nearby_crew(crew_id, radius_m)
    texts = {
        "NO_VITALS": f"{crew_id} ({ROSTER[crew_id]['module']}): SIN SIGNOS VITALES. Acudan de inmediato.",
        "SUPPORT": f"{crew_id} ({ROSTER[crew_id]['module']}) pide apoyo humano ahora.",
    }
    msg = texts.get(kind, f"{crew_id}: alerta {kind}")
    payload = {"ts": time.time(), "kind": kind, "crew": crew_id, "module": ROSTER[crew_id]["module"],
               "message": msg, "notified": [c for c, _, _ in near]}
    channels = []

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        channels.append(("Registro local", "ok"))
    except OSError as e:
        channels.append(("Registro local", f"falló: {e}"))

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(json.dumps(payload, ensure_ascii=False).encode("utf-8"), ("255.255.255.255", UDP_PORT))
        channels.append(("Red local (UDP)", "ok"))
    except OSError as e:
        channels.append(("Red local (UDP)", f"falló: {e}"))

    topic = os.getenv("BIOORBIT_NTFY_TOPIC")
    if topic:
        try:
            import requests
            requests.post(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"), timeout=5,
                          headers={"Title": "BioOrbit ALERTA", "Priority": "urgent", "Tags": "rotating_light"})
            channels.append(("Push (ntfy)", "ok"))
        except Exception as e:  # noqa: BLE001
            channels.append(("Push (ntfy)", f"falló: {e}"))

    return {"kind": kind, "crew": crew_id, "message": msg, "when": time.strftime("%H:%M:%S"),
            "notified": [(c, i["role"], d) for c, i, d in near], "channels": channels}
