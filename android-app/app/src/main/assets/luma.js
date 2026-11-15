/* Luma — robot compañero de BioOrbit (diseño original del equipo).
   5 estados: reposo · curioso · preocupado · calma · hablando */
(function () {
  const MOODS = { reposo: '#5DCAA5', curioso: '#85B7EB', preocupado: '#EF9F27', calma: '#9FE1CB', hablando: '#5DCAA5' };
  const PT = {
    reposo: { ew: 15, eh: 21, lid: 0, arc: 0, fin: 0.1 },
    curioso: { ew: 17, eh: 25, lid: 0, arc: 0, fin: 0.9 },
    preocupado: { ew: 15, eh: 20, lid: 1, arc: 0, fin: 1.2 },
    calma: { ew: 17, eh: 20, lid: 0, arc: 1, fin: 0.3 },
    hablando: { ew: 15, eh: 21, lid: 0, arc: 0, fin: 0.6 },
  };
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const rgb = a => 'rgb(' + a.map(Math.round).join(',') + ')';

  function pickMood({ level = 0, breathing = false, emergency = false, talking = false, face = true } = {}) {
    if (emergency) return 'preocupado';
    if (breathing) return 'calma';
    if (level >= 2) return 'preocupado';
    if (talking) return 'hablando';
    if (level === 1 || !face) return 'curioso';
    return 'reposo';
  }

  class LumaView {
    constructor(canvas) {
      this.cv = canvas; this.c = canvas.getContext('2d');
      this.base = 'reposo'; this.talkUntil = 0; this.bpm = 70;
      this.t = 0; this.blink = 0; this.nb = 2; this.last = performance.now();
      this.look = [0, 0]; this.lookT = [0, 0]; this.p = { ...PT.reposo }; this.col = hex(MOODS.reposo);
      this.visible = true; this.lastDraw = 0;
      this.fit(); addEventListener('resize', () => this.fit());
      // solo se dibuja cuando está en pantalla (ahorra batería y CPU)
      if ('IntersectionObserver' in window) {
        new IntersectionObserver(es => { this.visible = es[0].isIntersecting; }).observe(canvas);
      }
      canvas.addEventListener('pointermove', e => {
        const r = canvas.getBoundingClientRect();
        this.lookT = [((e.clientX - r.left) / r.width - 0.5) * 2, ((e.clientY - r.top) / r.height - 0.5) * 2];
      });
      requestAnimationFrame(n => this.frame(n));
    }
    fit() {
      const r = Math.min(devicePixelRatio || 1, 2);
      this.cv.width = Math.max(1, this.cv.clientWidth * r); this.cv.height = Math.max(1, this.cv.clientHeight * r);
    }
    setMood(m) { this.base = PT[m] ? m : 'reposo'; }
    talk(sec = 3) { this.talkUntil = performance.now() + sec * 1000; }
    setLook(x, y) { this.lookT = [Math.max(-1, Math.min(1, x)), Math.max(-1, Math.min(1, y))]; }
    get mood() {
      const talking = performance.now() < this.talkUntil;
      return talking && this.base !== 'preocupado' && this.base !== 'calma' ? 'hablando' : this.base;
    }
    draw(cx, cy, s) {
      const c = this.c, p = this.p, t = this.t, st = this.mood;
      const colS = rgb(this.col), bob = Math.sin(t * 1.6) * 8;
      c.fillStyle = 'rgba(0,0,0,0.35)'; c.beginPath(); c.ellipse(cx, cy + 150 * s, (70 - bob * 0.8) * s, 10 * s, 0, 0, 7); c.fill();
      c.save(); c.translate(cx, cy + bob * s); c.scale(s, s);
      c.lineWidth = 6; c.lineCap = 'round'; c.strokeStyle = colS; c.setLineDash([40, 24]); c.lineDashOffset = -t * 30;
      c.globalAlpha = 0.35; c.beginPath(); c.ellipse(0, 40, 130, 26, 0, Math.PI, 2 * Math.PI); c.stroke(); c.globalAlpha = 1; c.setLineDash([]);
      [-1, 1].forEach(side => {
        c.save(); c.translate(side * 100, 20);
        c.rotate(side * (0.35 + p.fin * 0.45 * Math.sin(t * 3 + (side > 0 ? 1.5 : 0))));
        c.fillStyle = '#D5E4E0'; c.strokeStyle = '#B8CCC7'; c.lineWidth = 2;
        c.beginPath(); c.ellipse(0, 18, 13, 32, 0, 0, 7); c.fill(); c.stroke(); c.restore();
      });
      c.fillStyle = '#EAF2F0'; c.strokeStyle = '#B8CCC7'; c.lineWidth = 2;
      c.beginPath(); c.ellipse(0, 0, 92, 112, 0, 0, 7); c.fill(); c.stroke();
      c.save(); c.beginPath(); c.ellipse(0, 0, 92, 112, 0, 0, 7); c.clip();
      c.fillStyle = '#D5E4E0'; c.fillRect(-100, -120, 200, 240);
      c.fillStyle = '#EAF2F0'; c.beginPath(); c.ellipse(-12, -14, 90, 110, 0, 0, 7); c.fill(); c.restore();
      c.save(); c.globalAlpha = 0.85; c.fillStyle = '#FFFFFF'; c.beginPath(); c.ellipse(-48, -70, 12, 26, -0.5, 0, 7); c.fill(); c.restore();
      c.fillStyle = '#0E1C22'; c.strokeStyle = '#2A4048'; c.lineWidth = 2;
      c.beginPath(); c.ellipse(0, -28, 72, 50, 0, 0, 7); c.fill(); c.stroke();
      const lx = this.look[0] * 8, ly = this.look[1] * 5, bl = this.blink > 0 ? 0.12 : 1;
      [-26, 26].forEach(ex0 => {
        const ex = ex0 + lx, ey = -32 + ly;
        c.save(); c.fillStyle = colS; c.strokeStyle = colS;
        if (p.arc > 0.5) {
          c.globalAlpha = 0.22; c.lineWidth = 15; c.beginPath(); c.arc(ex, ey + 8, 13, Math.PI * 1.1, Math.PI * 1.9); c.stroke();
          c.globalAlpha = 1; c.lineWidth = 7; c.beginPath(); c.arc(ex, ey + 8, 13, Math.PI * 1.1, Math.PI * 1.9); c.stroke();
        } else {
          const eh = Math.max(2, p.eh * bl);
          c.globalAlpha = 0.18; c.beginPath(); c.ellipse(ex, ey, p.ew + 7, eh + 7, 0, 0, 7); c.fill();
          c.globalAlpha = 1; c.beginPath(); c.ellipse(ex, ey, p.ew, eh, 0, 0, 7); c.fill();
        }
        c.restore();
        if (p.lid > 0.3) {
          const o = ex0 < 0 ? -1 : 1; c.fillStyle = '#0E1C22'; c.beginPath();
          c.moveTo(ex + o * 24, ey - 30); c.lineTo(ex - o * 4, ey - 30); c.lineTo(ex + o * 24, ey - 4); c.closePath(); c.fill();
        }
      });
      if (st === 'hablando') {
        c.save(); c.fillStyle = colS;
        c.beginPath(); c.ellipse(0, -4 + ly * 0.5, 10, 2 + Math.abs(Math.sin(t * 10)) * 5, 0, 0, 7); c.fill(); c.restore();
      }
      const beat = (t * (this.bpm || 70) / 60) % 1, pulse = Math.exp(-beat * 6);
      c.save(); c.fillStyle = colS;
      c.globalAlpha = 0.25 * pulse; c.beginPath(); c.arc(0, 70, 12 + 8 * pulse, 0, 7); c.fill();
      c.globalAlpha = 0.55 + 0.45 * pulse; c.beginPath(); c.arc(0, 70, 6 + 3 * pulse, 0, 7); c.fill(); c.restore();
      c.lineWidth = 6; c.lineCap = 'round'; c.strokeStyle = colS; c.setLineDash([40, 24]); c.lineDashOffset = -t * 30;
      c.beginPath(); c.ellipse(0, 40, 130, 26, 0, 0, Math.PI); c.stroke(); c.setLineDash([]); c.restore();
    }
    frame(now) {
      const dt = Math.min(0.05, (now - this.last) / 1000); this.last = now; this.t += dt;
      const st = this.mood, k = Math.min(1, dt * 5), tg = PT[st], tc = hex(MOODS[st]);
      for (const key in this.p) this.p[key] += (tg[key] - this.p[key]) * k;
      for (let i = 0; i < 3; i++) this.col[i] += (tc[i] - this.col[i]) * k;
      for (let i = 0; i < 2; i++) this.look[i] += (this.lookT[i] - this.look[i]) * Math.min(1, dt * 4);
      this.nb -= dt; if (this.nb <= 0) { this.blink = 0.15; this.nb = 2.5 + Math.random() * 2.5; }
      this.blink = Math.max(0, this.blink - dt);
      // 30 cuadros por segundo bastan para la animación (los teléfonos piden 60-120)
      if (this.visible && this.cv.offsetParent !== null && !document.hidden && now - this.lastDraw >= 32) {
        this.lastDraw = now;
        const r = Math.min(devicePixelRatio || 1, 2), w = this.cv.width / r, h = this.cv.height / r;
        if (Math.abs(this.cv.clientWidth * r - this.cv.width) > 2) this.fit();
        this.c.setTransform(r, 0, 0, r, 0, 0); this.c.clearRect(0, 0, w, h);
        const s = Math.min(w / 300, h / 310) * 0.95; this.draw(w / 2, h * 0.42, s);
      }
      requestAnimationFrame(n => this.frame(n));
    }
  }
  window.Luma = { LumaView, pickMood, MOODS };
})();
