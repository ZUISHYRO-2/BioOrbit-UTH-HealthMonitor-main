"""
Luma - compañero virtual de apoyo emocional para la tripulación.

Funciona sin internet con reglas empáticas. Si defines ANTHROPIC_API_KEY, usa un modelo
de lenguaje para conversar con más naturalidad (se envían al servicio el texto del chat y
un resumen de biometría, así que actívalo solo con consentimiento de la persona).
Si ocurre cualquier error de red, vuelve automáticamente a las reglas.

Luma es un acompañante, no un profesional de salud mental: no diagnostica y, ante señales
de crisis, pide apoyo humano de inmediato.
"""

import json
import os
import random
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

NAME = "Luma"

CRISIS = re.compile(
    r"suicid|quitarme la vida|matarme|no quiero vivir|hacerme da[ñn]o|terminar con todo|mejor muerto",
    re.I,
)
TOPICS = {
    "ansiedad": r"ansios|nervios|p[aá]nico|angusti|estr[eé]s|preocupad|agobi",
    "tristeza": r"triste|soledad|\bsol[oa]\b|extra[ñn]o|llor|deprim|vac[ií]o|desanim",
    "cansancio": r"cansad|sue[ñn]o|insomnio|agotad|fatiga|dormir|dorm[ií]",
    "enojo": r"enoj|furios|molest|harto|irritad|frustr",
    "bien": r"\bbien\b|content|feliz|tranquil|animad|genial|motivad",
    "gracias": r"gracias",
}
REPLIES = {
    "ansiedad": [
        "Se siente pesado cuando la mente corre. Probemos algo corto: respiremos juntos en el ejercicio de la derecha, un par de rondas.",
        "Lo que sientes es una reacción normal a un entorno exigente. Intenta nombrar en voz alta tres cosas que ves a tu alrededor; ayuda a aterrizar.",
    ],
    "tristeza": [
        "Gracias por contármelo. Extrañar y sentirse lejos es muy humano en una misión larga. ¿Te gustaría escribirle un mensaje a alguien de casa hoy?",
        "Aquí estoy contigo. A veces ayuda también hablar con un compañero a bordo; no tienes que cargar esto en silencio.",
    ],
    "cansancio": [
        "Suena a que tu cuerpo pide descanso. Si puedes, baja la luz, estira cuello y hombros y reserva un bloque corto para dormir.",
        "El cansancio acumulado pesa en el ánimo también. Hoy prioriza una cosa importante y deja el resto para mañana.",
    ],
    "enojo": [
        "Tiene sentido frustrarse cuando el espacio es chico y la rutina larga. Antes de responder a alguien, prueba tres respiraciones lentas.",
        "Gracias por decirlo en vez de guardarlo. ¿Quieres contarme qué lo detonó?",
    ],
    "bien": [
        "¡Qué bueno escucharlo! Aprovecha ese ánimo para charlar con alguien de la tripulación; el buen humor se contagia.",
    ],
    "gracias": ["Para eso estoy. Cuando quieras, seguimos hablando."],
    "otro": [
        "Te escucho. Cuéntame un poco más de cómo ha sido tu día.",
        "Gracias por compartirlo. ¿Cómo te sientes ahora mismo, en una palabra?",
    ],
}
CRISIS_TEXT = (
    "Gracias por decírmelo. No quiero que lo cargues solo ahora mismo. "
    "Por favor habla ya con un compañero cercano o con el cirujano de vuelo: pulsa «Pedir apoyo humano» "
    "y les aviso. Si estás en la Tierra y piensas en hacerte daño, llama a emergencias o a una línea "
    "de crisis de tu país. Yo me quedo aquí contigo mientras llega alguien."
)

SYSTEM = (
    "Eres Luma, un pequeño robot compañero amistoso para tripulantes de misiones espaciales. Hablas en español, "
    "con calidez y frases cortas (máximo 4). Escuchas primero, validas emociones sin reforzar ideas dañinas "
    "y propones UNA acción pequeña (respirar, hablar con un compañero, descansar). No diagnosticas ni "
    "sustituyes a un profesional. Si hay riesgo de autolesión, pide apoyo humano inmediato. "
    "Haz como máximo una pregunta por mensaje."
)


@dataclass
class Reply:
    text: str
    crisis: bool = False


def _num(row, key):
    try:
        v = row[key]
        return None if pd.isna(v) else float(v)
    except (KeyError, TypeError):
        return None


def body_hint(row) -> str:
    """Observación biométrica breve, solo cuando hay algo que decir."""
    if row is None:
        return ""
    hrv, sleep, co2 = _num(row, "hrv_rmssd_ms"), _num(row, "sleep_efficiency_pct"), _num(row, "cabin_co2_ppm")
    hints = []
    if hrv is not None and hrv < 30:
        hints.append(f"tu variabilidad cardíaca está baja ({hrv:.0f} ms), señal de que tu cuerpo está bajo carga")
    if sleep is not None and sleep < 70:
        hints.append(f"tu eficiencia de sueño fue de {sleep:.0f}%")
    if co2 is not None and co2 > 4000:
        hints.append(f"el CO₂ de la cabina está alto ({co2:.0f} ppm) y eso puede dar dolor de cabeza e irritabilidad")
    return ("Por cierto, " + "; ".join(hints) + ".") if hints else ""


def greeting(who: str, row) -> str:
    base = f"¡Hola, {who}! Soy Luma, tu compañero a bordo. Puedes contarme cómo te sientes cuando quieras."
    hint = body_hint(row)
    return f"{base} {hint}" if hint else base


def _llm(history, row):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import requests
        msgs = [{"role": r, "content": t} for r, t in history[-12:]]
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
        if not msgs:
            return None
        system = SYSTEM + (f" Contexto biométrico (úsalo solo si es relevante): {body_hint(row)}" if body_hint(row) else "")
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.getenv("BIOORBIT_MODEL", "claude-sonnet-5-5"), "max_tokens": 300,
                  "system": system, "messages": msgs},
            timeout=20,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"]).strip() or None
    except Exception:  # noqa: BLE001
        return None


def reply(text: str, who: str, row, history) -> Reply:
    if CRISIS.search(text):
        return Reply(CRISIS_TEXT, crisis=True)
    out = _llm(history, row)
    if out:
        return Reply(out)
    topic = next((t for t, rx in TOPICS.items() if re.search(rx, text, re.I)), "otro")
    msg = random.choice(REPLIES[topic])
    if topic in ("ansiedad", "tristeza", "cansancio", "enojo"):
        hint = body_hint(row)
        if hint:
            msg = f"{msg} {hint}"
    return Reply(msg)


# ----------------------------------------------------------------------------
# Lectura de la situación del tripulante (ventana de telemetría reciente)
# ----------------------------------------------------------------------------
REASONS = {
    "hrv_low": "tu HRV bajó (menor recuperación)",
    "sleep_low": "tu sueño ha sido poco eficiente",
    "alerts_high": "han saltado varias alertas fisiológicas",
}


def physio_state(window: pd.DataFrame) -> dict:
    """Interpreta los últimos registros (~3 h) de un tripulante. Nivel 0 estable, 1 leve, 2 alto."""
    hrv = float(window["hrv_rmssd_ms"].mean())
    sleep = float(window["sleep_efficiency_pct"].mean())
    crit_share = float((window["alert_level"] == "CRÍTICO").mean())
    points, reasons = 0, []
    if hrv == hrv:
        if hrv < 25:
            points += 2; reasons.append("hrv_low")
        elif hrv < 40:
            points += 1; reasons.append("hrv_low")
    if sleep == sleep:
        if sleep < 70:
            points += 2; reasons.append("sleep_low")
        elif sleep < 80:
            points += 1; reasons.append("sleep_low")
    if crit_share >= 0.25:
        points += 2; reasons.append("alerts_high")
    elif crit_share >= 0.10:
        points += 1; reasons.append("alerts_high")
    level = 2 if points >= 4 else 1 if points >= 2 else 0
    return {"hrv": hrv, "sleep": sleep, "crit_share": crit_share, "level": level, "reasons": reasons}


# Consejos cortos para la tarjeta de Luma en el HUD
HUD_TIPS = {
    "stable": [
        "Todo estable. Estírate un minuto y toma agua.",
        "Buen momento para grabarle un mensaje a tu familia.",
        "Mira la Tierra por la ventana un momento: ayuda a reconectar.",
        "Respira hondo: pulsa B y te guío cuatro tiempos.",
    ],
    "hrv_low": ["Tu HRV bajó: hagamos 4 respiraciones lentas para recuperarte (tecla B)."],
    "sleep_low": ["Tu sueño ha sido poco eficiente: baja la luz una hora antes de dormir."],
    "alerts_high": ["Varias alertas seguidas: haz una pausa corta y avisa a tu equipo."],
    "unsteady": ["Te noto inquieto en la cámara: relaja cuello y hombros un momento."],
    "support": ["Si algo te pesa, platícalo hoy con alguien de la tripulación."],
    "escalate": ["Hoy conviene hablar con el cirujano de vuelo o con el comandante."],
}


def hud_tips(level: int, reasons: list, unsteady: bool = False) -> list:
    tips = []
    for r in reasons:
        tips += HUD_TIPS.get(r, [])
    if unsteady:
        tips += HUD_TIPS["unsteady"]
    if level >= 1:
        tips += HUD_TIPS["support"]
    if level >= 2:
        tips += HUD_TIPS["escalate"]
    return tips or HUD_TIPS["stable"]


# ----------------------------------------------------------------------------
# Check-in de bienestar WHO-5 (índice de bienestar de la OMS, 5 preguntas)
# ----------------------------------------------------------------------------
WHO5_ITEMS = [
    "Me he sentido alegre y de buen humor",
    "Me he sentido tranquilo y relajado",
    "Me he sentido activo y con energía",
    "Me he despertado sintiéndome fresco y descansado",
    "Mi vida diaria ha estado llena de cosas que me interesan",
]
WHO5_SCALE = ["En ningún momento", "Pocas veces", "Menos de la mitad del tiempo",
              "Más de la mitad del tiempo", "Casi todo el tiempo", "Todo el tiempo"]
WHO5_BANDS = {
    0: "Bienestar dentro de lo esperado.",
    1: "Bienestar reducido: conviene cuidarte y platicarlo con alguien.",
    2: "Bienestar muy bajo: se recomienda apoyo de tu equipo.",
}


def who5_score(answers):
    """answers: 5 enteros 0..5. Devuelve (crudo 0-25, porcentaje 0-100)."""
    raw = int(sum(answers))
    return raw, raw * 4


def who5_level(raw):
    """0 normal, 1 reducido (<13 crudo / <50 %), 2 muy bajo (<=7 crudo / <=28 %)."""
    return 2 if raw <= 7 else 1 if raw < 13 else 0


def combine(physio_level: int, who5_lvl):
    """Une señales y check-in. Devuelve (nivel_general, conviene_escalar)."""
    lvl = physio_level if who5_lvl is None else max(physio_level, who5_lvl)
    escalate = who5_lvl == 2 or (who5_lvl == 1 and physio_level == 2)
    return lvl, escalate


# ----------------------------------------------------------------------------
# Puente HUD de cámara -> consola web (archivo temporal, ~2 veces por segundo)
# ----------------------------------------------------------------------------
STATUS_PATH = Path(tempfile.gettempdir()) / "bioorbit_vision_status.json"


def write_vision_status(**data) -> None:
    try:
        data["ts"] = time.time()
        STATUS_PATH.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def read_vision_status(max_age: float = 5.0):
    """Último estado del HUD de cámara, o None si no está corriendo."""
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if time.time() - data.get("ts", 0) <= max_age else None
