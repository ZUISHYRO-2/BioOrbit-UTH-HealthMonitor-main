"""
BioOrbit-UTH · HUD de cabina (cámara) con Luma.

    python src/vision_monitor.py [índice_de_cámara] [ASTRO-02] [--csv=data/demo_stress_arc.csv]

Qué es real y qué es simulado (el HUD lo indica en pantalla):
  - Rostro fijado: detector Haar de OpenCV con suavizado; la caja se queda "enclavada" en tu cara.
  - Pulso: estimación rPPG experimental con la cámara (canal verde de la frente + FFT).
  - Estabilidad de cabeza: movimiento del rostro detectado.
  - Reloj (Bluetooth LE): si hay un reloj conectado (consola web o watch_connect.py), la frecuencia
    cardíaca viene del reloj; si deja de mandar pulso, se dispara la alerta de signos vitales.
  - SpO2, temperatura, CO2, radiación, HRV: telemetría SIMULADA del CSV (data_pipeline).
  - Alerta por pérdida de signos vitales: usa esa telemetría (tecla S para simularla).
  - Luma: robot compañero; su ánimo cambia con tu estado y te mira. Para conversar: streamlit run src/app.py

Teclas: S simular pérdida · C estoy bien · B respiración · P pausa · A/D tiempo · N astronauta · Q salir
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
import ble_watch
import companion
from data_pipeline import calculate_health_scores, load_telemetry
from luma import LumaSprite, pick_mood

W, H = 1280, 720
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VITAL = ["heart_rate_bpm", "hrv_rmssd_ms", "spo2_pct"]
WINDOW = 12   # registros recientes (~6 h por astronauta) que analiza Luma

# Paleta (RGB). Para OpenCV se invierte a BGR.
CY, VI = (56, 225, 255), (139, 124, 255)
OK, WA, CR = (62, 240, 176), (255, 200, 87), (255, 77, 109)
TX, MU = (232, 241, 255), (143, 180, 217)
NAVY = (10, 14, 34)
LUMA_GREEN = (93, 202, 165)


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




# ------------------------------------------------------------------ rostro fijado
class FaceLock:
    """Detector Haar (dos modelos) + suavizado: la caja se queda fija en la cara.

    - Busca en la imagen reducida a 640 px y con histograma ecualizado (mejor con poca luz).
    - Descarta detecciones pegadas al borde y, al inicio, toma la cara más grande.
    - Ya fijada, sigue a esa misma cara (ignora falsos positivos de un instante) y suaviza la caja.
    - Tolera ~0.4 s sin detección antes de soltar el enlace.
    """

    def __init__(self):
        self.ok = hasattr(cv2, "CascadeClassifier")
        if self.ok:
            base = cv2.data.haarcascades
            self.main = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
            self.alt = cv2.CascadeClassifier(base + "haarcascade_frontalface_alt2.xml")
            self.ok = not self.main.empty()
        self.box, self.miss, self.away, self.t_lock = None, 99, 0, 0.0

    def _detect(self, frame):
        """Lista de candidatos (x, y, w, h) en coordenadas del cuadro."""
        h, w = frame.shape[:2]
        if not self.ok:
            b = detect_skin(frame)
            return [b] if b is not None else []
        scale = 640.0 / w if w > 640 else 1.0
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if scale != 1.0:
            g = cv2.resize(g, (int(w * scale), int(h * scale)))
        g = cv2.equalizeHist(g)
        side = max(60, int(g.shape[1] * 0.12))
        faces = self.main.detectMultiScale(g, 1.1, 6, minSize=(side, side))
        if len(faces) == 0 and not self.alt.empty():
            faces = self.alt.detectMultiScale(g, 1.1, 5, minSize=(side, side))
        sw, sh = g.shape[1], g.shape[0]
        return [tuple(v / scale for v in f) for f in faces
                if f[0] >= sw * 0.03 and f[1] >= sh * 0.03 and f[0] + f[2] <= sw * 0.97]

    @staticmethod
    def _dist(a, b):
        return math.hypot((a[0] + a[2] / 2) - (b[0] + b[2] / 2), (a[1] + a[3] / 2) - (b[1] + b[3] / 2))

    def update(self, frame, now):
        """Devuelve (caja o None, recién_fijado). Una vez fijada, la caja sigue a ESA cara:
        otras detecciones (falsos positivos, otra persona) solo la reemplazan si persisten ~0.5 s."""
        cands = self._detect(frame)
        fresh = False
        if self.box is None:
            if cands:
                self.box, self.t_lock, fresh = max(cands, key=lambda f: f[2] * f[3]), now, True
                self.miss, self.away = 0, 0
        else:
            near = [c for c in cands if self._dist(c, self.box) < self.box[2] * 0.6]
            if near:
                det = min(near, key=lambda c: self._dist(c, self.box))
                self.box = tuple(0.65 * o + 0.35 * n for o, n in zip(self.box, det))
                self.miss, self.away = 0, 0
            else:
                self.miss += 1
                self.away = self.away + 1 if cands else 0
                if self.away > 15:      # la cara se movió de verdad (o es otra persona)
                    self.box, self.t_lock, fresh = max(cands, key=lambda f: f[2] * f[3]), now, True
                    self.miss, self.away = 0, 0
                elif self.miss > 12:    # ~0.4 s sin verla: se suelta el enlace
                    self.box = None
        if self.box is None:
            return None, False
        h, w = frame.shape[:2]
        x, y, bw, bh = [int(v) for v in self.box]
        x, y = max(0, x), max(0, y)
        bw, bh = min(bw, w - x), min(bh, h - y)
        return ((x, y, bw, bh) if bw > 20 and bh > 20 else None), fresh


def detect_skin(frame):
    """Respaldo si tu OpenCV no trae Haar: segmentación por color de piel (menos robusta)."""
    m = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb), (0, 133, 77), (255, 173, 127))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.dilate(cv2.erode(m, k), k, iterations=2)
    best = None
    for c in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, w, h = cv2.boundingRect(c)
        if cv2.contourArea(c) > 4000 and 0.75 < h / w < 2.4 and (best is None or w * h > best[2] * best[3]):
            best = (x, y, w, h)
    return best


def draw_lock(frame, box, color, now, t_lock, label, text):
    """Retícula de fijación: esquinas que se cierran sobre la cara, anillo giratorio y barrido."""
    fx, fy, fw, fh = box
    k = min(1.0, (now - t_lock) / 0.45)
    ease = 1 - (1 - k) ** 3
    grow = int((1 - ease) * fw * 0.45)
    brackets(frame, fx - grow, fy - grow, fw + 2 * grow, fh + 2 * grow, color, n=int(22 + 10 * (1 - ease)))
    cx, cy = fx + fw // 2, fy + int(fh * 0.48)
    r = int(fw * 0.66)
    c = bgr(color)
    dim = tuple(int(v * 0.45) for v in c)
    cv2.circle(frame, (cx, cy), r, dim, 1, cv2.LINE_AA)
    ang = now * 1.6
    for i in range(4):
        a = ang + i * math.pi / 2
        p1 = (int(cx + (r - 7) * math.cos(a)), int(cy + (r - 7) * math.sin(a)))
        p2 = (int(cx + (r + 7) * math.cos(a)), int(cy + (r + 7) * math.sin(a)))
        cv2.line(frame, p1, p2, c, 2, cv2.LINE_AA)
    # barrido suave de arriba a abajo
    sy = fy + int((0.5 + 0.5 * math.sin(now * 2.2)) * fh)
    ov = frame.copy()
    cv2.line(ov, (fx + 6, sy), (fx + fw - 6, sy), c, 2, cv2.LINE_AA)
    cv2.addWeighted(ov, 0.45, frame, 0.55, 0, frame)
    ly = min(H - 206, max(fy + fh + grow, cy + r) + 24)
    text(fx + fw // 2, ly, "Fijando rostro…" if k < 1 else label, 14, color, True, "ms")


# ------------------------------------------------------------------ estado
def find_csv():
    arg = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--csv=")), None)
    if arg:
        return Path(arg)
    for name in ("demo_stress_arc.csv", "sample_astronaut_telemetry.csv"):
        if (DATA_DIR / name).exists():
            return DATA_DIR / name
    raise FileNotFoundError("No hay CSV de telemetría en data/")


class State:
    def __init__(self, crew):
        csv = find_csv()
        self.csv_name = csv.name
        self.all = calculate_health_scores(load_telemetry(str(csv))).sort_values("timestamp")
        self.crews = sorted(self.all.crew_id.unique())
        self.flat = False
        if crew not in self.crews:
            crew = "ASTRO-02" if "ASTRO-02" in self.crews else self.crews[0]
        self.set_crew(crew)
        self.playing, self.last_tick = True, 0.0
        self.em, self.sent = alerts.Emergency(), None
        self.rppg, self.bpm, self.q = RPPG(), None, 0.0
        self.wave, self.green_ema = deque(maxlen=220), None
        self.lock, self.face, self.cx = FaceLock(), None, deque(maxlen=60)
        self.breath, self.breath_t0 = False, 0.0
        self.luma, self.mood = LumaSprite(), "reposo"
        self.msg, self.msg_t, self.msg_i, self.msg_key, self.talk_until = "", 0.0, 0, None, 0.0
        self.fps, self.last_status = 30.0, 0.0
        print(f"[BioOrbit HUD] Telemetría simulada: {self.csv_name} · {self.crew}")

    def set_crew(self, crew):
        self.crew = crew
        self.df = self.all[self.all.crew_id == crew].reset_index(drop=True)
        self.i = 0
        self.refresh()

    def refresh(self):
        self.watch, self.watch_data = ble_watch.watch_state()
        self.row = ble_watch.apply_watch(self.df.iloc[self.i], self.watch, self.watch_data)
        win = self.df.iloc[max(0, self.i - WINDOW + 1): self.i + 1].copy()
        if self.flat:
            self.row[VITAL] = np.nan
        self.physio = companion.physio_state(win)
        self.status = alerts.vitals_status(self.row)

    def tick(self, now):
        """Avanza la telemetría simulada una fila por segundo y evalúa la alerta."""
        if now - self.last_tick < 1.0:
            return
        self.last_tick = now
        if self.playing:
            self.i = (self.i + 1) % len(self.df)
        self.refresh()
        ev = alerts.step(self.em, self.status, now)
        if ev == "DUE":
            self.sent = alerts.broadcast("NO_VITALS", self.crew)
            self.em.phase = "SENT"
        elif ev == "RECOVERED":
            self.sent = None

    def update(self, frame, now):
        face, fresh = self.lock.update(frame, now)
        self.face = face
        if face is None:
            if self.lock.box is None:
                self.rppg.clear()
                self.bpm, self.q = None, 0.0
            return
        if fresh:
            self.rppg.clear()
        fx, fy, fw, fh = face
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
        if len(self.cx) < 20 or self.face is None:
            return "midiendo", MU
        s = float(np.std(self.cx))
        return ("Alta", OK) if s < 6 else (("Media", WA) if s < 18 else ("Baja", CR))

    def companion_step(self, now):
        """Elige qué dice Luma y con qué ánimo."""
        lvl, reasons = self.physio["level"], self.physio["reasons"]
        emergency = self.em.phase in ("CONFIRMING", "SENT")
        unsteady = self.stability()[0] == "Baja"
        key = (lvl, tuple(reasons), self.em.phase, self.breath, unsteady)
        if self.em.phase == "CONFIRMING":
            pool = [f"{self.crew}, ¿me escuchas? No recibo tus signos vitales. Pulsa C si estás bien."]
        elif self.em.phase == "SENT":
            pool = ["Ya avisé a la tripulación cercana. La ayuda va en camino; me quedo contigo."]
        elif self.breath:
            pool = ["Inhala conmigo… sostén… exhala despacio. Lo estás haciendo bien."]
        else:
            pool = companion.hud_tips(lvl, reasons, unsteady)
            hint = companion.body_hint(self.row)
            if hint and lvl >= 1:
                pool = pool + [hint]
        if key != self.msg_key:
            self.msg_key, self.msg_i = key, 0
            self.msg, self.msg_t, self.talk_until = pool[0], now, now + 3.0
        elif now - self.msg_t > 10:
            self.msg_i += 1
            self.msg, self.msg_t, self.talk_until = pool[self.msg_i % len(pool)], now, now + 3.0
        self.mood = pick_mood(lvl, self.breath, emergency or self.status == "NO_VITALS",
                              now < self.talk_until, self.face is not None)

    def publish(self, now):
        """Comparte el estado con la consola web (streamlit) dos veces por segundo."""
        if now - self.last_status < 0.5:
            return
        self.last_status = now
        companion.write_vision_status(
            crew=self.crew, face_locked=self.face is not None,
            bpm=round(self.bpm, 1) if self.bpm else None, quality=round(self.q, 1),
            stability=self.stability()[0], mood=self.mood, level=self.physio["level"], watch=self.watch)


# ------------------------------------------------------------------ dibujo
LUMA_POS = (106, H - 112)


def draw_hud(frame, S, now, dt):
    T = []

    def text(x, y, s, size=14, color=TX, bold=False, anchor="ls"):
        T.append((x, y, s, size, color, bold, anchor))

    row = S.row
    lvl = S.physio["level"]
    level = {"NORMAL": ("Estable", OK), "PRECAUCIÓN": ("Precaución", WA), "CRÍTICO": ("Crítico", CR)}[row["alert_level"]]
    chip_txt, chip_col = level if S.status == "OK" else ("Sin señal", CR)
    lock_col = CR if S.status != "OK" or lvl >= 2 else (WA if lvl == 1 else CY)

    # Rostro fijado
    if S.face:
        draw_lock(frame, S.face, lock_col, now, S.lock.t_lock, f"{S.crew} · rostro fijado", text)
    else:
        cx, cy = W // 2, (90 + H - 196) // 2
        a = 0.5 + 0.5 * math.sin(now * 3)
        brackets(frame, cx - 110, cy - 130, 220, 260, tuple(int(v * (0.4 + 0.4 * a)) for v in MU), n=30)
        text(cx, cy + 156, "Buscando rostro…", 15, MU, True, "ms")

    # Barra superior
    text(28, 48, "BioOrbit", 28, CY, True)
    text(184, 48, f"UTH · NASA Space Apps 2026 · demostración · {S.csv_name}", 13, MU)
    glass(frame, W - 310, 22, 286, 44, chip_col, a=0.7, r=22)
    cv2.circle(frame, (W - 286, 44), 6, bgr(chip_col), -1, cv2.LINE_AA)
    text(W - 270, 50, f"{S.crew} · {chip_txt}", 15, chip_col, True)
    if not S.playing:
        text(W - 324, 50, "⏸ pausa", 13, WA, True, "rs")

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
    if S.watch == "live":
        dev = (S.watch_data or {}).get("device_name", "reloj")
        text(W - 304, 142, f"FC del reloj ({dev[:18]}) · resto simulado", 12, OK)
    elif S.watch == "lost":
        text(W - 304, 142, "Reloj sin señal de pulso", 12, CR, True)
    else:
        text(W - 304, 142, f"simulada · {row['timestamp']:%d %b %H:%M}", 12, MU)
    hr_lab = "Frec. cardíaca (reloj)" if S.watch == "live" else "Frec. cardíaca"
    items = [(hr_lab, row["heart_rate_bpm"], "bpm", "{:.0f}", lambda v: 55 <= v <= 100),
             ("SpO₂", row["spo2_pct"], "%", "{:.1f}", lambda v: v >= 96),
             ("Temperatura", row["body_temp_c"], "°C", "{:.1f}", lambda v: 36 <= v <= 37.5),
             ("CO₂ de cabina", row["cabin_co2_ppm"], "ppm", "{:,.0f}", lambda v: v < 4000),
             ("Radiación", row["radiation_rate_usv_h"], "µSv/h", "{:.0f}", lambda v: v < 35),
             ("HRV", row["hrv_rmssd_ms"], "ms", "{:.0f}", lambda v: v >= 40),
             ("Sueño (eficiencia)", row["sleep_efficiency_pct"], "%", "{:.0f}", lambda v: v >= 80)]
    for k, (lab, v, unit, fmt, good) in enumerate(items):
        y = 180 + k * 34
        missing = v != v
        col = CR if missing else (OK if good(v) else WA)
        cv2.circle(frame, (W - 300, y - 6), 5, bgr(col), -1, cv2.LINE_AA)
        text(W - 286, y, lab, 14, MU)
        text(W - 48, y, "—" if missing else f"{fmt.format(v)} {unit}", 17, TX, True, "rs")

    # Luma: tarjeta del compañero
    mood_col = {"preocupado": WA, "calma": (159, 225, 203), "curioso": (133, 183, 235)}.get(S.mood, LUMA_GREEN)
    glass(frame, 24, H - 196, 430, 172, mood_col)
    lx, ly = LUMA_POS
    if S.face:
        fx, fy, fw, fh = S.face
        look = ((fx + fw / 2 - lx) / 500.0, (fy + fh / 2 - ly) / 300.0)
    else:
        look = (math.sin(now * 0.7) * 0.7, math.sin(now * 0.45) * 0.3)
    S.luma.update(dt, S.mood, look)
    hr_row = row["heart_rate_bpm"] if row["heart_rate_bpm"] == row["heart_rate_bpm"] else None
    heart = hr_row if S.watch == "live" else (S.bpm or hr_row or 70)
    S.luma.draw(frame, lx, ly, 0.5, S.mood, heart)
    estado = {0: "estable", 1: "desgaste leve", 2: "desgaste alto"}[lvl]
    text(190, H - 166, "Luma", 18, mood_col, True)
    text(240, H - 166, f"· {S.mood} · {estado}", 12, MU)
    for k, line in enumerate(wrap(S.msg, 14, 250)[:4]):
        text(190, H - 140 + k * 21, line, 14, TX)
    text(190, H - 36, "Para platicar con Luma: streamlit run src/app.py", 11, MU)

    # Señal rPPG
    glass(frame, 478, H - 196, W - 502, 172, CY)
    text(498, H - 166, "Señal rPPG (frente)", 15, TX, True)
    text(W - 44, H - 166, "S pérdida · C estoy bien · B respiración · P pausa · A/D tiempo · N astronauta · Q salir",
         11, MU, False, "rs")
    x0, x1, ym = 498, W - 44, H - 98
    if len(S.wave) > 10 and S.face:
        a = np.convolve(np.array(S.wave), np.ones(3) / 3, mode="same")
        a = a / (np.abs(a).max() + 1e-6) * 44
        pts = np.stack([np.linspace(x0, x1, len(a)), ym - a], 1).astype(np.int32)
        cv2.polylines(frame, [pts], False, tuple(int(v * 0.4) for v in bgr(CY)), 6, cv2.LINE_AA)
        cv2.polylines(frame, [pts], False, bgr(CY), 2, cv2.LINE_AA)
    else:
        cv2.line(frame, (x0, ym), (x1, ym), (90, 80, 70), 1, cv2.LINE_AA)
        text((x0 + x1) // 2, ym - 6, "Esperando rostro…", 13, MU, False, "ms")

    # Respiración guiada (alrededor de la zona central inferior)
    if S.breath:
        t = (now - S.breath_t0) % 16
        ph, fr = int(t // 4), (t % 4) / 4
        sc = [0.5 + 0.5 * fr, 1.0, 1.0 - 0.5 * fr, 0.5][ph]
        bx, by = W - 174, 476
        cv2.circle(frame, (bx, by), int(44 * sc) + 5, tuple(int(v * 0.35) for v in bgr(CY)), -1, cv2.LINE_AA)
        cv2.circle(frame, (bx, by), int(44 * sc), bgr(CY), 2, cv2.LINE_AA)
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
    crew = next((a for a in sys.argv[1:] if a.upper().startswith("ASTRO")), "").upper()
    S = State(crew)
    cap, idx = open_camera()
    if cap is None:
        print("[BioOrbit HUD] ERROR: no se detectó ninguna cámara.")
        return
    if not S.lock.ok:
        print("[BioOrbit HUD] Aviso: tu OpenCV no trae el detector Haar; uso color de piel (menos preciso).")
        print("               Recomendado:  pip install \"opencv-python>=4.8,<5\"")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    title = f"BioOrbit-UTH · cámara {idx}"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    prev = time.time()
    print(f"[BioOrbit HUD] Cámara {idx} lista. Teclas: S pérdida · C estoy bien · B respiración · "
          "P pausa · A/D tiempo · N astronauta · Q salir")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        if frame.shape[1] != W or frame.shape[0] != H:
            frame = cv2.resize(frame, (W, H))
        now = time.time()
        dt = max(now - prev, 1e-3)
        S.fps = 0.9 * S.fps + 0.1 / dt
        prev = now
        S.tick(now)
        S.update(frame, now)
        S.companion_step(now)
        S.publish(now)
        cv2.imshow(title, draw_hud(frame, S, now, dt))
        k = cv2.waitKey(1) & 0xFF
        if k in (ord("q"), ord("Q"), 27):
            break
        if k in (ord("s"), ord("S")):
            S.flat = not S.flat
            S.refresh()
        elif k in (ord("c"), ord("C")):
            alerts.acknowledge(S.em, now)
        elif k in (ord("b"), ord("B")):
            S.breath, S.breath_t0 = not S.breath, now
        elif k in (ord("p"), ord("P")):
            S.playing = not S.playing
        elif k in (ord("d"), ord("D")):
            S.i = min(S.i + 5, len(S.df) - 1)
            S.refresh()
        elif k in (ord("a"), ord("A")):
            S.i = max(S.i - 5, 0)
            S.refresh()
        elif k in (ord("n"), ord("N")):
            S.set_crew(S.crews[(S.crews.index(S.crew) + 1) % len(S.crews)])
            S.em, S.sent = alerts.Emergency(), None
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
