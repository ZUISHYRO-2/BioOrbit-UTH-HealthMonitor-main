"""
BioOrbit-UTH · HUD de cabina (cámara).

    python src/vision_monitor.py [índice_de_cámara] [ASTRO-01]

Qué es real y qué es simulado (el HUD lo indica en pantalla):
  - Pulso: estimación rPPG experimental con la cámara (canal verde de la frente + FFT).
  - Estabilidad de cabeza: movimiento del rostro detectado.
  - SpO2, temperatura, CO2, radiación: telemetría SIMULADA que viene del CSV (data_pipeline).
  - Alerta por pérdida de signos vitales: usa esa telemetría (tecla S para simularla).
  - ORBI: mensajes de acompañamiento; para conversar abre la consola (streamlit run src/app.py).

Teclas: S simular pérdida de signos vitales · C estoy bien · B respiración guiada · Q / Esc salir
"""

import math
import os
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import alerts
import companion
from data_pipeline import calculate_health_scores, load_telemetry

W, H = 1280, 720
DATA = Path(__file__).resolve().parent.parent / "data" / "sample_astronaut_telemetry.csv"
VITAL = ["heart_rate_bpm", "hrv_rmssd_ms", "spo2_pct"]

# Paleta (RGB). Para OpenCV se invierte a BGR.
CY, VI = (56, 225, 255), (139, 124, 255)
OK, WA, CR = (62, 240, 176), (255, 200, 87), (255, 77, 109)
TX, MU = (232, 241, 255), (143, 180, 217)
NAVY = (10, 14, 34)


def bgr(c):
    return (int(c[2]), int(c[1]), int(c[0]))


# ------------------------------------------------------------------ texto (PIL, con acentos)
_fonts = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        names = []
        try:
            import matplotlib
            names.append(os.path.join(matplotlib.get_data_path(), "fonts", "ttf",
                                      "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"))
        except Exception:  # noqa: BLE001
            pass
        names += ["segoeuib.ttf" if bold else "segoeui.ttf", "arialbd.ttf" if bold else "arial.ttf"]
        for n in names:
            try:
                _fonts[key] = ImageFont.truetype(n, size)
                break
            except OSError:
                continue
        else:
            _fonts[key] = ImageFont.load_default()
    return _fonts[key]


def wrap(text, size, max_w):
    f, lines, cur = font(size), [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def flush_text(frame, queue):
    img = Image.fromarray(np.ascontiguousarray(frame[:, :, ::-1]))
    d = ImageDraw.Draw(img)
    for x, y, s, size, color, bold, anchor in queue:
        d.text((x, y), s, font=font(size, bold), fill=color, anchor=anchor)
    frame[:] = np.asarray(img)[:, :, ::-1]


# ------------------------------------------------------------------ elementos gráficos
_masks = {}


def glass(frame, x, y, w, h, accent=CY, tint=NAVY, a=0.62, r=20, thick=1):
    """Panel de vidrio esmerilado con esquinas redondeadas."""
    key = (w, h, r)
    if key not in _masks:
        m = np.zeros((h, w), np.uint8)
        cv2.rectangle(m, (r, 0), (w - r - 1, h - 1), 255, -1)
        cv2.rectangle(m, (0, r), (w - 1, h - r - 1), 255, -1)
        for cx, cy in ((r, r), (w - r - 1, r), (r, h - r - 1), (w - r - 1, h - r - 1)):
            cv2.circle(m, (cx, cy), r, 255, -1)
        cnt = max(cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0], key=cv2.contourArea)
        _masks[key] = (m, cnt)
    mask, cnt = _masks[key]
    roi = frame[y:y + h, x:x + w]
    small = cv2.GaussianBlur(cv2.resize(roi, (w // 4, h // 4), interpolation=cv2.INTER_AREA), (0, 0), 2)
    blur = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    mixed = cv2.addWeighted(blur, 1 - a, np.full_like(roi, bgr(tint)), a, 0)
    cv2.copyTo(mixed, mask, roi)
    cv2.drawContours(roi, [cnt], -1, bgr(accent), thick, cv2.LINE_AA)
    cv2.line(roi, (r + 4, 1), (r + 46, 1), bgr(accent), 3, cv2.LINE_AA)


def brackets(frame, x, y, w, h, color, n=26):
    c = bgr(color)
    for (px, py, dx, dy) in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        cv2.line(frame, (px, py), (px + dx * n, py), c, 2, cv2.LINE_AA)
        cv2.line(frame, (px, py), (px, py + dy * n), c, 2, cv2.LINE_AA)


def ring(frame, cx, cy, r, frac, color):
    """Medidor circular de 270° con trazo de neón."""
    cv2.ellipse(frame, (cx, cy), (r, r), 0, 135, 405, (70, 60, 50), 7, cv2.LINE_AA)
    if frac > 0:
        end = 135 + 270 * min(1.0, frac)
        cv2.ellipse(frame, (cx, cy), (r, r), 0, 135, end, tuple(int(v * 0.45) for v in bgr(color)), 11, cv2.LINE_AA)
        cv2.ellipse(frame, (cx, cy), (r, r), 0, 135, end, bgr(color), 5, cv2.LINE_AA)


# ------------------------------------------------------------------ señales
class RPPG:
    """Pulso por fotopletismografía remota: ventana de 8 s, quita tendencia, FFT en 0.75-3 Hz."""

    def __init__(self, win_s=8.0):
        self.win, self.t, self.v = win_s, deque(), deque()

    def clear(self):
        self.t.clear()
        self.v.clear()

    def push(self, t, v):
        self.t.append(t)
        self.v.append(v)
        while self.t and t - self.t[0] > self.win:
            self.t.popleft()
            self.v.popleft()

    def estimate(self):
        if len(self.t) < 40 or self.t[-1] - self.t[0] < 5.0:
            return None, 0.0
        t, v = np.array(self.t), np.array(self.v)
        fs = (len(t) - 1) / (t[-1] - t[0])
        tu = np.arange(t[0], t[-1], 1.0 / fs)
        x = np.interp(tu, t, v)
        x = (x - np.polyval(np.polyfit(tu, x, 1), tu)) * np.hanning(len(tu))
        spec = np.abs(np.fft.rfft(x, n=8192))
        f = np.fft.rfftfreq(8192, 1.0 / fs)
        band = (f >= 0.75) & (f <= 3.0)
        s = spec[band]
        k = int(np.argmax(s))
        return float(f[band][k] * 60.0), float(s[k] / (np.median(s) + 1e-9))


_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml") \
    if hasattr(cv2, "CascadeClassifier") else None


def detect_face(frame):
    if _cascade is not None and not _cascade.empty():
        g = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), None, fx=0.5, fy=0.5)
        f = _cascade.detectMultiScale(g, 1.15, 5, minSize=(50, 50))
        if len(f):
            x, y, w, h = max(f, key=lambda b: b[2] * b[3])
            return (int(x * 2), int(y * 2), int(w * 2), int(h * 2))
        return None
    # Respaldo (OpenCV sin Haar): segmentación por color de piel, menos robusta.
    m = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb), (0, 133, 77), (255, 173, 127))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.dilate(cv2.erode(m, k), k, iterations=2)
    best = None
    for c in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, w, h = cv2.boundingRect(c)
        if cv2.contourArea(c) > 4000 and 0.75 < h / w < 2.4 and (best is None or w * h > best[2] * best[3]):
            best = (x, y, w, h)
    return best


# ------------------------------------------------------------------ estado
TIPS = [
    "Respira hondo: pulsa B para una guía de cuatro tiempos.",
    "Mira un punto lejano durante 20 segundos para descansar la vista.",
    "Estira cuello y hombros un minuto; tu cuerpo lo agradece.",
    "Si algo te pesa, háblalo con un compañero. No tienes que cargarlo solo.",
]


class State:
    def __init__(self, crew):
        self.crew = crew
        self.df = calculate_health_scores(load_telemetry(str(DATA)))
        self.df = self.df[self.df.crew_id == crew].reset_index(drop=True)
        self.i, self.last_tick, self.flat = 0, 0.0, False
        self.row = self.df.iloc[0].copy()
        self.status = "OK"
        self.em, self.sent = alerts.Emergency(), None
        self.rppg, self.bpm, self.q = RPPG(), None, 0.0
        self.wave, self.green_ema = deque(maxlen=220), None
        self.face, self.miss, self.cx = None, 99, deque(maxlen=60)
        self.breath, self.breath_t0 = False, 0.0
        self.msg, self.msg_t, self.msg_i = companion.greeting(crew, self.row), time.time(), 0
        self.fps = 30.0

    def tick(self, now):
        """Avanza la telemetría simulada una fila por segundo y evalúa la alerta."""
        if now - self.last_tick < 1.0:
            return
        self.last_tick, self.i = now, self.i + 1
        self.row = self.df.iloc[self.i % len(self.df)].copy()
        if self.flat:
            self.row[VITAL] = np.nan
        self.status = alerts.vitals_status(self.row)
        ev = alerts.step(self.em, self.status, now)
        if ev == "DUE":
            self.sent = alerts.broadcast("NO_VITALS", self.crew)
            self.em.phase = "SENT"
        elif ev == "RECOVERED":
            self.sent = None
        if now - self.msg_t > 12:
            hint = companion.body_hint(self.row)
            pool = TIPS + ([hint] if hint else [])
            self.msg, self.msg_t, self.msg_i = pool[self.msg_i % len(pool)], now, self.msg_i + 1

    def update(self, frame, now):
        face = detect_face(frame)
        if face is not None:
            self.miss = 0
            self.face = face if self.face is None else tuple(int(0.7 * a + 0.3 * b) for a, b in zip(self.face, face))
        else:
            self.miss += 1
            if self.miss > 8:
                self.face = None
                self.rppg.clear()
                self.bpm, self.q = None, 0.0
        if self.face is None:
            return
        fx, fy, fw, fh = self.face
        self.cx.append(fx + fw / 2)
        roi = frame[max(0, fy + int(fh * 0.12)):max(1, fy + int(fh * 0.32)),
                    max(0, fx + int(fw * 0.35)):max(1, fx + int(fw * 0.65))]
        if roi.size:
            g = float(roi[:, :, 1].mean())
            self.green_ema = g if self.green_ema is None else 0.98 * self.green_ema + 0.02 * g
            self.rppg.push(now, g)
            self.wave.append(g - self.green_ema)
            bpm, self.q = self.rppg.estimate()
            if bpm is not None and self.q > 3.0:
                self.bpm = bpm if self.bpm is None else 0.9 * self.bpm + 0.1 * bpm

    def stability(self):
        if len(self.cx) < 20:
            return "midiendo", MU
        s = float(np.std(self.cx))
        return ("Alta", OK) if s < 6 else (("Media", WA) if s < 18 else ("Baja", CR))


# ------------------------------------------------------------------ dibujo
def draw_hud(frame, S, now):
    T = []

    def text(x, y, s, size=14, color=TX, bold=False, anchor="ls"):
        T.append((x, y, s, size, color, bold, anchor))

    row = S.row
    level = {"NORMAL": ("Estable", OK), "PRECAUCIÓN": ("Precaución", WA), "CRÍTICO": ("Crítico", CR)}[row["alert_level"]]
    chip_txt, chip_col = level if S.status == "OK" else ("Sin señal", CR)

    # Rostro
    if S.face:
        fx, fy, fw, fh = S.face
        brackets(frame, fx, fy, fw, fh, CY)
        text(fx, min(H - 180, fy + fh + 24), "Rostro detectado", 13, CY)

    # Barra superior
    text(28, 48, "BioOrbit", 28, CY, True)
    text(184, 48, "UTH · NASA Space Apps 2026 · demostración", 13, MU)
    glass(frame, W - 310, 22, 286, 44, chip_col, a=0.7, r=22)
    cv2.circle(frame, (W - 286, 44), 6, bgr(chip_col), -1, cv2.LINE_AA)
    text(W - 270, 50, f"{S.crew} · {chip_txt}", 15, chip_col, True)

    # Panel izquierdo: pulso óptico
    glass(frame, 24, 90, 300, 330)
    text(44, 122, "Pulso óptico", 17, TX, True)
    text(44, 142, "rPPG experimental · cámara", 12, MU)
    cx, cy = 174, 238
    bpm = S.bpm
    ring(frame, cx, cy, 66, ((bpm - 40) / 100) if bpm else 0, OK if bpm and 55 <= bpm <= 100 else WA)
    text(cx, cy + 12, f"{bpm:.0f}" if bpm else "—", 44, TX, True, "ms")
    text(cx, cy + 40, "latidos / min" if bpm else ("midiendo…" if S.face else "sin rostro"), 12, MU, False, "ms")
    stab, scol = S.stability()
    text(44, 350, "Estabilidad de cabeza", 13, MU)
    text(280, 350, stab, 14, scol, True, "rs")
    text(44, 376, "Calidad de señal", 13, MU)
    q = min(1.0, S.q / 8.0)
    cv2.rectangle(frame, (180, 368), (280, 376), (70, 60, 50), -1)
    cv2.rectangle(frame, (180, 368), (180 + int(100 * q), 376), bgr(OK if q > 0.4 else WA), -1)
    text(44, 404, "Con buena luz y sin moverte mejora.", 11, MU)

    # Panel derecho: telemetría simulada
    glass(frame, W - 324, 90, 300, 330, VI)
    text(W - 304, 122, "Telemetría de cabina", 17, TX, True)
    text(W - 304, 142, "simulada · reproduce el CSV", 12, MU)
    items = [("SpO₂", row["spo2_pct"], "%", "{:.1f}", lambda v: v >= 96),
             ("Temperatura", row["body_temp_c"], "°C", "{:.1f}", lambda v: 36 <= v <= 37.5),
             ("CO₂ de cabina", row["cabin_co2_ppm"], "ppm", "{:,.0f}", lambda v: v < 4000),
             ("Radiación", row["radiation_rate_usv_h"], "µSv/h", "{:.0f}", lambda v: v < 35),
             ("HRV", row["hrv_rmssd_ms"], "ms", "{:.0f}", lambda v: v >= 40)]
    for k, (lab, v, unit, fmt, good) in enumerate(items):
        y = 190 + k * 46
        missing = v != v
        col = CR if missing else (OK if good(v) else WA)
        cv2.circle(frame, (W - 300, y - 6), 5, bgr(col), -1, cv2.LINE_AA)
        text(W - 286, y, lab, 14, MU)
        text(W - 48, y, "—" if missing else f"{fmt.format(v)} {unit}", 17, TX, True, "rs")

    # ORBI
    glass(frame, 24, H - 170, 430, 146, VI)
    ox, oy = 72, H - 97
    cv2.circle(frame, (ox, oy), 34, (120, 60, 40), -1, cv2.LINE_AA)
    cv2.circle(frame, (ox, oy), 28, bgr(VI), -1, cv2.LINE_AA)
    cv2.circle(frame, (ox, oy), 18, bgr(CY), -1, cv2.LINE_AA)
    cv2.circle(frame, (ox - 7, oy - 8), 6, (255, 255, 255), -1, cv2.LINE_AA)
    text(120, H - 140, "ORBI", 16, VI, True)
    for k, line in enumerate(wrap(S.msg, 13, 300)[:4]):
        text(120, H - 116 + k * 20, line, 13, TX)
    text(120, H - 38, "Para conversar abre la consola (streamlit)", 11, MU)

    # Señal rPPG
    glass(frame, 478, H - 170, W - 502, 146, CY)
    text(498, H - 142, "Señal rPPG (frente)", 15, TX, True)
    text(W - 44, H - 142, "S simular pérdida · C estoy bien · B respiración · Q salir", 11, MU, False, "rs")
    x0, x1, ym = 498, W - 44, H - 82
    if len(S.wave) > 10:
        a = np.convolve(np.array(S.wave), np.ones(3) / 3, mode="same")
        a = a / (np.abs(a).max() + 1e-6) * 40
        pts = np.stack([np.linspace(x0, x1, len(a)), ym - a], 1).astype(np.int32)
        cv2.polylines(frame, [pts], False, tuple(int(v * 0.4) for v in bgr(CY)), 6, cv2.LINE_AA)
        cv2.polylines(frame, [pts], False, bgr(CY), 2, cv2.LINE_AA)
    else:
        cv2.line(frame, (x0, ym), (x1, ym), (90, 80, 70), 1, cv2.LINE_AA)
        text((x0 + x1) // 2, ym - 6, "Esperando rostro…", 13, MU, False, "ms")

    # Respiración guiada
    if S.breath:
        t = (now - S.breath_t0) % 16
        ph, fr = int(t // 4), (t % 4) / 4
        sc = [0.5 + 0.5 * fr, 1.0, 1.0 - 0.5 * fr, 0.5][ph]
        bx, by = W - 174, 484
        cv2.circle(frame, (bx, by), int(52 * sc) + 5, tuple(int(v * 0.35) for v in bgr(CY)), -1, cv2.LINE_AA)
        cv2.circle(frame, (bx, by), int(52 * sc), bgr(CY), 2, cv2.LINE_AA)
        text(bx, by + 5, ["Inhala", "Sostén", "Exhala", "Sostén"][ph], 14, TX, True, "ms")

    # Banner de emergencia
    bx, bw = 350, W - 700
    if S.em.phase == "CONFIRMING":
        glass(frame, bx, 90, bw, 78, WA, tint=(48, 34, 6), a=0.8)
        text(bx + 22, 122, f"No detecto signos vitales de {S.crew}", 17, WA, True)
        text(bx + 22, 148, f"Aviso a tripulantes cercanos en {max(0, S.em.deadline - now):.0f} s · pulsa C si estás bien", 13, TX)
    elif S.em.phase == "SENT" and S.sent:
        pulse = 0.5 + 0.5 * math.sin(now * 6)
        glass(frame, bx, 90, bw, 96, tuple(int(v * (0.45 + 0.55 * pulse)) for v in CR), tint=(70, 8, 24), a=0.85, thick=3)
        text(bx + 22, 122, f"Alerta enviada a las {S.sent['when']}", 17, CR, True)
        who = ", ".join(f"{c} ({d:.0f} m)" for c, _, d in S.sent["notified"]) or "nadie dentro del radio"
        for k, ln in enumerate(wrap(f"Avisados: {who}", 13, bw - 44)[:2]):
            text(bx + 22, 148 + k * 20, ln, 13, TX)
    elif S.status == "SENSOR_FAULT":
        glass(frame, bx, 90, bw, 56, WA, tint=(48, 34, 6), a=0.8)
        text(bx + 22, 124, "Un sensor dejó de reportar. Revisa que esté bien colocado.", 14, WA, True)

    flush_text(frame, T)
    return frame


# ------------------------------------------------------------------ cámara y bucle
def open_camera():
    win = sys.platform.startswith("win")
    order = [int(sys.argv[1])] if len(sys.argv) > 1 and sys.argv[1].isdigit() else [1, 2, 0]
    for api in ([cv2.CAP_DSHOW, None] if win else [None]):
        for idx in order:
            cap = cv2.VideoCapture(idx, api) if api is not None else cv2.VideoCapture(idx)
            if cap.isOpened() and cap.read()[0]:
                return cap, idx
            cap.release()
    return None, -1


def main():
    crew = next((a for a in sys.argv[1:] if a.upper().startswith("ASTRO")), "ASTRO-01").upper()
    S = State(crew)
    cap, idx = open_camera()
    if cap is None:
        print("[BioOrbit HUD] ERROR: no se detectó ninguna cámara.")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    title = f"BioOrbit-UTH · cámara {idx}"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    prev = time.time()
    print(f"[BioOrbit HUD] Cámara {idx} lista. Teclas: S simular · C estoy bien · B respiración · Q salir")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        if frame.shape[1] != W or frame.shape[0] != H:
            frame = cv2.resize(frame, (W, H))
        now = time.time()
        S.fps = 0.9 * S.fps + 0.1 / max(now - prev, 1e-3)
        prev = now
        S.tick(now)
        S.update(frame, now)
        cv2.imshow(title, draw_hud(frame, S, now))
        k = cv2.waitKey(1) & 0xFF
        if k in (ord("q"), ord("Q"), 27):
            break
        if k in (ord("s"), ord("S")):
            S.flat = not S.flat
        elif k in (ord("c"), ord("C")):
            alerts.acknowledge(S.em, now)
        elif k in (ord("b"), ord("B")):
            S.breath, S.breath_t0 = not S.breath, now
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
