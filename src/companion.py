"""
ORBI - compañero virtual de apoyo emocional para la tripulación.

Funciona sin internet con reglas empáticas. Si defines ANTHROPIC_API_KEY, usa un modelo
de lenguaje para conversar con más naturalidad (se envían al servicio el texto del chat y
un resumen de biometría, así que actívalo solo con consentimiento de la persona).
Si ocurre cualquier error de red, vuelve automáticamente a las reglas.

ORBI es un acompañante, no un profesional de salud mental: no diagnostica y, ante señales
de crisis, pide apoyo humano de inmediato.
"""

import os
import random
import re
from dataclasses import dataclass

import pandas as pd

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
    "Eres ORBI, un compañero virtual amistoso para tripulantes de misiones espaciales. Hablas en español, "
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
    base = f"¡Hola, {who}! Soy ORBI, tu compañero a bordo. Puedes contarme cómo te sientes cuando quieras."
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
