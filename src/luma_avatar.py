"""
Avatar animado Luma (ORBI) para el visor del casco (OpenCV HUD).
Estados: REPOSO | CURIOSO | PREOCUPADO | CALMA | HABLANDO
"""

import math
import cv2
import numpy as np

# Colores RGB -> BGR
PALETTES = {
    "REPOSO":     ((56, 225, 255), (139, 124, 255)),  # Cian y violeta
    "CURIOSO":    ((62, 240, 176), (56, 225, 255)),   # Verde menta y cian
    "PREOCUPADO": ((255, 77, 109), (255, 200, 87)),   # Rojo alerta y ámbar
    "CALMA":      ((139, 124, 255), (90, 180, 255)),  # Violeta suave y azul
    "HABLANDO":   ((56, 225, 255), (62, 240, 176)),   # Cian brillante y verde
}


def _bgr(c):
    return (int(c[2]), int(c[1]), int(c[0]))


def resolve_mood(status: str, em_phase: str, breath_active: bool, face_detected: bool, is_speaking: bool) -> str:
    """Determina automáticamente el estado de ánimo de Luma según la telemetría."""
    if em_phase in ("CONFIRMING", "SENT") or status != "OK":
        return "PREOCUPADO"
    if breath_active:
        return "CALMA"
    if is_speaking:
        return "HABLANDO"
    if face_detected:
        return "CURIOSO"
    return "REPOSO"


def draw_luma(frame, cx: int, cy: int, now: float, mood: str = "REPOSO", scale: float = 1.0):
    """Dibuja a Luma flotando en (cx, cy) con animación fluida y expresiones faciales."""
    primary, secondary = PALETTES.get(mood, PALETTES["REPOSO"])
    c1, c2 = _bgr(primary), _bgr(secondary)

    # Flotación vertical suave
    bob_speed = 4.5 if mood == "PREOCUPADO" else (1.8 if mood == "CALMA" else 2.8)
    bob_amp = 4 if mood == "PREOCUPADO" else 7
    fy = int(cy + math.sin(now * bob_speed) * bob_amp * scale)
    fx = int(cx + (math.sin(now * 18) * 2 if mood == "PREOCUPADO" else 0))

    r_outer = int(34 * scale)
    r_visor = int(25 * scale)

    # Halo exterior translúcido
    overlay = frame.copy()
    cv2.circle(overlay, (fx, fy), int(r_outer * 1.35), c2, -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)

    # Antena superior
    ant_y = fy - r_outer - int(10 * scale)
    cv2.line(frame, (fx, fy - r_outer + 2), (fx, ant_y), c1, 2, cv2.LINE_AA)
    pulse_r = int((4 + 1.5 * math.sin(now * 6)) * scale)
    cv2.circle(frame, (fx, ant_y), pulse_r, c1, -1, cv2.LINE_AA)

    # Cuerpo / Casco del robot
    cv2.circle(frame, (fx, fy), r_outer, (28, 34, 68), -1, cv2.LINE_AA)
    cv2.circle(frame, (fx, fy), r_outer, c1, 2, cv2.LINE_AA)

    # Orejas / propulsores laterales
    ear_w, ear_h = int(5 * scale), int(14 * scale)
    cv2.rectangle(frame, (fx - r_outer - ear_w, fy - ear_h // 2), (fx - r_outer, fy + ear_h // 2), c2, -1)
    cv2.rectangle(frame, (fx + r_outer, fy - ear_h // 2), (fx + r_outer + ear_w, fy + ear_h // 2), c2, -1)

    # Pantalla facial oscura
    cv2.ellipse(frame, (fx, fy + int(2 * scale)), (r_visor, int(r_visor * 0.78)), 0, 0, 360, (12, 16, 36), -1, cv2.LINE_AA)

    # Parpadeo periódico cada ~3.5 segundos
    blink = (now % 3.6) > 3.45 and mood not in ("PREOCUPADO", "CALMA")
    eye_dx = int(10 * scale)
    eye_y = fy - int(2 * scale)

    if blink:
        cv2.line(frame, (fx - eye_dx - 5, eye_y), (fx - eye_dx + 5, eye_y), c1, 2, cv2.LINE_AA)
        cv2.line(frame, (fx + eye_dx - 5, eye_y), (fx + eye_dx + 5, eye_y), c1, 2, cv2.LINE_AA)
    elif mood == "CALMA":
        # Ojos cerrados relajados (arcos hacia abajo)
        cv2.ellipse(frame, (fx - eye_dx, eye_y), (6, 4), 0, 0, 180, c1, 2, cv2.LINE_AA)
        cv2.ellipse(frame, (fx + eye_dx, eye_y), (6, 4), 0, 0, 180, c1, 2, cv2.LINE_AA)
    elif mood == "PREOCUPADO":
        # Ojos abiertos con cejas inclinadas
        cv2.circle(frame, (fx - eye_dx, eye_y + 1), int(4.5 * scale), c1, -1, cv2.LINE_AA)
        cv2.circle(frame, (fx + eye_dx, eye_y + 1), int(4.5 * scale), c1, -1, cv2.LINE_AA)
        cv2.line(frame, (fx - eye_dx - 6, eye_y - 4), (fx - eye_dx + 5, eye_y - 8), c1, 2, cv2.LINE_AA)
        cv2.line(frame, (fx + eye_dx - 5, eye_y - 8), (fx + eye_dx + 6, eye_y - 4), c1, 2, cv2.LINE_AA)
    elif mood == "CURIOSO":
        # Un ojo ligeramente más grande que el otro
        cv2.circle(frame, (fx - eye_dx, eye_y), int(5.5 * scale), c1, -1, cv2.LINE_AA)
        cv2.circle(frame, (fx + eye_dx, eye_y), int(3.8 * scale), c1, -1, cv2.LINE_AA)
    else:
        # REPOSO / HABLANDO: ojos brillantes estándar
        cv2.circle(frame, (fx - eye_dx, eye_y), int(4.5 * scale), c1, -1, cv2.LINE_AA)
        cv2.circle(frame, (fx + eye_dx, eye_y), int(4.5 * scale), c1, -1, cv2.LINE_AA)

    # Boca animada según el estado
    mouth_y = fy + int(10 * scale)
    if mood == "HABLANDO":
        h_mouth = int((2 + 4 * abs(math.sin(now * 14))) * scale)
        cv2.ellipse(frame, (fx, mouth_y), (int(6 * scale), h_mouth), 0, 0, 360, c1, -1, cv2.LINE_AA)
    elif mood == "PREOCUPADO":
        cv2.ellipse(frame, (fx, mouth_y + 3), (6, 4), 0, 180, 360, c1, 2, cv2.LINE_AA)
    elif mood in ("CURIOSO", "REPOSO"):
        cv2.ellipse(frame, (fx, mouth_y - 1), (6, 4), 0, 0, 180, c1, 2, cv2.LINE_AA)
