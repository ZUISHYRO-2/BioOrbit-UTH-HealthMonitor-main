"""
Luma - asistente robot flotante de BioOrbit (diseño original del equipo).

Dos formas de dibujarlo, con el mismo aspecto y los mismos 5 estados de ánimo:
  - LumaSprite: lo dibuja con OpenCV dentro del HUD de la cámara (vision_monitor.py).
  - luma_html(): lienzo HTML/JS animado para la consola web (app.py).

Estados: reposo · curioso · preocupado · calma · hablando
"""

import math
import random

import cv2
import numpy as np

# color (hex) de ojos/brillo y forma de los ojos por estado (igual que el prototipo HTML)
MOODS = {
    "reposo":     {"col": "#5DCAA5", "ew": 15, "eh": 21, "lid": 0, "arc": 0, "fin": 0.1},
    "curioso":    {"col": "#85B7EB", "ew": 17, "eh": 25, "lid": 0, "arc": 0, "fin": 0.9},
    "preocupado": {"col": "#EF9F27", "ew": 15, "eh": 20, "lid": 1, "arc": 0, "fin": 1.2},
    "calma":      {"col": "#9FE1CB", "ew": 17, "eh": 20, "lid": 0, "arc": 1, "fin": 0.3},
    "hablando":   {"col": "#5DCAA5", "ew": 15, "eh": 21, "lid": 0, "arc": 0, "fin": 0.6},
}
SHAPE_KEYS = ("ew", "eh", "lid", "arc", "fin")


def _hex_rgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def _bgr(rgb):
    return (int(rgb[2]), int(rgb[1]), int(rgb[0]))


def pick_mood(level=0, breathing=False, emergency=False, talking=False, face=True):
    """Elige el ánimo de Luma según la situación del tripulante."""
    if emergency:
        return "preocupado"
    if breathing:
        return "calma"
    if level >= 2:
        return "preocupado"
    if talking:
        return "hablando"
    if level == 1 or not face:
        return "curioso"
    return "reposo"


# ------------------------------------------------------------------ OpenCV
BODY, BODY_DARK, EDGE = (234, 242, 240), (213, 228, 224), (184, 204, 199)   # RGB
VISOR, VISOR_EDGE = (14, 28, 34), (42, 64, 72)


class LumaSprite:
    """Animación de Luma para OpenCV. Llama draw(frame, ...) en cada cuadro."""

    def __init__(self):
        self.p = {k: float(MOODS["reposo"][k]) for k in SHAPE_KEYS}
        self.col = [float(v) for v in _hex_rgb(MOODS["reposo"]["col"])]
        self.t, self.blink, self.next_blink = 0.0, 0.0, 2.0
        self.look = [0.0, 0.0]

    def update(self, dt, mood, look=(0.0, 0.0)):
        dt = min(0.05, max(0.0, dt))
        self.t += dt
        k = min(1.0, dt * 5)
        tg = MOODS.get(mood, MOODS["reposo"])
        for key in SHAPE_KEYS:
            self.p[key] += (tg[key] - self.p[key]) * k
        tc = _hex_rgb(tg["col"])
        for i in range(3):
            self.col[i] += (tc[i] - self.col[i]) * k
        for i in range(2):
            self.look[i] += (max(-1.0, min(1.0, look[i])) - self.look[i]) * min(1.0, dt * 4)
        self.next_blink -= dt
        if self.next_blink <= 0:
            self.blink, self.next_blink = 0.15, 2.5 + random.random() * 2.5
        self.blink = max(0.0, self.blink - dt)

    # --- utilidades de dibujo (s = escala, (ox, oy) = origen local en el sprite)
    def draw(self, frame, cx, cy, s, mood, bpm=70.0):
        """Dibuja a Luma centrado en (cx, cy) con escala s (1.0 ≈ 230 px de alto)."""
        t, p = self.t, self.p
        col = _bgr(self.col)
        bob = math.sin(t * 1.6) * 8

        sw, sh = int(300 * s), int(310 * s)
        x0, y0 = int(cx - sw / 2), int(cy - 130 * s)
        fx0, fy0 = max(0, x0), max(0, y0)
        fx1, fy1 = min(frame.shape[1], x0 + sw), min(frame.shape[0], y0 + sh)
        if fx1 <= fx0 or fy1 <= fy0:
            return

        img = np.zeros((sh, sw, 3), np.uint8)
        alpha = np.zeros((sh, sw), np.uint8)
        glow = np.zeros((sh, sw, 3), np.uint8)
        ox, oy = sw / 2, 130 * s          # centro del cuerpo dentro del sprite
        by = oy + bob * s                  # centro con flotación

        def P(x, y, base_y=None):
            return (int(round(ox + x * s)), int(round((by if base_y is None else base_y) + y * s)))

        def A(a, b):
            return (max(1, int(round(a * s))), max(1, int(round(b * s))))

        def ell(c, ax, ang, a0, a1, color, th, a=255):
            cv2.ellipse(img, c, ax, ang, a0, a1, color, th, cv2.LINE_AA)
            cv2.ellipse(alpha, c, ax, ang, a0, a1, int(a), th, cv2.LINE_AA)

        def dashed(a0, a1, color, a):
            # órbita punteada animada: 40 px trazo / 24 px hueco, desplazándose
            ths = np.radians(np.linspace(a0, a1, 220))
            xs, ys = 130 * np.cos(ths), 40 + 26 * np.sin(ths)
            seg = np.hypot(np.diff(xs), np.diff(ys))
            L = np.concatenate([[0], np.cumsum(seg)])
            on = ((L + t * 30) % 64) < 40
            th = max(1, int(round(6 * s)))
            for i in range(len(xs) - 1):
                if on[i]:
                    p1, p2 = P(xs[i], ys[i]), P(xs[i + 1], ys[i + 1])
                    cv2.line(img, p1, p2, color, th, cv2.LINE_AA)
                    cv2.line(alpha, p1, p2, int(a), th, cv2.LINE_AA)

        # sombra (no flota)
        ell(P(0, 150, oy), A(70 - bob * 0.8, 10), 0, 0, 360, (0, 0, 0), -1, 90)
        # órbita trasera (tenue)
        dashed(180, 360, col, 90)
        # aletas
        for side in (-1, 1):
            ang = side * (0.35 + p["fin"] * 0.45 * math.sin(t * 3 + (1.5 if side > 0 else 0)))
            ccx, ccy = side * 100 - 18 * math.sin(ang), 20 + 18 * math.cos(ang)
            ell(P(ccx, ccy), A(13, 32), math.degrees(ang), 0, 360, _bgr(BODY_DARK), -1)
            ell(P(ccx, ccy), A(13, 32), math.degrees(ang), 0, 360, _bgr(EDGE), max(1, int(2 * s)))
        # cuerpo con sombreado
        body_mask = np.zeros_like(alpha)
        cv2.ellipse(body_mask, P(0, 0), A(92, 112), 0, 0, 360, 255, -1, cv2.LINE_AA)
        ell(P(0, 0), A(92, 112), 0, 0, 360, _bgr(BODY_DARK), -1)
        light = np.zeros_like(alpha)
        cv2.ellipse(light, P(-12, -14), A(90, 110), 0, 0, 360, 255, -1, cv2.LINE_AA)
        m = cv2.min(light, body_mask).astype(np.float32)[..., None] / 255.0
        img[:] = (img * (1 - m) + np.array(_bgr(BODY), np.float32) * m).astype(np.uint8)
        ell(P(0, 0), A(92, 112), 0, 0, 360, _bgr(EDGE), max(1, int(2 * s)))
        # brillo
        hl = np.zeros_like(alpha)
        cv2.ellipse(hl, P(-48, -70), A(12, 26), -28.6, 0, 360, 255, -1, cv2.LINE_AA)
        m = (hl.astype(np.float32) * 0.85 / 255.0)[..., None]
        img[:] = (img * (1 - m) + 255 * m).astype(np.uint8)
        # visor
        ell(P(0, -28), A(72, 50), 0, 0, 360, _bgr(VISOR), -1)
        ell(P(0, -28), A(72, 50), 0, 0, 360, _bgr(VISOR_EDGE), max(1, int(2 * s)))
        # ojos (miran hacia el rostro del tripulante)
        lx, ly = self.look[0] * 8, self.look[1] * 5
        bl = 0.12 if self.blink > 0 else 1.0
        # halo de neón: se pinta DEBAJO de los ojos (como shadowBlur del canvas)
        th_arc = max(2, int(7 * s))
        for ex0 in (-26, 26):
            ex, ey = ex0 + lx, -32 + ly
            if p["arc"] > 0.5:
                cv2.ellipse(glow, P(ex, ey + 8), A(13, 13), 0, 198, 342, col, th_arc + 2, cv2.LINE_AA)
            else:
                cv2.ellipse(glow, P(ex, ey), A(p["ew"] + 2, max(3, p["eh"] * bl + 2)), 0, 0, 360, col, -1, cv2.LINE_AA)
        if mood == "hablando":
            cv2.ellipse(glow, P(0, -4 + ly * 0.5), A(11, 3 + abs(math.sin(t * 10)) * 5), 0, 0, 360, col, -1, cv2.LINE_AA)
        glow = cv2.GaussianBlur(glow, (0, 0), max(1.0, 6 * s))
        img[:] = cv2.add(img, (glow * 0.9).astype(np.uint8))
        for ex0 in (-26, 26):
            ex, ey = ex0 + lx, -32 + ly
            if p["arc"] > 0.5:   # ojos felices (calma)
                ell(P(ex, ey + 8), A(13, 13), 0, 198, 342, col, th_arc)
            else:
                ell(P(ex, ey), A(p["ew"], max(2, p["eh"] * bl)), 0, 0, 360, col, -1)
            if p["lid"] > 0.3:   # párpado preocupado
                o = -1 if ex0 < 0 else 1
                tri = np.array([P(ex + o * 24, ey - 30), P(ex - o * 4, ey - 30), P(ex + o * 24, ey - 4)], np.int32)
                cv2.fillPoly(img, [tri], _bgr(VISOR), cv2.LINE_AA)
        # boca al hablar
        if mood == "hablando":
            ell(P(0, -4 + ly * 0.5), A(10, 2 + abs(math.sin(t * 10)) * 5), 0, 0, 360, col, -1)
        # corazón que late al ritmo del pulso
        beat = (t * (bpm or 70) / 60.0) % 1.0
        pulse = math.exp(-beat * 6)
        a = 0.55 + 0.45 * pulse
        heart = tuple(int(c * a + b * (1 - a)) for c, b in zip(col, _bgr(BODY)))
        ell(P(0, 70), A(6 + 3 * pulse, 6 + 3 * pulse), 0, 0, 360, heart, -1)
        # órbita delantera
        dashed(0, 180, col, 255)

        # composición sobre el cuadro
        sx0, sy0 = fx0 - x0, fy0 - y0
        sx1, sy1 = sx0 + (fx1 - fx0), sy0 + (fy1 - fy0)
        roi = frame[fy0:fy1, fx0:fx1]
        a3 = (alpha[sy0:sy1, sx0:sx1].astype(np.float32) / 255.0)[..., None]
        roi[:] = (roi * (1 - a3) + img[sy0:sy1, sx0:sx1] * a3).astype(np.uint8)


# ------------------------------------------------------------------ HTML (consola web)
def luma_html(mood="reposo", bpm=70, talk_s=0.0, height=300):
    """Lienzo animado de Luma. Solo recibe números y el nombre del ánimo (sin texto libre)."""
    mood = mood if mood in MOODS else "reposo"
    bpm = float(bpm) if bpm and bpm == bpm else 70.0
    return f"""
<style>html,body{{margin:0;background:transparent;overflow:hidden}}
#cv{{width:100%;height:{height}px;display:block;touch-action:none}}</style>
<canvas id="cv"></canvas>
<script>
const cv=document.getElementById('cv'),c=cv.getContext('2d');
const MOODS={{reposo:'#5DCAA5',curioso:'#85B7EB',preocupado:'#EF9F27',calma:'#9FE1CB',hablando:'#5DCAA5'}};
const PT={{reposo:{{ew:15,eh:21,lid:0,arc:0,fin:0.1}},curioso:{{ew:17,eh:25,lid:0,arc:0,fin:0.9}},
preocupado:{{ew:15,eh:20,lid:1,arc:0,fin:1.2}},calma:{{ew:17,eh:20,lid:0,arc:1,fin:0.3}},
hablando:{{ew:15,eh:21,lid:0,arc:0,fin:0.6}}}};
const BASE='{mood}', BPM={bpm:.1f};
let talk={max(0.0, float(talk_s)):.1f};
let st=talk>0&&BASE!=='preocupado'&&BASE!=='calma'?'hablando':BASE;
let t=0,mx=0,my=0,blink=0,nb=2,last=performance.now(),p={{...PT[st]}};
const hex=h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));
let col=hex(MOODS[st]);
const rgb=a=>'rgb('+a.map(Math.round).join(',')+')';
function fit(){{const r=window.devicePixelRatio||1;cv.width=cv.clientWidth*r;cv.height={height}*r;}}
fit();addEventListener('resize',fit);
cv.addEventListener('pointermove',e=>{{const r=cv.getBoundingClientRect();
mx=((e.clientX-r.left)/r.width-0.5)*2;my=((e.clientY-r.top)/r.height-0.5)*2;}});
cv.addEventListener('pointerleave',()=>{{mx=0;my=0;}});
function ch(cx,cy,s){{
  const colS=rgb(col),bob=Math.sin(t*1.6)*8;
  c.fillStyle='rgba(0,0,0,0.35)';c.beginPath();c.ellipse(cx,cy+150*s,(70-bob*0.8)*s,10*s,0,0,7);c.fill();
  c.save();c.translate(cx,cy+bob*s);c.scale(s,s);
  c.lineWidth=6;c.lineCap='round';c.strokeStyle=colS;c.setLineDash([40,24]);c.lineDashOffset=-t*30;
  c.globalAlpha=0.35;c.beginPath();c.ellipse(0,40,130,26,0,Math.PI,2*Math.PI);c.stroke();c.globalAlpha=1;c.setLineDash([]);
  [-1,1].forEach(side=>{{c.save();c.translate(side*100,20);
    c.rotate(side*(0.35+p.fin*0.45*Math.sin(t*3+(side>0?1.5:0))));
    c.fillStyle='#D5E4E0';c.strokeStyle='#B8CCC7';c.lineWidth=2;
    c.beginPath();c.ellipse(0,18,13,32,0,0,7);c.fill();c.stroke();c.restore();}});
  c.fillStyle='#EAF2F0';c.strokeStyle='#B8CCC7';c.lineWidth=2;
  c.beginPath();c.ellipse(0,0,92,112,0,0,7);c.fill();c.stroke();
  c.save();c.beginPath();c.ellipse(0,0,92,112,0,0,7);c.clip();
  c.fillStyle='#D5E4E0';c.fillRect(-100,-120,200,240);
  c.fillStyle='#EAF2F0';c.beginPath();c.ellipse(-12,-14,90,110,0,0,7);c.fill();c.restore();
  c.save();c.globalAlpha=0.85;c.fillStyle='#FFFFFF';c.beginPath();c.ellipse(-48,-70,12,26,-0.5,0,7);c.fill();c.restore();
  c.fillStyle='#0E1C22';c.strokeStyle='#2A4048';c.lineWidth=2;
  c.beginPath();c.ellipse(0,-28,72,50,0,0,7);c.fill();c.stroke();
  const lx=mx*8,ly=my*5,bl=blink>0?0.12:1;
  [-26,26].forEach(ex0=>{{const ex=ex0+lx,ey=-32+ly;
    c.save();c.shadowColor=colS;c.shadowBlur=14;c.fillStyle=colS;c.strokeStyle=colS;
    if(p.arc>0.5){{c.lineWidth=7;c.beginPath();c.arc(ex,ey+8,13,Math.PI*1.1,Math.PI*1.9);c.stroke();}}
    else{{c.beginPath();c.ellipse(ex,ey,p.ew,Math.max(2,p.eh*bl),0,0,7);c.fill();}}
    c.restore();
    if(p.lid>0.3){{const o=ex0<0?-1:1;c.fillStyle='#0E1C22';c.beginPath();
      c.moveTo(ex+o*24,ey-30);c.lineTo(ex-o*4,ey-30);c.lineTo(ex+o*24,ey-4);c.closePath();c.fill();}}}});
  if(st==='hablando'){{c.save();c.shadowColor=colS;c.shadowBlur=8;c.fillStyle=colS;
    c.beginPath();c.ellipse(0,-4+ly*0.5,10,2+Math.abs(Math.sin(t*10))*5,0,0,7);c.fill();c.restore();}}
  const beat=((t*BPM/60)%1),pulse=Math.exp(-beat*6);
  c.save();c.shadowColor=colS;c.shadowBlur=6+14*pulse;c.fillStyle=colS;
  c.globalAlpha=0.55+0.45*pulse;c.beginPath();c.arc(0,70,6+3*pulse,0,7);c.fill();c.restore();
  c.lineWidth=6;c.lineCap='round';c.strokeStyle=colS;c.setLineDash([40,24]);c.lineDashOffset=-t*30;
  c.beginPath();c.ellipse(0,40,130,26,0,0,Math.PI);c.stroke();c.setLineDash([]);c.restore();
}}
function frame(now){{
  const dt=Math.min(0.05,(now-last)/1000);last=now;t+=dt;
  if(talk>0){{talk-=dt;if(talk<=0)st=BASE;}}
  const k=Math.min(1,dt*5),tg=PT[st],tc=hex(MOODS[st]);
  for(const key in p)p[key]+=(tg[key]-p[key])*k;
  for(let i=0;i<3;i++)col[i]+=(tc[i]-col[i])*k;
  nb-=dt;if(nb<=0){{blink=0.15;nb=2.5+Math.random()*2.5;}}blink=Math.max(0,blink-dt);
  const r=window.devicePixelRatio||1,w=cv.width/r,h=cv.height/r;
  c.setTransform(r,0,0,r,0,0);c.clearRect(0,0,w,h);
  const s=Math.min(w/300,h/310)*0.95;ch(w/2,h*0.42,s);
  requestAnimationFrame(frame);
}}
requestAnimationFrame(frame);
</script>"""
