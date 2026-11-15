/* BioOrbit móvil — lógica de la app (versión teléfono del HUD + consola de escritorio).
   Qué es real y qué es simulado:
     · Rostro fijado y pulso rPPG: cámara frontal del teléfono (real, experimental).
     · Frecuencia cardíaca del reloj: Bluetooth LE (real) o «Demo».
     · SpO2, temperatura, CO2, radiación, HRV, sueño: telemetría SIMULADA (assets/telemetry.json).
   PROTOTIPO EDUCATIVO: no es un dispositivo médico. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const N = window.BioNative;
  const store = {
    get(k, d) { try { const v = localStorage.getItem('bio_' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('bio_' + k, JSON.stringify(v)); } catch (e) { /* sin almacenamiento */ } },
  };

  // ------------------------------------------------------------------ datos fijos
  const ROSTER = {
    'ASTRO-01': { role: 'Comandante', module: 'Hábitat', pos: [0, 0] },
    'ASTRO-02': { role: 'Ingeniera de vuelo', module: 'Laboratorio', pos: [9, 4] },
    'ASTRO-03': { role: 'Especialista médico', module: 'Laboratorio', pos: [12, 6] },
    'ASTRO-04': { role: 'Especialista de carga', module: 'Almacén', pos: [38, 2] },
  };
  const FIRST_RESPONSE = [
    'Llega hasta la persona y háblale fuerte; toca su hombro. ¿Responde?',
    'Si no responde ni respira con normalidad: pide ayuda y trae el desfibrilador (DEA).',
    'Inicia compresiones torácicas al centro del pecho, firmes y continuas, hasta que llegue apoyo.',
    'Avisa al cirujano de vuelo / control de misión y sigue sus indicaciones.',
  ];
  const CRISIS = /suicid|quitarme la vida|matarme|no quiero vivir|hacerme da[ñn]o|terminar con todo|mejor muerto/i;
  const TOPICS = {
    ansiedad: /ansios|nervios|p[aá]nico|angusti|estr[eé]s|preocupad|agobi/i,
    tristeza: /triste|soledad|\bsol[oa]\b|extra[ñn]o|llor|deprim|vac[ií]o|desanim/i,
    cansancio: /cansad|sue[ñn]o|insomnio|agotad|fatiga|dormir|dorm[ií]/i,
    enojo: /enoj|furios|molest|harto|irritad|frustr/i,
    bien: /\bbien\b|content|feliz|tranquil|animad|genial|motivad/i,
    gracias: /gracias/i,
    saludo: /^(hola|buen[oa]s|qu[eé] tal|hey|ey|qu[eé] onda)\b/i,
    como: /c[oó]mo est[aá]s|y t[uú]\b|qu[eé] haces/i,
  };
  const REPLIES = {
    ansiedad: ['Se siente pesado cuando la mente corre. Probemos algo corto: toca «Respiración guiada» y respiramos juntos un par de rondas.',
      'Lo que sientes es una reacción normal a un entorno exigente. Intenta nombrar en voz alta tres cosas que ves a tu alrededor; ayuda a aterrizar.'],
    tristeza: ['Gracias por contármelo. Extrañar y sentirse lejos es muy humano en una misión larga. ¿Te gustaría escribirle un mensaje a alguien de casa hoy?',
      'Aquí estoy contigo. A veces ayuda también hablar con un compañero a bordo; no tienes que cargar esto en silencio.'],
    cansancio: ['Suena a que tu cuerpo pide descanso. Si puedes, baja la luz, estira cuello y hombros y reserva un bloque corto para dormir.',
      'El cansancio acumulado pesa en el ánimo también. Hoy prioriza una cosa importante y deja el resto para mañana.'],
    enojo: ['Tiene sentido frustrarse cuando el espacio es chico y la rutina larga. Antes de responder a alguien, prueba tres respiraciones lentas.',
      'Gracias por decirlo en vez de guardarlo. ¿Quieres contarme qué lo detonó?'],
    bien: ['¡Qué bueno escucharlo! Aprovecha ese ánimo para charlar con alguien de la tripulación; el buen humor se contagia.'],
    gracias: ['Para eso estoy. Cuando quieras, seguimos hablando.', '¡De nada! Me gusta platicar contigo.'],
    saludo: ['¡Hola! ¿Cómo va tu día?', '¡Hola! Qué gusto escucharte. ¿Qué tal todo por allá?'],
    como: ['Yo aquí, flotando y cuidando la cabina. ¿Y tú, cómo te sientes hoy?', 'Muy bien, gracias por preguntar. ¿Qué has hecho hoy?'],
    otro: ['Te escucho. Cuéntame un poco más de cómo ha sido tu día.', 'Gracias por compartirlo. ¿Cómo te sientes ahora mismo, en una palabra?'],
  };
  const CRISIS_TEXT = 'Gracias por decírmelo. No quiero que lo cargues solo ahora mismo. Por favor habla ya con un compañero cercano o con el cirujano de vuelo: toca «Pedir apoyo humano» y les aviso. Si estás en la Tierra y piensas en hacerte daño, llama a emergencias o a una línea de crisis de tu país. Yo me quedo aquí contigo mientras llega alguien.';
  const HUD_TIPS = {
    stable: ['Todo estable. Estírate un minuto y toma agua.', 'Buen momento para grabarle un mensaje a tu familia.',
      'Mira la Tierra por la ventana un momento: ayuda a reconectar.', 'Respira hondo: en la pestaña Luma te guío cuatro tiempos.'],
    hrv_low: ['Tu HRV bajó: hagamos 4 respiraciones lentas para recuperarte.'],
    sleep_low: ['Tu sueño ha sido poco eficiente: baja la luz una hora antes de dormir.'],
    alerts_high: ['Varias alertas seguidas: haz una pausa corta y avisa a tu equipo.'],
    unsteady: ['Te noto inquieto en la cámara: relaja cuello y hombros un momento.'],
    support: ['Si algo te pesa, platícalo hoy con alguien de la tripulación.'],
    escalate: ['Hoy conviene hablar con el cirujano de vuelo o con el comandante.'],
  };
  const WHO5_ITEMS = ['Me he sentido alegre y de buen humor', 'Me he sentido tranquilo y relajado', 'Me he sentido activo y con energía',
    'Me he despertado sintiéndome fresco y descansado', 'Mi vida diaria ha estado llena de cosas que me interesan'];
  const WHO5_BANDS = ['Bienestar dentro de lo esperado.', 'Bienestar reducido: conviene cuidarte y platicarlo con alguien.',
    'Bienestar muy bajo: se recomienda apoyo de tu equipo.'];
  const QUICK = ['Estoy estresado', 'No puedo dormir', 'Me siento solo', 'Estoy bien'];
  const COL = { ok: '#3ef0b0', wa: '#ffc857', cr: '#ff4d6d', cy: '#38e1ff', vi: '#8b7cff', mu: '#8fb4d9' };
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const nan = v => v === null || v === undefined || Number.isNaN(v);

  // ------------------------------------------------------------------ estado
  const S = {
    data: null, crew: store.get('crew', 'ASTRO-02'), idx: {}, playing: true, tickN: 0,
    flat: false, radius: store.get('radius', 20),
    em: { phase: 'OK', missing: 0, deadline: 0, ackUntil: 0 }, sent: null,
    row: null, physio: { level: 0, reasons: [] }, status: 'OK',
    watch: { state: 'off', name: '', bpm: null, rr: [], hrv: null, last: 0, demo: null, devices: [] },
    cam: { on: false, ready: false, face: null, lastDet: 0, busy: false, cx: [], detMs: 60, fps: 0, frames: 0, fpsT: 0, visible: true },
    breath: false, crisis: false, checkins: store.get('checkins', {}), chat: store.get('chat', {}),
    tx: [], rx: [], msg: { key: '', i: 0, t: 0 }, locked: false, ready: false,
    // vigilancia "nadie en cámara"
    abs: { phase: 'OK', lastSeen: 0, deadline: 0, ackUntil: 0, sent: null, nextBuzz: 0, nextSay: 0 },
    cfg: { absence: store.get('absence', true), absSec: store.get('absSec', 20), voice: store.get('voice', true), voiceAck: store.get('voiceAck', true), listenAlways: store.get('listenAlways', true), voiceSos: store.get('voiceSos', true), replyAll: store.get('replyAll2', true), bg: store.get('bg', true), preferApp: store.get('preferApp', true) },
    voice: { listening: false, purpose: null, after: null, convo: store.get('convo', false), misses: 0 },
    sos: { phase: 'OK', deadline: 0, sent: null, text: '' },
    ai: { key: false, waiting: null, seq: 0, spoken: false, timer: 0 },
    music: { active: false, playing: false, mode: '', title: '', station: '', desc: '', spoken: false, wanted: null },
  };

  // ------------------------------------------------------------------ utilidades UI
  function toast(text, ms = 3500) {
    const t = $('toast'); t.textContent = text; t.classList.remove('hidden');
    clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add('hidden'), ms);
  }
  function showView(v) {
    document.querySelectorAll('.view').forEach(e => e.classList.toggle('active', e.id === 'view-' + v));
    document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
    if (v === 'alerts') $('rxDot').classList.add('hidden');
    if (window.BioCrew) BioCrew.onView(v);
    window.scrollTo(0, 0);
  }

  // ------------------------------------------------------------------ telemetría simulada
  function physioState(win) {
    const mean = k => { const v = win.map(r => r[k]).filter(x => !nan(x)); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : NaN; };
    const hrv = mean('hrv_rmssd_ms'), sleep = mean('sleep_efficiency_pct');
    const crit = win.filter(r => r.alert === 'CRÍTICO').length / Math.max(1, win.length);
    let pts = 0; const reasons = [];
    if (!nan(hrv)) { if (hrv < 25) { pts += 2; reasons.push('hrv_low'); } else if (hrv < 40) { pts += 1; reasons.push('hrv_low'); } }
    if (!nan(sleep)) { if (sleep < 70) { pts += 2; reasons.push('sleep_low'); } else if (sleep < 80) { pts += 1; reasons.push('sleep_low'); } }
    if (crit >= 0.25) { pts += 2; reasons.push('alerts_high'); } else if (crit >= 0.10) { pts += 1; reasons.push('alerts_high'); }
    return { level: pts >= 4 ? 2 : pts >= 2 ? 1 : 0, reasons };
  }
  function vitalsStatus(r) {
    const bad = v => nan(v) || v <= 0;
    const hb = bad(r.heart_rate_bpm), sb = bad(r.spo2_pct);
    return hb && sb ? 'NO_VITALS' : (hb || sb ? 'SENSOR_FAULT' : 'OK');
  }
  function crewRows() { return S.data ? (S.data.crew[S.crew] || Object.values(S.data.crew)[0]) : []; }

  function currentRow() {
    const rows = crewRows(); const i = (S.idx[S.crew] || 0) % rows.length;
    const r = Object.assign({}, rows[i]);
    const w = S.watch;
    if (w.state === 'live' && w.bpm) {
      r.heart_rate_bpm = w.bpm; r.src_hr = 'reloj';
      if (w.hrv) { r.hrv_rmssd_ms = w.hrv; r.src_hrv = 'reloj'; }
    } else if (w.state === 'lost') {
      r.heart_rate_bpm = r.hrv_rmssd_ms = r.spo2_pct = NaN;
    }
    if (S.flat) r.heart_rate_bpm = r.hrv_rmssd_ms = r.spo2_pct = NaN;
    const win = rows.slice(Math.max(0, i - 11), i + 1);
    return { r, physio: physioState(win) };
  }

  // máquina de estados de la alerta (igual que src/alerts.py)
  function emStep(status, now) {
    const em = S.em;
    if (status !== 'NO_VITALS') {
      const rec = em.phase === 'CONFIRMING' || em.phase === 'SENT';
      em.phase = 'OK'; em.missing = 0; return rec ? 'RECOVERED' : '';
    }
    if (now < em.ackUntil) return '';
    em.missing++;
    if (em.phase === 'OK' && em.missing >= 3) { em.phase = 'CONFIRMING'; em.deadline = now + 10; return 'CONFIRMING'; }
    if (em.phase === 'CONFIRMING' && now >= em.deadline) { em.phase = 'DUE'; return 'DUE'; }
    return '';
  }
  function nearby(crew) {
    const [x0, y0] = ROSTER[crew].pos;
    return Object.entries(ROSTER).filter(([c]) => c !== crew)
      .map(([c, i]) => [c, i, Math.hypot(i.pos[0] - x0, i.pos[1] - y0)])
      .filter(t => t[2] <= S.radius).sort((a, b) => a[2] - b[2]);
  }
  function broadcast(kind) {
    const crew = S.crew, mod = ROSTER[crew].module, near = nearby(crew);
    const u = window.BioCrew && BioCrew.state.user, who = u ? `${u.name} (${crew})` : crew;
    const message = kind === 'NO_VITALS' ? `${who} · ${mod}: SIN SIGNOS VITALES. Acudan de inmediato.`
      : kind === 'NO_PRESENCE' ? `${who} · ${mod}: no aparece en la cámara. Vayan a revisar que esté bien.`
      : kind === 'SOS' ? `${who} · ${mod} pidió AYUDA por voz. Acudan de inmediato.`
      : `${who} · ${mod} pide apoyo humano ahora.`;
    const payload = { ts: Date.now() / 1000, kind, crew, module: mod, message, notified: near.map(n => n[0]), origin: N.deviceId };
    N.sendAlert(payload);
    if (window.BioCrew) BioCrew.alert(kind, message);     // también al servidor (llega por datos móviles)
    const rec = { kind, message, when: new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), near };
    S.tx.unshift(rec); renderAlerts();
    return rec;
  }

  // ------------------------------------------------------------------ voz de Luma
  function say(text, urgent = false) {
    if (S.locked) return;                       // en el login Luma no habla
    S.said = (S.said || []).filter(x => Date.now() - x.t < 30000).concat([{ text, t: Date.now() }]).slice(-4);
    lumaS.talk(Math.min(8, 1 + text.length / 14)); lumaB.talk(Math.min(8, 1 + text.length / 14));
    if (S.cfg.voice) N.speak(text, urgent);
  }
  // pregunta en voz alta durante una alerta y luego escucha «estoy bien / estoy aquí»
  function askAck(text) {
    say(text, true);
    if (!S.cfg.voiceAck) return;
    if (S.cfg.voice) S.voice.after = 'ack'; else setTimeout(() => listen('ack'), 500);
  }
  const BUZZ_WARN = [0, 400, 200, 400];
  const BUZZ_SENT = [0, 900, 300, 900, 300, 900];

  // ------------------------------------------------------------------ nadie en cámara
  // OK -> (sin rostro S.cfg.absSec s) -> WARN (15 s para tocar «Estoy aquí») -> SENT (alerta a cercanos)
  const ABS_COUNTDOWN = 15;
  function absenceStep(now) {
    const a = S.abs;
    const watching = S.cfg.absence && S.cam.on && S.cam.ready && !document.hidden;
    if (!watching) {
      if (a.phase !== 'OK') { a.phase = 'OK'; a.sent = null; }
      a.lastSeen = now; return;
    }
    if (lock.box) {
      if (a.phase !== 'OK') {
        a.phase = 'OK'; a.sent = null; N.stopSpeaking();
        say(`Ya te veo, ${S.crew}. Qué bueno que estás aquí.`); toast('Rostro detectado de nuevo.');
      }
      a.lastSeen = now; return;
    }
    if (now < a.ackUntil) { a.lastSeen = now; return; }
    const away = now - a.lastSeen;
    if (a.phase === 'OK' && away >= S.cfg.absSec) {
      a.phase = 'WARN'; a.deadline = now + ABS_COUNTDOWN; a.nextBuzz = now + 5; a.nextSay = now + 8;
      N.vibratePattern(BUZZ_WARN);
      askAck(`${S.crew}, no te veo en la cámara. Si estás bien, di «estoy aquí» o toca el botón.`);
      N.notify('BioOrbit: no te veo en la cámara', 'Toca «Estoy aquí» o se avisará a la tripulación cercana.', true);
    } else if (a.phase === 'WARN') {
      if (now >= a.deadline) {
        a.phase = 'SENT'; a.sent = broadcast('NO_PRESENCE'); a.nextBuzz = now + 8; a.nextSay = now + 30;
        N.vibratePattern(BUZZ_SENT);
        const who = a.sent.near.map(n => n[0]).join(' y ');
        say(`Alerta enviada. ${who ? 'Avisé a ' + who + '.' : 'No hay nadie dentro del radio.'} ${S.crew} no aparece en la cámara.`, true);
        N.notify('BioOrbit: alerta enviada', a.sent.message, true);
      } else {
        if (now >= a.nextBuzz) { N.vibrate(300); a.nextBuzz = now + 5; }
        if (now >= a.nextSay) { askAck('¿Sigues ahí? Di «estoy aquí».'); a.nextSay = now + 30; }
      }
    } else if (a.phase === 'SENT') {
      // sigue llamando la atención de quien esté cerca del teléfono
      if (now >= a.nextBuzz) { N.vibratePattern(BUZZ_SENT); a.nextBuzz = now + 8; }
      if (now >= a.nextSay) { say(`Atención: ${S.crew} necesita ayuda. No aparece en la cámara.`, true); a.nextSay = now + 30; }
    }
  }

  function tick() {
    const now = Date.now() / 1000;
    if (S.watch.state === 'live' && now - S.watch.last > 8) setWatch('lost', 'El reloj dejó de mandar pulso.');
    S.tickN++;
    if (S.playing && S.tickN % 2 === 0) S.idx[S.crew] = (S.idx[S.crew] || 0) + 1;
    const { r, physio } = currentRow();
    S.row = r; S.physio = physio; S.status = vitalsStatus(r);
    const ev = S.locked ? null : emStep(S.status, now);
    if (ev === 'CONFIRMING') {
      N.vibratePattern(BUZZ_WARN); N.notify('BioOrbit: ¿estás bien?', 'No detecto tus signos vitales. Abre la app y toca «Estoy bien».', true);
      askAck(`${S.crew}, no detecto tus signos vitales. Si estás bien, di «estoy bien» o toca el botón.`);
    } else if (ev === 'DUE') {
      S.sent = broadcast('NO_VITALS'); S.em.phase = 'SENT';
      N.vibratePattern(BUZZ_SENT); N.notify('BioOrbit: alerta enviada', S.sent.message, true);
      const who = S.sent.near.map(n => n[0]).join(' y ');
      say(`Alerta enviada. ${who ? 'Avisé a ' + who + '.' : 'No hay nadie dentro del radio.'}`, true);
    } else if (ev === 'RECOVERED') S.sent = null;
    if (!S.locked) { absenceStep(now); sosStep(now); }
    renderEar(); if (S.tickN % 2 === 0) renderDiag();
    renderTelemetry(); renderEmergency(); lumaStep(now);
  }

  // ------------------------------------------------------------------ render telemetría
  function renderTelemetry() {
    const r = S.row; if (!r) return;
    const items = [
      ['Frec. cardíaca' + (r.src_hr ? ' ⌚' : ''), r.heart_rate_bpm, 'bpm', 0, v => v >= 55 && v <= 100],
      ['SpO₂', r.spo2_pct, '%', 1, v => v >= 96],
      ['HRV' + (r.src_hrv ? ' ⌚' : ''), r.hrv_rmssd_ms, 'ms', 0, v => v >= 40],
      ['Temperatura', r.body_temp_c, '°C', 1, v => v >= 36 && v <= 37.5],
      ['CO₂ cabina', r.cabin_co2_ppm, 'ppm', 0, v => v < 4000],
      ['Radiación', r.radiation_rate_usv_h, 'µSv/h', 0, v => v < 35],
      ['Sueño', r.sleep_efficiency_pct, '%', 0, v => v >= 80],
    ];
    const g = $('telGrid');
    if (g.children.length !== items.length) {
      g.textContent = '';
      items.forEach(() => { const d = document.createElement('div'); d.className = 'tile'; d.innerHTML = '<span></span><b></b><small></small>'; g.appendChild(d); });
    }
    items.forEach(([lab, v, unit, dec, good], k) => {
      const d = g.children[k], miss = nan(v);
      d.style.setProperty('--c', miss ? COL.cr : (good(v) ? COL.ok : COL.wa));
      d.children[0].textContent = lab;
      d.children[1].textContent = miss ? '—' : v.toLocaleString('es-MX', { maximumFractionDigits: dec, minimumFractionDigits: dec });
      d.children[2].textContent = miss ? '' : unit;
    });
    const w = S.watch.state;
    $('telSub').textContent = w === 'live' ? `pulso del reloj · resto simulado · ${r.t}` : w === 'lost' ? 'reloj sin señal de pulso' : `simulada · ${r.t}`;
    $('telSub').style.color = w === 'live' ? COL.ok : w === 'lost' ? COL.cr : '';
    const lv = { NORMAL: ['Estable', COL.ok], 'PRECAUCIÓN': ['Precaución', COL.wa], 'CRÍTICO': ['Crítico', COL.cr] }[r.alert] || ['Estable', COL.ok];
    const [txt, col] = S.status === 'OK' ? lv : ['Sin señal', COL.cr];
    $('crewTxt').textContent = S.crew; $('crewState').textContent = txt; $('crewChip').style.setProperty('--c', col);
  }

  function renderEmergency() {
    const box = $('emergency'), em = S.em, now = Date.now() / 1000;
    if (em.phase === 'CONFIRMING') {
      box.className = 'emergency warn';
      $('emTitle').textContent = `No detecto signos vitales de ${S.crew}`;
      $('emText').textContent = `Aviso a tripulantes cercanos en ${Math.max(0, Math.ceil(em.deadline - now))} s. Si estás bien, tócalo.`;
      $('emSteps').classList.add('hidden');
    } else if (em.phase === 'SENT' && S.sent) {
      box.className = 'emergency';
      $('emTitle').textContent = `Alerta enviada a las ${S.sent.when}`;
      $('emText').textContent = 'Avisados: ' + (S.sent.near.map(n => `${n[0]} (${n[2].toFixed(0)} m)`).join(', ') || 'nadie dentro del radio');
      $('emSteps').classList.remove('hidden');
    } else if (S.sos.phase === 'SENT' && S.sos.sent) {
      box.className = 'emergency';
      $('emTitle').textContent = `SOS enviado: ${S.crew} pidió ayuda por voz`;
      $('emText').textContent = `${S.sos.sent.when} · Avisados: ` + (S.sos.sent.near.map(n => `${n[0]} (${n[2].toFixed(0)} m)`).join(', ') || 'nadie dentro del radio');
      $('emSteps').classList.remove('hidden');
    } else if (S.sos.phase === 'CONFIRM') {
      box.className = 'emergency warn';
      $('emTitle').textContent = '¿Necesitas ayuda?';
      $('emText').textContent = `Escuché «${S.sos.text.slice(0, 60)}». Aviso a la tripulación en ${Math.max(0, Math.ceil(S.sos.deadline - now))} s. Si fue un error, di «cancela» o toca el botón.`;
      $('emSteps').classList.add('hidden');
    } else if (S.abs.phase === 'SENT' && S.abs.sent) {
      box.className = 'emergency';
      $('emTitle').textContent = `Alerta enviada: ${S.crew} no aparece en la cámara`;
      $('emText').textContent = `${S.abs.sent.when} · Avisados: ` + (S.abs.sent.near.map(n => `${n[0]} (${n[2].toFixed(0)} m)`).join(', ') || 'nadie dentro del radio');
      $('emSteps').classList.remove('hidden');
    } else if (S.abs.phase === 'WARN') {
      box.className = 'emergency warn';
      $('emTitle').textContent = 'No te veo en la cámara';
      $('emText').textContent = `Aviso a tripulantes cercanos en ${Math.max(0, Math.ceil(S.abs.deadline - now))} s. Si estás bien, tócalo.`;
      $('emSteps').classList.add('hidden');
    } else if (S.status === 'SENSOR_FAULT') {
      box.className = 'emergency warn';
      $('emTitle').textContent = 'Un sensor dejó de reportar';
      $('emText').textContent = 'Revisa que el reloj o el sensor estén bien colocados.';
      $('emSteps').classList.add('hidden');
    } else box.className = 'emergency hidden';
    const vit = em.phase === 'CONFIRMING' || em.phase === 'SENT', abs = S.abs.phase !== 'OK', sos = S.sos.phase !== 'OK';
    $('btnOk').classList.toggle('hidden', !(vit || abs || sos));
    $('btnOk').textContent = vit ? 'Estoy bien' : sos && S.sos.phase === 'CONFIRM' ? 'Cancelar, estoy bien' : sos ? 'Ya estoy bien' : 'Estoy aquí';
  }

  // ------------------------------------------------------------------ reloj
  function setWatch(state, msg, name) {
    const w = S.watch; w.state = state; if (name) w.name = name;
    if (state !== 'live') { w.bpm = null; }
    if (state === 'off') { w.rr = []; w.hrv = null; }
    if (msg) $('watchHint').textContent = msg;
    renderWatch();
  }
  function renderWatch() {
    const w = S.watch;
    const sub = { off: 'Sin reloj · Bluetooth', scanning: 'Buscando relojes…', connecting: 'Conectando…', connected: 'Conectado · esperando pulso',
      live: `${w.name} · en vivo`, lost: `${w.name || 'Reloj'} · sin señal de pulso`, error: 'Error de Bluetooth' }[w.state] || '';
    $('watchSub').textContent = sub;
    $('watchSub').style.color = w.state === 'live' ? COL.ok : (w.state === 'lost' || w.state === 'error') ? COL.cr : '';
    $('watchBpm').textContent = w.bpm ? Math.round(w.bpm) : '—';
    const active = ['connecting', 'connected', 'live', 'lost'].includes(w.state) || w.demo;
    $('btnWatch').textContent = w.state === 'scanning' ? 'Buscando…' : active ? 'Desconectar reloj' : 'Conectar reloj';
    $('btnWatch').className = 'btn ' + (active ? 'danger' : 'primary');
    $('btnWatch').disabled = w.state === 'scanning';
    $('btnWatchDemo').classList.toggle('hidden', !!active);
    const list = $('watchList'); list.textContent = '';
    list.classList.toggle('hidden', !(w.devices.length && !active));
    w.devices.forEach(d => {
      const li = document.createElement('li');
      const left = document.createElement('div'); left.textContent = d.name;
      const sm = document.createElement('small'); sm.textContent = ` ${d.rssi} dBm${d.hr ? ' · ❤ perfil cardíaco' : ''}`; left.appendChild(sm);
      const b = document.createElement('button'); b.className = 'btn small primary'; b.textContent = 'Conectar';
      b.onclick = () => { w.devices = []; setWatch('connecting', `Conectando a ${d.name}…`, d.name); N.watchConnect(d.address); };
      li.append(left, b); list.appendChild(li);
    });
  }
  function onHR(p) {
    const w = S.watch;
    if (!p || !(p.bpm > 0)) return;
    w.bpm = p.bpm; w.last = Date.now() / 1000;
    if (p.rr && p.rr.length) {
      w.rr.push(...p.rr); w.rr = w.rr.slice(-40);
      if (w.rr.length >= 8) {
        let s = 0; for (let i = 1; i < w.rr.length; i++) s += (w.rr[i] - w.rr[i - 1]) ** 2;
        w.hrv = Math.sqrt(s / (w.rr.length - 1));
      }
    }
    if (w.state !== 'live') { w.state = 'live'; $('watchHint').textContent = `Recibiendo pulso de ${w.name || 'tu reloj'}.`; }
    renderWatch();
  }
  function startDemoWatch() {
    stopDemoWatch(); let t = 0;
    S.watch.name = 'Reloj demo (Wear OS)';
    S.watch.demo = setInterval(() => {
      t++; const bpm = 72 + 3.2 * Math.sin(t * 0.35);
      const rr = 60000 / bpm + 32 * Math.sin(t * 0.9);
      onHR({ bpm: Math.round(bpm * 10) / 10, rr: [rr] });
    }, 1000);
    setWatch('connected', 'Demo de reloj: pulso simulado.');
  }
  function stopDemoWatch() { if (S.watch.demo) { clearInterval(S.watch.demo); S.watch.demo = null; } }
  function watchButton() {
    const w = S.watch;
    if (w.demo) { stopDemoWatch(); setWatch('off', 'Reloj desconectado.'); return; }
    if (['connecting', 'connected', 'live', 'lost'].includes(w.state)) { setWatch('off', 'Reloj desconectado.'); N.watchDisconnect(); return; }
    w.devices = []; setWatch('scanning', 'Buscando relojes por Bluetooth (10 s)…'); N.watchScan();
  }
  N.on('watch_devices', list => {
    S.watch.devices = (list || []).filter(d => d && d.address);
    if (!S.watch.devices.length) { setWatch('off', 'No encontré reloj. Abre BioOrbit Watch Bridge y pulsa «Iniciar transmisión».'); return; }
    const hr = S.watch.devices.filter(d => d.hr);
    if (hr.length === 1) { const d = hr[0]; S.watch.devices = []; setWatch('connecting', `Conectando a ${d.name}…`, d.name); N.watchConnect(d.address); return; }
    setWatch('off', 'Elige tu reloj:');
  });
  N.on('watch_status', s => {
    if (!s) return;
    if (s.state === 'lost' && S.watch.state === 'off') return;   // desconexión pedida por la persona
    if (s.state === 'connected' && S.watch.state === 'live') return;
    setWatch(s.state, s.msg, s.name);
  });
  N.on('watch_hr', onHR);

  // ------------------------------------------------------------------ alertas recibidas
  N.on('alert_received', ev => {
    const p = (ev && ev.payload) || {};
    if (p.origin && p.origin === N.deviceId) return;
    // la misma alerta puede llegar por el Wi-Fi (UDP) y por el servidor: solo una vez
    const key = String(p.kind) + '|' + String(p.message), nowMs = Date.now();
    S.rxSeen = (S.rxSeen || []).filter(x => nowMs - x.t < 120000);
    if (S.rxSeen.some(x => x.k === key)) return;
    S.rxSeen.push({ k: key, t: nowMs });
    S.rx.unshift({ kind: String(p.kind || 'ALERTA'), message: String(p.message || 'Alerta BioOrbit'), from: String(ev.from || ''),
      when: new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }) });
    S.rx = S.rx.slice(0, 30); renderAlerts();
    if (!document.getElementById('view-alerts').classList.contains('active')) $('rxDot').classList.remove('hidden');
    toast('⚠ ' + S.rx[0].message, 6000); N.vibratePattern(BUZZ_SENT);
    say('Alerta de la tripulación. ' + S.rx[0].message.slice(0, 180), true);
  });
  N.on('alert_sent', r => { if (r && r.msg) toast(r.msg); });
  function renderAlerts() {
    const fill = (ul, arr, fn) => {
      ul.textContent = '';
      if (!arr.length) { const li = document.createElement('li'); li.className = 'empty'; li.textContent = 'Sin alertas.'; ul.appendChild(li); return; }
      arr.forEach(a => { const li = document.createElement('li'); li.className = (a.kind === 'NO_VITALS' || a.kind === 'NO_PRESENCE' || a.kind === 'SOS') ? 'crit' : ''; fn(li, a); ul.appendChild(li); });
    };
    fill($('rxList'), S.rx, (li, a) => { li.textContent = a.message; const s = document.createElement('small'); s.textContent = `${a.when}${a.from ? ' · desde ' + a.from : ''}`; li.appendChild(s); });
    fill($('txList'), S.tx, (li, a) => { li.textContent = a.message; const s = document.createElement('small'); s.textContent = `${a.when} · avisados: ${a.near.map(n => n[0]).join(', ') || 'nadie en el radio'}`; li.appendChild(s); });
  }

  // ------------------------------------------------------------------ cámara: rostro fijado + rPPG
  const ov = $('overlay'), oc = ov.getContext('2d'), video = $('cam');
  const sampler = document.createElement('canvas'); sampler.width = 24; sampler.height = 12;
  const sc = sampler.getContext('2d', { willReadFrequently: true });
  const rppg = { t: [], v: [], bpm: null, q: 0, ema: null, wave: [] };
  const lock = { box: null, miss: 99, away: 0, tLock: 0 };

  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
      video.srcObject = stream; await video.play();
      S.cam.on = true; $('camOff').classList.add('hidden'); $('faceTag').textContent = 'Cargando detector de rostro…';
      if (!S.cam.ready) {
        try {
          try { await faceapi.tf.setBackend('webgl'); } catch (e) { await faceapi.tf.setBackend('cpu'); }
          await faceapi.tf.ready();
          await faceapi.nets.tinyFaceDetector.loadFromUri('model');
          S.cam.ready = true;
        } catch (e) { $('faceTag').textContent = 'No se pudo cargar el detector: ' + e.message; }
      }
      if (!S.cam.loop) { S.cam.loop = true; requestAnimationFrame(camLoop); }
    } catch (e) {
      $('faceTag').textContent = 'Sin permiso de cámara';
      toast('No pude abrir la cámara: ' + e.message);
    }
  }
  const dist = (a, b) => Math.hypot((a.x + a.w / 2) - (b.x + b.w / 2), (a.y + a.h / 2) - (b.y + b.h / 2));
  function lockUpdate(cands, now) {   // misma lógica que FaceLock en vision_monitor.py
    let fresh = false;
    if (!lock.box) {
      if (cands.length) { lock.box = cands.reduce((a, b) => (b.w * b.h > a.w * a.h ? b : a)); lock.target = { ...lock.box }; lock.tLock = now; lock.miss = lock.away = 0; fresh = true; }
    } else {
      const near = cands.filter(c => dist(c, lock.box) < lock.box.w * 0.6);
      if (near.length) {
        const d = near.reduce((a, b) => (dist(b, lock.box) < dist(a, lock.box) ? b : a));
        lock.target = d;
        lock.miss = lock.away = 0;
      } else {
        lock.miss++; lock.away = cands.length ? lock.away + 1 : 0;
        if (lock.away > 3) { lock.box = cands.reduce((a, b) => (b.w * b.h > a.w * a.h ? b : a)); lock.target = { ...lock.box }; lock.tLock = now; lock.miss = lock.away = 0; fresh = true; }
        else if (lock.miss > 4) lock.box = null;
      }
    }
    if (fresh || !lock.box) { rppg.t = []; rppg.v = []; rppg.wave = []; rppg.ema = null; if (!lock.box) { rppg.bpm = null; rppg.q = 0; } S.cam.cx = []; }
  }
  // Detector adaptativo: buscando rostro -> más seguido y con más resolución;
  // ya fijado -> menos seguido y más ligero (la caja se suaviza entre detecciones).
  // Si el teléfono tarda en detectar, el intervalo crece solo para no trabar la app.
  async function detect(now) {
    const locked = !!lock.box;
    const every = Math.max(locked ? 0.25 : 0.12, (S.cam.detMs / 1000) * 2.5);
    if (!S.cam.ready || S.cam.busy || now - S.cam.lastDet < every) return;
    S.cam.busy = true; S.cam.lastDet = now;
    const t0 = performance.now();
    try {
      const res = await faceapi.detectAllFaces(video, new faceapi.TinyFaceDetectorOptions({ inputSize: locked ? 160 : 224, scoreThreshold: 0.45 }));
      S.cam.detMs = 0.8 * S.cam.detMs + 0.2 * (performance.now() - t0);
      const vw = video.videoWidth;
      const cands = res.map(r => r.box).filter(b => b.x > vw * 0.02 && b.x + b.width < vw * 0.98)
        .map(b => ({ x: b.x, y: b.y, w: b.width, h: b.height }));
      lockUpdate(cands, performance.now() / 1000);
    } catch (e) { /* cuadro perdido */ }
    S.cam.busy = false;
  }
  function sampleGreen(now) {
    const b = lock.box; if (!b) return;
    const sx = b.x + b.w * 0.35, sy = b.y + b.h * 0.10, sw = b.w * 0.30, sh = b.h * 0.18;
    try { sc.drawImage(video, sx, sy, sw, sh, 0, 0, 24, 12); } catch (e) { return; }
    const d = sc.getImageData(0, 0, 24, 12).data; let g = 0;
    for (let i = 1; i < d.length; i += 4) g += d[i];
    g /= d.length / 4;
    rppg.ema = rppg.ema === null ? g : 0.98 * rppg.ema + 0.02 * g;
    rppg.t.push(now); rppg.v.push(g); rppg.wave.push(g - rppg.ema);
    while (rppg.t.length && now - rppg.t[0] > 8) { rppg.t.shift(); rppg.v.shift(); }
    if (rppg.wave.length > 150) rppg.wave.shift();
    S.cam.cx.push((b.x + b.w / 2) / b.w); if (S.cam.cx.length > 60) S.cam.cx.shift();
  }
  function estimate() {   // ventana de 8 s, sin tendencia, ventana Hann, espectro en 0.75–3 Hz
    const t = rppg.t, v = rppg.v, n = t.length;
    if (n < 40 || t[n - 1] - t[0] < 5) return;
    const fs = (n - 1) / (t[n - 1] - t[0]), m = Math.floor((t[n - 1] - t[0]) * fs);
    const x = new Float64Array(m); let j = 0;
    for (let i = 0; i < m; i++) {
      const tt = t[0] + i / fs; while (j < n - 2 && t[j + 1] < tt) j++;
      const a = (tt - t[j]) / Math.max(1e-6, t[j + 1] - t[j]); x[i] = v[j] + a * (v[j + 1] - v[j]);
    }
    let sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (let i = 0; i < m; i++) { sx += i; sy += x[i]; sxx += i * i; sxy += i * x[i]; }
    const slope = (m * sxy - sx * sy) / (m * sxx - sx * sx), icpt = (sy - slope * sx) / m;
    for (let i = 0; i < m; i++) x[i] = (x[i] - (slope * i + icpt)) * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (m - 1)));
    const pw = []; let best = 0, bf = 0;
    for (let f = 0.75; f <= 3.0001; f += 0.01) {
      let re = 0, im = 0; const w = 2 * Math.PI * f / fs;
      for (let i = 0; i < m; i++) { re += x[i] * Math.cos(w * i); im -= x[i] * Math.sin(w * i); }
      const p = Math.hypot(re, im); pw.push(p); if (p > best) { best = p; bf = f; }
    }
    const sorted = pw.slice().sort((a, b) => a - b), med = sorted[sorted.length >> 1] || 1e-9;
    rppg.q = best / med;
    if (rppg.q > 3) rppg.bpm = rppg.bpm === null ? bf * 60 : 0.9 * rppg.bpm + 0.1 * bf * 60;
  }
  function stability() {
    const a = S.cam.cx; if (a.length < 20 || !lock.box) return ['midiendo', COL.mu];
    const m = a.reduce((p, c) => p + c, 0) / a.length, sd = Math.sqrt(a.reduce((p, c) => p + (c - m) ** 2, 0) / a.length);
    return sd < 0.04 ? ['Alta', COL.ok] : sd < 0.12 ? ['Media', COL.wa] : ['Baja', COL.cr];
  }
  function brackets(x, y, w, h, n, col) {
    oc.strokeStyle = col; oc.lineWidth = 3; oc.lineCap = 'round'; oc.beginPath();
    [[x, y, 1, 1], [x + w, y, -1, 1], [x, y + h, 1, -1], [x + w, y + h, -1, -1]].forEach(([px, py, dx, dy]) => {
      oc.moveTo(px + dx * n, py); oc.lineTo(px, py); oc.lineTo(px, py + dy * n);
    });
    oc.stroke();
  }
  function drawOverlay(now) {
    const r = Math.min(devicePixelRatio || 1, 1.5), cw = ov.clientWidth, ch = ov.clientHeight;
    if (ov.width !== Math.round(cw * r)) { ov.width = Math.round(cw * r); ov.height = Math.round(ch * r); }
    oc.setTransform(r, 0, 0, r, 0, 0); oc.clearRect(0, 0, cw, ch);
    const vw = video.videoWidth, vh = video.videoHeight; if (!vw) return;
    const s = Math.max(cw / vw, ch / vh), ox = (cw - vw * s) / 2, oy = (ch - vh * s) / 2;
    const lvl = S.physio.level, col = S.status !== 'OK' || lvl >= 2 ? COL.cr : lvl === 1 ? COL.wa : COL.cy;
    const b = lock.box;
    if (b) {
      const x = cw - (ox + (b.x + b.w) * s), y = oy + b.y * s, w = b.w * s, h = b.h * s;   // espejo
      const k = Math.min(1, (now - lock.tLock) / 0.45), e = 1 - (1 - k) ** 3, g = (1 - e) * w * 0.45;
      brackets(x - g, y - g, w + 2 * g, h + 2 * g, 22 + 10 * (1 - e), col);
      const cx = x + w / 2, cy = y + h * 0.48, rr = w * 0.68;
      oc.strokeStyle = col + '66'; oc.lineWidth = 1; oc.beginPath(); oc.arc(cx, cy, rr, 0, 7); oc.stroke();
      oc.strokeStyle = col; oc.lineWidth = 2.5;
      for (let i = 0; i < 4; i++) {
        const a = now * 1.6 + i * Math.PI / 2; oc.beginPath();
        oc.moveTo(cx + (rr - 7) * Math.cos(a), cy + (rr - 7) * Math.sin(a)); oc.lineTo(cx + (rr + 7) * Math.cos(a), cy + (rr + 7) * Math.sin(a)); oc.stroke();
      }
      const sy = y + (0.5 + 0.5 * Math.sin(now * 2.2)) * h;
      const gr = oc.createLinearGradient(x, 0, x + w, 0); gr.addColorStop(0, col + '00'); gr.addColorStop(0.5, col + 'aa'); gr.addColorStop(1, col + '00');
      oc.strokeStyle = gr; oc.lineWidth = 2; oc.beginPath(); oc.moveTo(x + 6, sy); oc.lineTo(x + w - 6, sy); oc.stroke();
      setTag(k < 1 ? 'Fijando rostro…' : `${S.crew} · rostro fijado`, col);
    } else {
      const a = 0.5 + 0.5 * Math.sin(now * 3), w = cw * 0.5, h = w * 1.25;
      brackets((cw - w) / 2, (ch - h) / 2, w, h, 30, `rgba(143,180,217,${0.35 + 0.4 * a})`);
      if (S.cam.ready) setTag('Buscando rostro…', '');
    }
    // onda rPPG al pie del cuadro
    if (b && rppg.wave.length > 10) {
      const wv = rppg.wave, base = ch - 34;
      let mx2 = 1e-6; for (const v of wv) { const a = Math.abs(v); if (a > mx2) mx2 = a; }
      oc.strokeStyle = COL.cy; oc.lineWidth = 2; oc.beginPath();
      wv.forEach((v, i) => { const px = cw * 0.38 + (cw * 0.58) * i / (wv.length - 1), py = base - v / mx2 * 16; i ? oc.lineTo(px, py) : oc.moveTo(px, py); });
      oc.stroke();
    }
  }
  let lastEst = 0, lastFrame = 0, lastTag = '';
  function setTag(text, color) {
    if (text === lastTag) return;
    lastTag = text; $('faceTag').textContent = text; $('faceTag').style.color = color;
  }
  // En segundo plano Android no deja usar la cámara: se suelta y se vuelve a abrir al regresar
  // (la vigilancia «nadie en cámara» se pausa mientras la app está minimizada).
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (S.cam.on && video.srcObject) { video.srcObject.getTracks().forEach(t => t.stop()); S.cam.on = false; S.cam.paused = true; }
    } else {
      S.abs.lastSeen = Date.now() / 1000;
      if (S.cam.paused && !S.locked) { S.cam.paused = false; startCamera(); }
      renderBg();
    }
  });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(es => { S.cam.visible = es[0].isIntersecting; }).observe($('cam'));
  }
  // 30 cuadros por segundo: suficiente para el pulso (rPPG) y la mitad o un cuarto
  // del trabajo en pantallas de 60/120 Hz.
  function camLoop(ms) {
    requestAnimationFrame(camLoop);
    const now = ms / 1000;
    if (!S.cam.on || video.readyState < 2 || document.hidden || now - lastFrame < 0.032) return;
    lastFrame = now;
    detect(now);
    if (lock.box && lock.target) {   // la caja se desliza hacia la última detección (movimiento suave)
      for (const k of ['x', 'y', 'w', 'h']) lock.box[k] += (lock.target[k] - lock.box[k]) * 0.25;
    }
    sampleGreen(now);
    if (now - lastEst > 1) { lastEst = now; estimate(); renderPulse(); }
    if (S.cam.visible) drawOverlay(now);
    S.cam.frames++;
    if (now - S.cam.fpsT >= 2) {
      S.cam.fps = S.cam.frames / (now - S.cam.fpsT); S.cam.frames = 0; S.cam.fpsT = now;
      const be = (window.faceapi && faceapi.tf.getBackend()) || '—';
      $('perfTxt').textContent = `Rendimiento: ${S.cam.fps.toFixed(0)} fps · rostro ${S.cam.detMs.toFixed(0)} ms · ${be}`;
    }
  }
  function renderPulse() {
    const bpm = rppg.bpm, ok = bpm && bpm >= 55 && bpm <= 100;
    $('bpmCam').textContent = bpm ? Math.round(bpm) : '—';
    $('bpmCamLbl').textContent = bpm ? 'latidos/min' : (lock.box ? 'midiendo…' : 'sin rostro');
    const arc = $('ringArc'); const frac = bpm ? Math.max(0, Math.min(1, (bpm - 40) / 100)) : 0;
    arc.style.strokeDashoffset = String(314 * (1 - frac)); arc.style.stroke = ok ? COL.ok : COL.wa;
    const [st, sc2] = stability(); $('stab').textContent = st; $('stab').style.color = sc2;
    $('qBar').style.width = Math.min(100, rppg.q / 8 * 100) + '%';
  }

  // ------------------------------------------------------------------ Luma
  const lumaS = new Luma.LumaView($('lumaSmall')), lumaB = new Luma.LumaView($('lumaBig'));
  function whoLevel(raw) { return raw <= 7 ? 2 : raw < 13 ? 1 : 0; }
  function overall() {
    const ci = S.checkins[S.crew], wl = ci ? whoLevel(ci.raw) : null, pl = S.physio.level;
    return { level: wl === null ? pl : Math.max(pl, wl), escalate: wl === 2 || (wl === 1 && pl === 2) };
  }
  function lumaStep(now) {
    const { level, escalate } = overall(), reasons = S.physio.reasons, em = S.em.phase;
    const unsteady = stability()[0] === 'Baja';
    let pool;
    if (em === 'CONFIRMING') pool = [`${S.crew}, ¿me escuchas? No recibo tus signos vitales. Toca «Estoy bien» si lo estás.`];
    else if (em === 'SENT') pool = ['Ya avisé a la tripulación cercana. La ayuda va en camino; me quedo contigo.'];
    else if (S.sos.phase === 'CONFIRM') pool = ['Escuché que pides ayuda. Si fue un error, di «cancela».'];
    else if (S.sos.phase === 'SENT') pool = ['Ya pedí ayuda a la tripulación. Quédate donde estás; me quedo contigo.'];
    else if (S.abs.phase === 'WARN') pool = [`${S.crew}, no te veo en la cámara. Toca «Estoy aquí» si estás bien.`];
    else if (S.abs.phase === 'SENT') pool = ['Avisé a la tripulación cercana porque no apareces en la cámara.'];
    else if (S.breath) pool = ['Inhala conmigo… sostén… exhala despacio. Lo estás haciendo bien.'];
    else {
      pool = [];
      reasons.forEach(r => pool.push(...(HUD_TIPS[r] || [])));
      if (unsteady) pool.push(...HUD_TIPS.unsteady);
      if (level >= 1) pool.push(...HUD_TIPS.support);
      if (level >= 2) pool.push(...HUD_TIPS.escalate);
      if (!pool.length) pool = HUD_TIPS.stable;
    }
    const key = [level, reasons.join(), em, S.abs.phase, S.sos.phase, S.breath, unsteady].join('|');
    const m = S.msg;
    if (key !== m.key) { m.key = key; m.i = 0; m.t = now; setLumaMsg(pool[0]); }
    else if (now - m.t > 10) { m.i++; m.t = now; setLumaMsg(pool[m.i % pool.length]); }
    const emergency = em === 'CONFIRMING' || em === 'SENT' || S.status === 'NO_VITALS' || S.crisis || S.abs.phase !== 'OK' || S.sos.phase !== 'OK';
    const mood = Luma.pickMood({ level, breathing: S.breath, emergency, face: !!lock.box || !S.cam.on });
    [lumaS, lumaB].forEach(l => { l.setMood(mood); l.bpm = (S.watch.state === 'live' && S.watch.bpm) || rppg.bpm || S.row.heart_rate_bpm || 70; });
    if (lock.box && video.videoWidth) {
      const b = lock.box; lumaS.setLook(-((b.x + b.w / 2) / video.videoWidth - 0.5) * 2, -0.8);
    }
    $('lumaMood').textContent = lumaS.mood; $('lumaMood2').textContent = lumaB.mood;
    $('lumaState').textContent = `${S.crew} · ${['estable', 'desgaste leve', 'desgaste alto'][level]}`;
    $('escalate').classList.toggle('hidden', !escalate);
    $('btnSupport').classList.toggle('hidden', !(S.crisis || escalate));
  }
  function setLumaMsg(t) { $('lumaMsg').textContent = t; lumaS.talk(3); }

  // chat
  function chatHist() { return (S.chat[S.crew] = S.chat[S.crew] || []); }
  function bodyHint(r) {
    if (!r) return ''; const h = [];
    if (!nan(r.hrv_rmssd_ms) && r.hrv_rmssd_ms < 30) h.push(`tu variabilidad cardíaca está baja (${Math.round(r.hrv_rmssd_ms)} ms), señal de que tu cuerpo está bajo carga`);
    if (!nan(r.sleep_efficiency_pct) && r.sleep_efficiency_pct < 70) h.push(`tu eficiencia de sueño fue de ${Math.round(r.sleep_efficiency_pct)}%`);
    if (!nan(r.cabin_co2_ppm) && r.cabin_co2_ppm > 4000) h.push(`el CO₂ de la cabina está alto (${Math.round(r.cabin_co2_ppm)} ppm) y eso puede dar dolor de cabeza e irritabilidad`);
    return h.length ? 'Por cierto, ' + h.join('; ') + '.' : '';
  }
  function reply(text) {
    if (CRISIS.test(text)) { S.crisis = true; return CRISIS_TEXT; }
    const topic = Object.keys(TOPICS).find(k => TOPICS[k].test(text)) || 'otro';
    let msg = pick(REPLIES[topic]);
    if (['ansiedad', 'tristeza', 'cansancio', 'enojo'].includes(topic)) { const h = bodyHint(S.row); if (h) msg += ' ' + h; }
    return msg;
  }
  function renderChat() {
    const log = $('chatLog'), h = chatHist();
    if (!h.length) h.push(['bot', `¡Hola, ${S.crew}! Soy Luma, tu compañero a bordo. Puedes escribirme o hablarme con el micrófono cuando quieras.`]);
    log.textContent = '';
    h.slice(-40).forEach(([who, t]) => { const d = document.createElement('div'); d.className = 'msg ' + who; d.textContent = t; log.appendChild(d); });
    if (S.ai.waiting) { const d = document.createElement('div'); d.className = 'msg bot typing'; d.textContent = 'Luma está pensando…'; log.appendChild(d); }
    log.scrollTop = log.scrollHeight;
  }
  function saveChat() { S.chat[S.crew] = chatHist().slice(-60); store.set('chat', S.chat); }

  // ---------------- IA (Claude) ----------------
  function aiSystem() {
    const r = S.row || {}, f = (v, d = 0) => (nan(v) ? 'sin dato' : Number(v).toFixed(d));
    const lvl = ['estable', 'desgaste leve', 'desgaste alto'][overall().level];
    const ci = S.checkins[S.crew];
    return `Eres Luma, un pequeño robot compañero a bordo de una misión espacial (prototipo educativo BioOrbit, NASA Space Apps). ` +
      `Hablas con ${S.crew} (${ROSTER[S.crew].role}). Responde SIEMPRE en español de México, cálido, cercano y breve: ` +
      `Esto es una CONVERSACIÓN NORMAL POR VOZ: platica como un amigo, de cualquier tema (su día, la misión, la Tierra, música, dudas, chistes). ` +
      `Responde con naturalidad y brevedad (1 a 3 frases cortas, se leen en voz alta), sin listas, sin markdown y sin emojis. ` +
      `Puedes hacer preguntas de seguimiento para que la plática fluya. Si te saluda, salúdalo; si te da las gracias, responde con calidez. ` +
      `La transcripción de voz puede traer errores: interpreta la intención; si no se entiende, pide que lo repita. ` +
      `No conviertas cada respuesta en un consejo: habla de bienestar solo si menciona cómo se siente o si sus datos lo ameritan; ` +
      `entonces valida lo que siente y sugiere algo pequeño y concreto (respirar, descansar, hidratarse, hablar con alguien de la tripulación). ` +
      `La app tiene un ejercicio de «Respiración guiada» y un botón «Pedir apoyo humano». ` +
      `No eres médico ni psicólogo: no diagnosticas, no recetas y no das dosis. ` +
      `Si menciona hacerse daño, una crisis o una emergencia, pídele con calma que hable ya con un compañero o con el cirujano de vuelo y que toque «Pedir apoyo humano». ` +
      `Datos de su telemetría (simulada, salvo la frecuencia cardíaca si viene del reloj); úsalos solo si vienen al caso: ` +
      `frecuencia cardíaca ${f(r.heart_rate_bpm)} bpm${r.src_hr ? ' (reloj)' : ''}, HRV ${f(r.hrv_rmssd_ms)} ms, SpO2 ${f(r.spo2_pct, 1)} %, ` +
      `sueño ${f(r.sleep_efficiency_pct)} %, CO2 de cabina ${f(r.cabin_co2_ppm)} ppm, estado general: ${lvl}` +
      (ci ? `, último check-in WHO-5: ${ci.pct} %.` : '.');
  }
  function aiMessages() {
    const out = [];
    for (const [who, t] of chatHist().slice(-14)) {
      const role = who === 'me' ? 'user' : 'assistant';
      if (!out.length && role !== 'user') continue;          // la API pide empezar con el usuario
      if (out.length && out[out.length - 1].role === role) out[out.length - 1].content += '\n' + t;
      else out.push({ role, content: t });
    }
    return out;
  }
  function aiReady() { return S.ai.key && N.aiHasKey(); }
  function renderAI() {
    S.ai.key = N.aiHasKey();
    $('aiSub').textContent = S.ai.key ? `${N.aiModel() || 'IA'} · activa · necesita internet` : (N.isAndroid ? 'Respuestas básicas (sin IA)' : 'La IA solo funciona dentro del APK');
    $('aiDot').classList.toggle('on', !!S.ai.key);
    $('aiForm').classList.toggle('hidden', !!S.ai.key || !N.isAndroid);
    $('btnAiClear').classList.toggle('hidden', !S.ai.key);
  }

  function botSays(text, spoken) {
    S.lastBotT = Date.now();
    chatHist().push(['bot', text]); saveChat(); renderChat();
    lumaB.talk(Math.min(8, 1 + text.length / 14)); lumaStep(Date.now() / 1000);
    if (spoken || S.voice.convo) {
      if (S.cfg.voice) { say(text); if (S.voice.convo) S.voice.after = 'chat'; }
      else if (S.voice.convo) setTimeout(() => listen('chat'), 600);
    }
  }
  function send(text, spoken = false) {
    text = text.trim(); if (!text) return;
    if (musicCommand(text, spoken)) return;            // «pon música», «pausa», «siguiente»…
    if (window.BioCrew && BioCrew.voiceCommand(text, spoken)) return;   // «dile a la tripulación que…»
    if (S.ai.waiting) { S.ai.queue = (S.ai.queue ? S.ai.queue + '. ' : '') + text; return; }   // lo contesta al terminar
    chatHist().push(['me', text]); saveChat();
    if (/respiraci[oó]n guiada|^resp[ií]r/i.test(text) || /(gu[ií]ame|vamos|hagamos).*(respir)/i.test(text)) {
      renderChat(); botSays('Claro, respiremos juntos. Sigue el círculo: cuatro tiempos para cada fase.', spoken);
      setTimeout(() => breathe(true), 1500); return;
    }
    if (CRISIS.test(text) || !aiReady()) { renderChat(); botSays(reply(text), spoken); return; }
    const id = String(++S.ai.seq);
    S.ai.waiting = id; S.ai.spoken = spoken; renderChat();
    $('lumaMood2').textContent = 'pensando…';
    N.aiChat(id, aiSystem(), aiMessages());
    clearTimeout(S.ai.timer);
    S.ai.timer = setTimeout(() => { if (S.ai.waiting === id) N.emit('ai_error', { id, msg: 'La IA tardó demasiado.' }); }, 35000);
  }
  N.on('ai_reply', r => {
    if (!r || r.id !== S.ai.waiting) return;
    S.ai.waiting = null; clearTimeout(S.ai.timer);
    botSays(String(r.text).slice(0, 1200), S.ai.spoken);
    sendQueued();
  });
  function sendQueued() {
    if (!S.ai.queue) return;
    const q = S.ai.queue; S.ai.queue = '';
    setTimeout(() => send(q, true), 60);
  }
  N.on('ai_error', r => {
    if (!r || r.id !== S.ai.waiting) return;
    S.ai.waiting = null; clearTimeout(S.ai.timer);
    toast(r.msg || 'Sin IA. Uso respuestas básicas.', 4500);
    const h = chatHist(), last = [...h].reverse().find(x => x[0] === 'me');
    botSays(reply(last ? last[1] : ''), S.ai.spoken);
    renderAI(); sendQueued();
  });


  // ---------------- música ----------------
  // «pon música», «pon música relajante», «ponme a Bad Bunny», «reproduce Despacito», «pausa»,
  // «siguiente», «sube el volumen», «quita la música», «¿qué canción es?»
  // Mientras suena música, Luma solo contesta si empiezas con «Luma…» (para no responderle a la canción);
  // los controles («pausa», «siguiente», «bájale»…) funcionan sin decir «Luma».
  const plain = t => t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[¿?¡!.,;:«»"]/g, ' ').replace(/\s+/g, ' ').trim();
  const GENRES = [
    [/\b(relaj\w*|tranquil\w*|chill|calma\w*|suave|estudiar|concentr\w*|trabajar|lofi|lo fi)\b/, 'groovesalad'],
    [/\b(dormir|meditar|meditacion|ambiental|ambient|descansar|sueno)\b/, 'dronezone'],
    [/\b(nasa|mision|mission|astronauta\w*|cohete\w*)\b/, 'missioncontrol'],
    [/\b(espacial\w*|espacio|galaxia|cosmic\w*|cosmos|estrellas)\b/, 'deepspaceone'],
    [/\b(rock\w*|alternativ\w*|guitarra\w*)\b/, 'bagel'],
    [/\b(ochenta\w*|80s|80|ochentera\w*)\b/, 'u80s'],
    [/\b(setenta\w*|70s|70)\b/, 'seventies'],
    [/\b(jazz)\b/, 'sonicuniverse'],
    [/\b(electronica|electro\w*|bailar|baile|fiesta|animad\w*|alegre\w*|dance)\b/, 'poptron'],
    [/\b(pop|indie)\b/, 'indiepop'],
    [/\b(folk|acustic\w*|country)\b/, 'folkfwd'],
    [/\b(misterio|espias?|suspenso|agente secreto)\b/, 'secretagent'],
    [/\b(dubstep)\b/, 'dubstep'],
  ];
  const PLAY_RE = /^(?:(?:oye|por favor|porfa|puedes|podrias|me puedes|quiero que|ahora)\s+)*(pon(?:me|nos|le|gas|es|er)?|ponga|reproduce(?:me)?|reproducir|toca(?:me)?|tocar|quiero (?:escuchar|oir)|me (?:pones|pondrias|tocas)|escuchemos|pongamos|play)\b\s*(.*)$/;
  const MUSIC_W = /\b(musica|cancion|canciones|rola|rolas|radio|estacion|playlist|lista|album|disco|algo)\b/;
  function parseMusic(raw) {
    let t = plain(raw); if (!t) return null;
    // «… en Spotify» / «… en YouTube Music»: esa app directo
    let app = '';
    const am = t.match(/\s+(?:en|por|desde|con)\s+(spotify|youtube music|youtube|yt music)\b/);
    if (am) { app = /spotify/.test(am[1]) ? 'spotify' : 'youtube'; t = t.replace(am[0], ' ').replace(/\s+/g, ' ').trim(); }
    const vol = /\b(volumen|mas fuerte|mas alto|mas bajo|mas bajito|subele|bajale|sube|baja)\b/;
    if (/\b(que (cancion|musica|estacion|radio|suena|esta sonando|estas (tocando|poniendo))|como se llama (la|esta) cancion)\b/.test(t)) return { cmd: 'what' };
    if (vol.test(t) && /\b(sube\w*|subir|subele|mas fuerte|mas alto|aumenta\w*)\b/.test(t)) return { cmd: 'up' };
    if (vol.test(t) && /\b(baja\w*|bajar|bajale|mas bajo|mas bajito|disminuye)\b/.test(t)) return { cmd: 'down' };
    if (/\b(quita\w*|apaga\w*|deten\w*|para|detener|cierra|ya no quiero)\b.*\b(musica|radio|cancion|rola)\b/.test(t) || /^(stop|silencio|ya basta|basta)$/.test(t)) return { cmd: 'stop' };
    if (/^(pausa|pausala|pausar|pon pausa|pon(le)? (en )?pausa|pausa (la )?(musica|cancion|radio))$/.test(t) || /\bpausa (la )?(musica|cancion|radio)\b/.test(t)) return { cmd: 'pause' };
    if (/^(continua|sigue|reanuda|reanudala|play|quita la pausa|despausa|dale play)( (la )?(musica|cancion|radio))?$/.test(t)) return { cmd: 'resume' };
    if (/^(siguiente|la siguiente|otra|otra cancion|cambiala|cambia(la)? (de )?(cancion|estacion|musica|rola)|salta(la)?|adelanta(la)?|la que sigue|pon otra( cancion)?|siguiente (cancion|rola|estacion))$/.test(t)) return { cmd: 'next' };
    const m = t.match(PLAY_RE); if (!m) return null;
    const verb = m[1]; let rest = m[2].trim();
    const focus = /^(a\s+\S|(algo de|la musica de|musica de|canciones de|rolas de|lo de|lo mejor de|exitos de)\s+\S)/.test(rest) ? 'artist' : 'any';
    if (/^(la |una |algo de )?(radio|estacion)$/.test(rest)) return { cmd: 'play', query: '', station: 'groovesalad', generic: false };
    const strong = /^(reproduce|reproducir|toca|tocar|quiero|escuchemos|play)/.test(verb);
    if (!strong && !app && !MUSIC_W.test(rest) && !GENRES.some(g => g[0].test(rest)) && !/^a\s+\S/.test(rest)) return null;   // «pon una alarma» no es música
    rest = rest.replace(/\b(por favor|porfa|luma|ahorita|ahora)\b/g, ' ')
      .replace(/^(un poco de|un poquito de|algo de|algo|alguna|algunas?|unas?|la|el|las|los|mi|mis)\s+/, '')
      .replace(/^(musica|canciones|cancion|rolas|rola|radio|estacion|playlist|lista de reproduccion|album|disco)\b\s*/, '')
      .replace(/^(de|del|que sea|para|tipo|estilo|como)\s+/, '').replace(/^a\s+/, '').replace(/\s+/g, ' ').trim();
    if (app && rest) return { cmd: 'play', query: rest, station: '', generic: false, app, focus };
    if (!rest || /^(musica|algo|lo que sea|cualquier cosa|cualquiera|de todo|mia|mias|que tengo|del telefono|guardada)( \w+)?$/.test(rest)) return { cmd: 'play', query: '', station: '', generic: true };
    const g = rest.split(' ').length <= 4 && GENRES.find(x => x[0].test(rest));
    if (g) return { cmd: 'play', query: rest, station: g[1], generic: false };
    return { cmd: 'play', query: rest, station: '', generic: false, app, focus };
  }
  function musicOn() { return !!(S.music.active && S.music.playing); }
  function musicCommand(text, spoken) {
    const c = parseMusic(text); if (!c) return false;
    chatHist().push(['me', text]); saveChat(); renderChat();
    S.music.spoken = spoken;
    const m = S.music, ans = t => botSays(t, spoken);
    if (c.cmd === 'play') {
      S.music.wanted = c; N.musicPlay(c.query, c.station, c.generic, { app: c.app || '', focus: c.focus || 'any', preferApp: S.cfg.preferApp });   // contesta con music_result
      return true;
    }
    if (c.cmd === 'what') {
      ans(!m.active ? 'No hay música sonando. Di «pon música» y te pongo algo.'
        : m.mode === 'radio' ? `Es la radio ${m.title}${m.desc ? ', ' + m.desc : ''}. No sé el nombre exacto de la canción.`
        : m.mode === 'external' ? 'Está sonando en tu app de música; ahí puedes ver el nombre.'
        : `Es «${m.title}».`);
      return true;
    }
    if (!m.active) { ans('No hay música sonando. Di «pon música» y te pongo algo.'); return true; }
    N.musicControl(c.cmd);
    const t = { pause: 'Pausado.', resume: 'Sigo.', next: 'Va la siguiente.', stop: 'Listo, quité la música.', up: 'Subí el volumen.', down: 'Bajé el volumen.' }[c.cmd];
    botSays(t, spoken && c.cmd !== 'up' && c.cmd !== 'down');   // el volumen no se anuncia (se ve en pantalla)
    return true;
  }
  N.on('music_result', r => {
    if (!r) return;
    const st = N.STATIONS.find(x => x.id === r.station), q = r.query ? '«' + String(r.query).replace(/(^|\s)\S/g, x => x.toUpperCase()) + '»' : 'tu música', sp = S.music.spoken;
    const t = r.source === 'local' ? (r.query ? `Va, pongo ${q}${r.count > 1 ? ` (${r.count} canciones)` : ''}.` : `Va, pongo tu música: ${r.count} ${r.count === 1 ? 'canción' : 'canciones'} en aleatorio.`)
      : r.source === 'radio' ? `Va, pongo ${st ? st.desc + ' en la radio ' + st.name : 'la radio'}.`
      : r.source === 'radio_fallback' ? `No encontré música guardada en tu teléfono, así que pongo radio: ${st ? st.desc : 'música relajante'}.`
      : r.source === 'external' ? `Va, pongo ${q} en ${r.app || 'tu app de música'}.`
      : r.source === 'tap_notification' ? `Con la app minimizada Android no me deja abrir ${r.app}. Te dejé una notificación: tócala y pongo ${q}.`
      : r.source === 'app_missing' ? `No encontré ${r.app === 'youtube' ? 'YouTube Music' : 'Spotify'} instalado en tu teléfono.`
      : r.source === 'open_failed' ? `No pude abrir ${r.app}. Ábrelo una vez a mano, inicia sesión y vuelve a pedírmelo.`
      : r.source === 'none_background' ? `No encontré ${q} en el teléfono. Abre la app y te la busco en Spotify o YouTube Music.`
      : r.source === 'old' ? 'Actualiza la app para poner música.'
      : `No encontré ${q} en tu teléfono ni una app de música. Si quieres, pongo radio: di «pon música relajante» o «pon rock».`;
    botSays(t, sp);
  });
  // 5 s después de abrir Spotify: ¿ya suena algo?
  N.on('music_check', c => {
    S.music.check = c; renderDiag();
    if (c && !c.playing) botSays(`${c.app} abrió la búsqueda pero no le dio play solo. Toca la canción o el artista para ponerla; después «pausa» y «siguiente» los controlo yo.`, S.music.spoken);
  });
  N.on('music_state', m => {
    if (!m) return;
    const was = S.music.active;
    const st = N.STATIONS.find(x => x.id === m.station);
    Object.assign(S.music, { active: !!m.active, playing: !!m.playing, mode: m.mode || '', title: m.title || (st ? st.name : ''), station: m.station || '', desc: st ? st.desc : '' });
    if (m.event === 'error') {
      S.music.active = S.music.playing = false;
      botSays((m.failed || m.mode) === 'radio' ? 'No pude conectar con la radio. Revisa el internet e inténtalo de nuevo.' : 'No pude reproducir esa canción.', S.music.spoken);
    }
    if (was !== S.music.active) toast(S.music.active ? 'Hay música: para hablar con Luma empieza con «Luma…»' : 'Música detenida.', 3000);
    renderMusic(); renderEar();
  });
  function renderMusic() {
    const m = S.music, on = m.active;
    $('music').classList.toggle('hidden', !on);
    $('app').classList.toggle('has-music', on);
    if (!on) return;
    $('muTitle').textContent = m.title || (m.mode === 'external' ? 'App de música' : 'Música');
    $('muSub').textContent = (m.mode === 'radio' ? 'Radio · ' + (m.desc || '') : m.mode === 'external' ? 'En tu app de música' : 'De tu teléfono') + (m.playing ? '' : ' · en pausa');
    $('muPlay').textContent = m.playing ? '⏸' : '▶';
    $('muPlay').setAttribute('aria-label', m.playing ? 'Pausar' : 'Seguir');
  }
  let duckT = 0;
  function duckWindow(ms) {   // baja la música mientras te escucha después de «Luma»
    if (!S.music.active) return;
    N.musicDuck(true); clearTimeout(duckT);
    duckT = setTimeout(() => { if (!S.speaking) N.musicDuck(false); }, ms);
  }
  // ---------------- segundo plano ----------------
  function renderBg() {
    const i = N.backgroundInfo() || {};
    $('optBg').checked = S.cfg.bg;
    $('bgTxt').textContent = i.web ? 'Segundo plano: solo en el APK.'
      : i.old ? 'Actualiza la app para usar el segundo plano.'
      : `Servicio: ${i.service ? 'activo ✓' : 'apagado'} · Límite de batería: ${i.battery ? 'quitado ✓' : 'activo (Android puede cerrar la app)'}`;
    $('btnBattery').classList.toggle('hidden', !!i.battery || !!i.web);
  }

  // ---------------- escuchar (micrófono) ----------------
  // Con «Escucha permanente» el micrófono queda abierto mientras la app está en pantalla.
  // Con «Responder a todo lo que escuche» (por defecto) Luma contesta cada frase, menos su propio eco
  // y las muletillas. Si se apaga, solo actúa cuando:
  //   · dices «Luma…» (palabra de activación)  · tocaste el micrófono del chat  · modo conversación
  //   · hay una alerta y dices «estoy bien»     · dices «ayuda / auxilio / socorro» (SOS por voz)
  const ACK = /(estoy bien|estoy aqu[ií]|aqu[ií] estoy|todo bien|s[ií],? (estoy|aqu[ií])|me encuentro bien|cancela|falsa alarma|fue un error|^s[ií]$|^bien$)/i;
  const SOS = /\b(ayuda|aux[ií]lio|socorro|emergencia|me siento muy mal|me desmayo|no puedo respirar)\b/i;
  // «Luma» solo cuenta al inicio de la frase (el reconocedor a veces escribe «Luna» o «Loma»)
  const WAKE = /^\s*(?:oye|hola|hey|ey)?[\s,]*(luma|lumma|luna|loma|lumba)\b[\s,.:!¡¿?]*(.*)$/i;
  const LEVELS = new Array(140).fill(0);
  const ear = { state: 'idle', continuous: false, ondevice: false, heard: '', heardT: 0, chatUntil: 0, oneShot: false };

  function listen(purpose) {
    if (!N.listenAvailable()) { if (purpose === 'chat') toast('Este dispositivo no reconoce voz.'); return; }
    S.voice.purpose = purpose; S.voice.after = null;
    if (ear.continuous) {        // ya está escuchando: la siguiente frase va al chat
      if (purpose === 'chat') { ear.chatUntil = Date.now() + 12000; setMic(true); }
      return;
    }
    ear.oneShot = true;
    N.listenStart();
  }
  function alertActive() { return S.em.phase === 'CONFIRMING' || S.em.phase === 'SENT' || S.abs.phase !== 'OK' || S.sos.phase !== 'OK'; }
  function chatArmed() { return Date.now() < ear.chatUntil || S.voice.convo || (S.cfg.replyAll && ear.continuous); }
  function setMic(on) {
    S.voice.listening = on; $('btnMic').classList.toggle('on', on);
    if (!on) $('micLevel').style.width = '0';
    $('chatTxt').placeholder = on ? 'Te escucho…' : 'Escribe o toca el micrófono…';
  }
  function renderEar() {
    const st = ear.state, on = ear.continuous;
    const label = !on ? (S.voice.listening ? 'Escuchando una frase…' : 'Micrófono apagado')
      : st === 'paused' ? 'Luma está hablando…'
      : st === 'processing' ? 'Entendiendo…'
      : S.ai.waiting ? 'Luma está pensando…'
      : musicOn() && Date.now() >= ear.chatUntil ? 'Escuchando · hay música'
      : chatArmed() ? 'Te escucho, habla con Luma' : 'Escuchando';
    $('earState').textContent = label;
    $('earState').title = on && ear.ondevice ? 'Reconocimiento en el teléfono (sin internet)' : '';
    const fresh = Date.now() - ear.heardT < 6000;
    $('earText').textContent = fresh && ear.heard ? '«' + ear.heard + '»' + (ear.heardNote || '') : (on ? (musicOn() ? 'Hay música: di «Luma…» para hablarme · «pausa» · «siguiente»' : S.cfg.replyAll ? 'Háblame y te contesto · «ayuda» para un SOS' : 'Di «Luma…» para hablarle · «ayuda» para un SOS') : 'Toca el micrófono para que Luma te escuche siempre');
    $('btnEar').classList.toggle('on', on);
    $('btnEar').setAttribute('aria-label', on ? 'Apagar escucha permanente' : 'Encender escucha permanente');
    $('ear').classList.toggle('off', !on);
  }
  N.on('listen_mode', m => { ear.continuous = !!(m && m.continuous); ear.ondevice = !!(m && m.ondevice); D.ondevice = ear.ondevice; renderEar(); renderDiag(); });
  N.on('listen_state', st => {
    const state = (st && st.state) || 'idle';
    if (!ear.continuous && !ear.oneShot && state !== 'idle') return;   // evento atrasado de una escucha ya apagada
    ear.state = state;
    if (state === 'idle') ear.oneShot = false;
    if (!ear.continuous) setMic(ear.state === 'listening' || ear.state === 'processing');
    else setMic(chatArmed() && ear.state !== 'paused');
    renderEar();
  });
  N.on('listen_level', l => {
    const v = Math.max(0, Math.min(1, +l.v || 0));
    LEVELS.push(v); LEVELS.shift();
    D.levelMax = Math.max(D.levelMax * 0.995, v);
    $('micLevel').style.width = Math.round(v * 100) + '%';
  });
  N.on('listen_partial', p => {
    if (!p || !p.text) return;
    ear.heardNote = '';
    ear.heard = p.text; ear.heardT = Date.now();
    if (S.voice.purpose === 'chat' && (chatArmed() || !ear.continuous)) $('chatTxt').value = p.text;
  });
  N.on('listen_result', r => {
    const text = String((r && r.text) || '').trim();
    if (!text) return;
    ear.heard = text; ear.heardT = Date.now();
    handleHeard(text);
    if (!ear.continuous) setMic(false);
    renderEar();
  });
  // ¿es Luma escuchándose a sí misma? (compara con lo que acaba de decir)
  const norm = t => t.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9ñ ]/g, ' ').split(/\s+/).filter(Boolean);
  // Solo cuenta como eco si llega mientras Luma habla o hasta 5 s después, y si casi todas las
  // palabras importantes (no «que», «me», «muy»…) coinciden con lo que ella acaba de decir.
  const STOP = new Set('que como para pero porque esta este esto esos esas eres estas estoy estas tengo tiene muy mas menos algo nada todo todos bien aqui alli ahora hoy tambien solo cuando donde quien cual sobre entre hasta desde hace hacer puedo puedes quieres quiero sientes siento contigo conmigo usted ellos ellas nosotros vamos seria fuera'.split(' '));
  const content = t => norm(t).filter(w => w.length > 3 && !STOP.has(w));
  function isEcho(text) {
    const recent = Date.now() - (S.lastSpeakEnd || 0) < 5000 || S.speaking;
    if (!recent) return false;
    const heard = norm(text).join(' ');
    const w = content(text);
    if (w.length < 2) {   // frase corta: es eco solo si es un pedazo literal de lo que Luma dijo
      return heard.length >= 8 && (S.said || []).some(x => Date.now() - x.t < 30000 && norm(x.text).join(' ').includes(heard));
    }
    return (S.said || []).some(x => {
      if (Date.now() - x.t > 30000) return false;
      const said = new Set(content(x.text)), hit = w.filter(t => said.has(t)).length;
      return hit / w.length >= 0.7;
    });
  }
  const FILLER = /^(e+h*|m+|mm+|a+h+|u+h+|e+ste+|o+h+)[.!?…]*$/i;   // solo ruidos, no palabras
  function lumaAsked() {   // ¿Luma acaba de hacer una pregunta? (entonces «sí» / «no» sí cuentan)
    const h = chatHist(), last = h[h.length - 1];
    return last && last[0] === 'bot' && /\?\s*$/.test(last[1]) && Date.now() - S.lastBotT < 30000;
  }
  function handleHeard(text) {
    if (S.locked) return;
    D.lastHeard = text; D.action = 'sin acción (di «Luma…» o activa «Responder a todo»)';
    // 1) en una alerta, «estoy bien / cancela» la detiene
    if (alertActive() && ACK.test(text)) { $('chatTxt').value = ''; $('btnOk').click(); return; }
    // 2) pedir ayuda por voz
    if (SOS.test(text) && S.sos.phase === 'OK' && S.cfg.voiceSos) { sosStart(text); return; }
    // 3) mensaje para Luma: responde a todo, micrófono del chat, modo conversación o «Luma…»
    if (isEcho(text)) { diag('ignoré', 'parece mi propia voz'); return; }      // su propia voz
    // 4) con música sonando: solo controles («pausa», «siguiente»…) o frases que empiecen con «Luma…»
    if (musicOn() && Date.now() >= ear.chatUntil) {
      const mw = text.match(WAKE), body = mw ? (mw[2] || '').trim() : text, c = parseMusic(body);
      if (c && c.cmd !== 'play') { diag('contesto', ''); send(body, true); return; }
      if (!mw) { diag('ignoré', 'hay música: di «Luma…»'); return; }
      if (body.length < 2) { ear.chatUntil = Date.now() + 10000; duckWindow(10000); say('¿Sí? Te escucho.'); setMic(true); return; }
      diag('contesto', ''); duckWindow(8000); send(body, true); return;
    }
    if (S.cfg.replyAll && ear.continuous && Date.now() >= ear.chatUntil) {
      const words = norm(text);
      if (FILLER.test(text.trim()) || !words.length) { diag('ignoré', 'solo fue un ruido'); return; }
    }
    const armed = chatArmed() || (!ear.continuous && S.voice.purpose === 'chat');
    const m = text.match(WAKE);
    if (armed && m && (m[2] || '').trim().length < 2) { ear.chatUntil = Date.now() + 10000; say('¿Sí? Te escucho.'); return; }
    if (armed) { diag('contesto', ''); ear.chatUntil = 0; $('chatTxt').value = ''; S.voice.purpose = null; send(m && m[2] ? m[2] : text, true); setMic(false); return; }
    if (m) {
      const rest = (m[2] || '').trim();
      if (rest.length < 2) { ear.chatUntil = Date.now() + 10000; say('¿Sí? Te escucho.'); setMic(true); return; }
      send(rest, true);
    }
  }
  N.on('listen_error', e => {
    if (ear.continuous) { if (e && e.msg && e.code !== 7 && e.code !== 6) toast(e.msg, 5000); return; }
    setMic(false);
    if (S.voice.purpose === 'chat') {
      $('chatTxt').value = '';
      if (S.voice.convo && ++S.voice.misses >= 2) { S.voice.misses = 0; toast('Pausé el modo conversación. Toca el micrófono para seguir.'); return; }
      if (S.voice.convo && (e.code === 6 || e.code === 7 || e.code === 'no-speech')) { setTimeout(() => listen('chat'), 400); return; }
      toast(e.msg || 'No pude escucharte.');
    }
  });
  // cuando Luma termina de hablar (sin escucha permanente): escuchar la respuesta
  N.on('speak_state', st => {
    if (st) { S.speaking = !!st.speaking; if (!st.speaking) S.lastSpeakEnd = Date.now(); D.tts = st.speaking ? 'hablando' : (st.done ? 'funciona' : D.tts); }
    if (!st || !st.done) return;
    const next = S.voice.after; S.voice.after = null;
    if (ear.continuous) { if (next === 'chat') ear.chatUntil = Date.now() + 12000; return; }   // el teléfono ya reanuda solo
    if (next === 'ack' && alertActive() && S.cfg.voiceAck) setTimeout(() => listen('ack'), 300);
    else if (next === 'chat' && S.voice.convo) setTimeout(() => listen('chat'), 300);
  });
  function setListenAlways(on) {
    S.cfg.listenAlways = on; store.set('listenAlways', on);
    $('optListen').checked = on;
    N.listenContinuous(on);
    if (!on) { ear.continuous = false; ear.state = 'idle'; renderEar(); }
  }

  // ---------------- diagnóstico de voz ----------------
  const ERR = { 1: 'red lenta', 2: 'sin internet', 3: 'error de audio', 4: 'error del servidor', 5: 'error del cliente', 6: 'silencio', 7: 'no entendí',
    8: 'micrófono ocupado', 9: 'sin permiso de micrófono', 10: 'demasiadas solicitudes', 11: 'servidor desconectado', 12: 'idioma no soportado en el teléfono', 13: 'español sin conexión no instalado' };
  const D = { lastHeard: '', action: '', ev: '—', sessions: 0, ondevice: false, tts: 'sin probar', levelMax: 0 };
  function diag(what, why) { D.action = what === 'contesto' ? 'le contesté' : `${what}: ${why}`; ear.heardNote = what === 'ignoré' ? ' · ignorado (' + why + ')' : ''; renderDiag(); }
  N.on('listen_debug', d => {
    D.sessions = d.sessions; D.ondevice = d.ondevice;
    D.ev = d.ev === 'error' ? `error ${d.code} (${ERR[d.code] || '?'})` : d.ev === 'result' ? 'frase reconocida'
      : d.ev === 'partial_as_result' ? `frase reconocida (el teléfono dio error ${d.code}, usé lo que entendió)` : 'frase vacía';
    renderDiag();
  });
  function renderDiag() {
    const el = $('voiceDiag'); if (!el) return;
    const mic = N.micGranted ? (N.micGranted() ? 'sí' : 'NO — acéptalo en Ajustes › Apps › BioOrbit › Permisos') : '—';
    const lines = [
      ['Permiso de micrófono', mic],
      ['Escucha permanente', ear.continuous ? 'activa' : 'apagada'],
      ['Reconocimiento', ear.continuous ? (D.ondevice ? 'en el teléfono' : 'en línea (Google)') : '—'],
      ['Nivel de sonido', D.levelMax > 0.08 ? 'llega bien' : 'no llega (gráfica plana)'],
      ['Intentos de escucha', String(D.sessions)],
      ['Último evento', D.ev],
      ['Última frase oída', D.lastHeard ? '«' + D.lastHeard.slice(0, 60) + '»' : '—'],
      ['Qué hice', D.action || '—'],
      ['Voz de Luma', S.cfg.voice ? D.tts : 'apagada'],
      ['IA', S.ai.key ? (N.aiModel() || 'activa') : 'sin clave (respuestas básicas)'],
      ['Música', !S.music.check ? (S.music.active ? (S.music.mode === 'external' ? 'en app externa' : S.music.mode) : '—') : `${S.music.check.app}: ${S.music.check.playing ? 'sonando ✓' : 'abrió pero no dio play'}`],
    ];
    el.textContent = '';
    lines.forEach(([k, v]) => { const d = document.createElement('div'); const a = document.createElement('span'); a.textContent = k; const b = document.createElement('b'); b.textContent = v; d.append(a, b); el.appendChild(d); });
  }

  // gráfica del sonido captado (nivel del micrófono, ~20 muestras por segundo, últimos 7 s)
  const eg = $('earGraph'), ec = eg.getContext('2d');
  let egLast = 0, egVisible = true;
  if ('IntersectionObserver' in window) new IntersectionObserver(es => { egVisible = es[0].isIntersecting; }).observe(eg);
  function drawEar(ms) {
    requestAnimationFrame(drawEar);
    if (!egVisible || document.hidden || ms - egLast < 40) return;
    egLast = ms;
    const r = Math.min(devicePixelRatio || 1, 2), w = eg.clientWidth, h = eg.clientHeight;
    if (eg.width !== Math.round(w * r)) { eg.width = Math.round(w * r); eg.height = Math.round(h * r); }
    ec.setTransform(r, 0, 0, r, 0, 0); ec.clearRect(0, 0, w, h);
    const mid = h / 2, n = LEVELS.length, bw = w / n;
    ec.strokeStyle = 'rgba(143,180,217,.18)'; ec.lineWidth = 1; ec.beginPath(); ec.moveTo(0, mid); ec.lineTo(w, mid); ec.stroke();
    const live = ear.continuous || S.voice.listening, paused = ear.state === 'paused';
    for (let i = 0; i < n; i++) {
      const v = live && !paused ? LEVELS[i] : 0;
      const bh = Math.max(1.5, v * (h - 6));
      ec.fillStyle = !live ? 'rgba(143,180,217,.25)' : paused ? 'rgba(139,124,255,.45)'
        : v > 0.75 ? '#ffc857' : v > 0.4 ? '#3ef0b0' : '#38e1ff';
      ec.globalAlpha = 0.35 + 0.65 * (i / n);
      ec.fillRect(i * bw + 0.5, mid - bh / 2, Math.max(1, bw - 1.2), bh);
    }
    ec.globalAlpha = 1;
    if (paused) {   // mientras Luma habla, una onda suave
      ec.strokeStyle = '#8b7cff'; ec.lineWidth = 2; ec.beginPath();
      for (let x = 0; x <= w; x += 4) { const y = mid + Math.sin(x / 14 + ms / 140) * 6 * Math.sin(ms / 300 + x / 90); x ? ec.lineTo(x, y) : ec.moveTo(x, y); }
      ec.stroke();
    }
  }
  requestAnimationFrame(drawEar);

  // ---------------- SOS por voz ----------------
  const SOS_COUNTDOWN = 10;
  function sosStart(text) {
    const s = S.sos; s.phase = 'CONFIRM'; s.deadline = Date.now() / 1000 + SOS_COUNTDOWN; s.text = text;
    N.vibratePattern(BUZZ_WARN);
    askAck(`¿Necesitas ayuda, ${S.crew}? Aviso a la tripulación en ${SOS_COUNTDOWN} segundos. Di «cancela» si fue un error.`);
    renderEmergency(); lumaStep(Date.now() / 1000);
  }
  function sosStep(now) {
    const s = S.sos;
    if (s.phase === 'CONFIRM' && now >= s.deadline) {
      s.phase = 'SENT'; s.sent = broadcast('SOS');
      N.vibratePattern(BUZZ_SENT); N.notify('BioOrbit: SOS enviado', s.sent.message, true);
      const who = s.sent.near.map(n => n[0]).join(' y ');
      say(`Pedí ayuda. ${who ? 'Avisé a ' + who + '.' : 'No hay nadie dentro del radio.'} Quédate donde estás.`, true);
    }
  }

  // WHO-5
  function buildWho() {
    const f = $('whoForm'); f.textContent = '';
    WHO5_ITEMS.forEach((it, k) => {
      const fs = document.createElement('fieldset'), lg = document.createElement('legend');
      lg.textContent = `${k + 1}. ${it}`; fs.appendChild(lg);
      const opts = document.createElement('div'); opts.className = 'opts';
      for (let v = 0; v <= 5; v++) {
        const l = document.createElement('label'), i = document.createElement('input'), s = document.createElement('span');
        i.type = 'radio'; i.name = 'q' + k; i.value = v; s.textContent = v; l.append(i, s); opts.appendChild(l);
      }
      const scl = document.createElement('div'); scl.className = 'scale'; scl.innerHTML = '<span>En ningún momento</span><span>Todo el tiempo</span>';
      fs.append(opts, scl); f.appendChild(fs);
    });
    const b = document.createElement('button'); b.className = 'btn primary'; b.type = 'submit'; b.textContent = 'Guardar check-in';
    const w = document.createElement('div'); w.className = 'btns'; w.appendChild(b); f.appendChild(w);
  }
  function renderWhoLast() {
    const ci = S.checkins[S.crew];
    $('whoLast').textContent = ci ? `Último: ${ci.pct} % · ${WHO5_BANDS[whoLevel(ci.raw)]} (${ci.when})` : 'Últimas dos semanas · 5 preguntas de la OMS';
  }

  // respiración guiada
  let breathTimer = null;
  function breathe(on) {
    S.breath = on; $('breath').classList.toggle('hidden', !on); clearInterval(breathTimer);
    if (!on) { lumaStep(Date.now() / 1000); return; }
    const ph = [['Inhala', 1], ['Sostén', 1], ['Exhala', 0.5], ['Sostén', 0.5]]; let i = 0;
    const step = () => { const [t, s] = ph[i % 4]; $('breathTxt').textContent = t; $('breathCircle').style.transform = `scale(${s})`; i++; };
    step(); breathTimer = setInterval(step, 4000); lumaStep(Date.now() / 1000);
  }

  // ------------------------------------------------------------------ eventos
  function bind() {
    document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => showView(b.dataset.view));
    $('btnCam').onclick = startCamera;
    $('btnWatch').onclick = watchButton;
    $('btnWatchDemo').onclick = startDemoWatch;
    $('btnOk').onclick = () => {
      const now = Date.now() / 1000;
      S.em.phase = 'OK'; S.em.missing = 0; S.em.ackUntil = now + 60; S.sent = null;
      S.abs.phase = 'OK'; S.abs.sent = null; S.abs.ackUntil = now + 60; S.abs.lastSeen = now;
      S.sos.phase = 'OK'; S.sos.sent = null;
      if (S.flat) S.flat = false;
      if (window.BioCrew) BioCrew.resolved();
      N.stopSpeaking(); N.vibrate(60);
      renderEmergency(); toast('Gracias. Vuelvo a revisar en un minuto.');
      say('Gracias. Vuelvo a revisar en un minuto.');
    };
    $('optAbsence').checked = S.cfg.absence;
    $('optAbsence').onchange = e => { S.cfg.absence = e.target.checked; store.set('absence', S.cfg.absence); S.abs.lastSeen = Date.now() / 1000; };
    $('optAbsSec').value = String(S.cfg.absSec);
    $('optAbsSec').onchange = e => { S.cfg.absSec = +e.target.value; store.set('absSec', S.cfg.absSec); };
    $('optVoiceAck').checked = S.cfg.voiceAck;
    $('optVoiceAck').onchange = e => { S.cfg.voiceAck = e.target.checked; store.set('voiceAck', S.cfg.voiceAck); };
    $('optConvo').checked = S.voice.convo;
    $('optConvo').onchange = e => {
      S.voice.convo = e.target.checked; store.set('convo', S.voice.convo); S.voice.misses = 0;
      if (S.voice.convo) { toast('Modo conversación: después de cada respuesta, Luma te escucha.'); listen('chat'); }
      else if (!ear.continuous) { N.listenStop(); }
    };
    $('btnMic').onclick = () => {
      if (ear.continuous) { if (chatArmed() && !S.voice.convo) { ear.chatUntil = 0; setMic(false); } else listen('chat'); renderEar(); return; }
      if (S.voice.listening) N.listenStop(); else { S.voice.misses = 0; listen('chat'); }
    };
    $('btnEar').onclick = () => setListenAlways(!S.cfg.listenAlways);
    $('optListen').checked = S.cfg.listenAlways;
    $('optListen').onchange = e => setListenAlways(e.target.checked);
    $('optSos').checked = S.cfg.voiceSos;
    $('optSos').onchange = e => { S.cfg.voiceSos = e.target.checked; store.set('voiceSos', S.cfg.voiceSos); };
    $('btnTestVoice').onclick = () => { D.tts = 'probando… (¿la escuchaste?)'; renderDiag(); say('Hola, soy Luma. Si me escuchas, mi voz funciona.'); };
    $('optOnline').checked = store.get('online', false);
    if ($('optOnline').checked && N.listenForceOnline) N.listenForceOnline(true);
    $('optOnline').onchange = e => { store.set('online', e.target.checked); if (N.listenForceOnline) N.listenForceOnline(e.target.checked); toast(e.target.checked ? 'Uso el reconocimiento en línea de Google.' : 'Uso el reconocimiento del teléfono si está disponible.'); };
    $('muPlay').onclick = () => N.musicControl(S.music.playing ? 'pause' : 'resume');
    $('muNext').onclick = () => N.musicControl('next');
    $('muStop').onclick = () => N.musicControl('stop');
    $('optSpotify').checked = S.cfg.preferApp;
    $('optSpotify').onchange = e => { S.cfg.preferApp = e.target.checked; store.set('preferApp', S.cfg.preferApp); };
    $('optBg').onchange = e => {
      S.cfg.bg = e.target.checked; store.set('bg', S.cfg.bg); N.setBackground(S.cfg.bg);
      toast(S.cfg.bg ? 'Luma seguirá escuchando y la música sonando con la app minimizada.' : 'Al minimizar la app, Luma deja de escuchar.');
      setTimeout(renderBg, 400);
    };
    $('btnBattery').onclick = () => { N.openBatterySettings(); setTimeout(renderBg, 4000); };
    $('optReplyAll').checked = S.cfg.replyAll;
    $('optReplyAll').onchange = e => {
      S.cfg.replyAll = e.target.checked; store.set('replyAll2', S.cfg.replyAll); renderEar();
      toast(S.cfg.replyAll ? 'Luma contestará todo lo que escuche.' : 'Luma solo contestará cuando digas «Luma…».');
    };
    $('btnAiSave').onclick = () => {
      const k = $('aiKey').value.trim();
      if (!/^(AQ\.|AIza|sk-ant-)/.test(k) || k.length < 20 || /\s/.test(k)) {
        toast('Esa no parece una clave válida: las de Gemini empiezan con AQ. o AIza y las de Claude con sk-ant-.'); return;
      }
      N.aiSetKey(k); $('aiKey').value = ''; renderAI();
      toast(`Clave guardada en este teléfono. Luma ya usa ${k.startsWith('sk-ant-') ? 'Claude' : 'Gemini'}.`);
    };
    $('btnAiClear').onclick = () => { N.aiClearKey(); renderAI(); toast('Clave eliminada. Luma usa respuestas básicas.'); };
    $('optVoice').checked = S.cfg.voice;
    $('optVoice').onchange = e => {
      S.cfg.voice = e.target.checked; store.set('voice', S.cfg.voice);
      if (S.cfg.voice) say('Voz de Luma activada.'); else N.stopSpeaking();
    };
    $('btnLoss').onclick = () => { S.flat = true; toast('Simulando pérdida de signos vitales…'); };
    $('btnReset').onclick = () => { S.flat = false; toast('Sensores restablecidos.'); };
    $('btnPlay').onclick = () => { S.playing = !S.playing; $('btnPlay').textContent = S.playing ? 'Pausa' : 'Seguir'; };
    const sel = $('crewSel');
    Object.keys(ROSTER).forEach(c => { const o = document.createElement('option'); o.value = c; o.textContent = `${c} · ${ROSTER[c].role}`; sel.appendChild(o); });
    sel.value = S.crew;
    sel.onchange = () => {
      S.crew = sel.value; store.set('crew', S.crew); S.em = { phase: 'OK', missing: 0, deadline: 0, ackUntil: 0 }; S.sent = null; S.crisis = false;
      renderChat(); renderWhoLast(); tick();
    };
    $('radius').value = S.radius; $('radTxt').textContent = S.radius + ' m';
    $('radius').oninput = e => { S.radius = +e.target.value; $('radTxt').textContent = S.radius + ' m'; store.set('radius', S.radius); };
    $('chatForm').onsubmit = e => { e.preventDefault(); send($('chatTxt').value); $('chatTxt').value = ''; };
    QUICK.forEach(q => { const b = document.createElement('button'); b.type = 'button'; b.textContent = q; b.onclick = () => send(q); $('quick').appendChild(b); });
    $('btnBreath').onclick = () => breathe(true);
    $('btnBreathEnd').onclick = () => breathe(false);
    $('btnSupport').onclick = () => {
      const r = broadcast('SUPPORT'); N.vibrate(300);
      toast('Aviso enviado. Avisados: ' + (r.near.map(n => n[0]).join(', ') || 'nadie dentro del radio'));
    };
    $('btnWho').onclick = () => $('whoForm').classList.toggle('hidden');
    $('whoForm').onsubmit = e => {
      e.preventDefault();
      const ans = WHO5_ITEMS.map((_, k) => { const c = document.querySelector(`input[name=q${k}]:checked`); return c ? +c.value : null; });
      if (ans.includes(null)) { toast('Responde las 5 preguntas.'); return; }
      const raw = ans.reduce((a, b) => a + b, 0);
      S.checkins[S.crew] = { raw, pct: raw * 4, when: new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }) };
      store.set('checkins', S.checkins); $('whoForm').classList.add('hidden'); renderWhoLast(); lumaStep(Date.now() / 1000);
      toast(WHO5_BANDS[whoLevel(raw)]);
    };
    const steps = (ol) => FIRST_RESPONSE.forEach(s => { const li = document.createElement('li'); li.textContent = s; ol.appendChild(li); });
    steps($('emSteps')); steps($('stepsStatic'));
  }

  async function init() {
    bind(); buildWho(); renderWatch(); renderAlerts(); renderAI();
    try { S.data = await (await fetch('telemetry.json')).json(); }
    catch (e) { toast('No se pudo leer la telemetría: ' + e.message); return; }
    if (!S.data.crew[S.crew]) S.crew = Object.keys(S.data.crew)[0];
    renderChat(); renderWhoLast(); tick(); setInterval(tick, 1000);
    S.ready = true;
    if (S.locked) return;               // con el login abierto no arranca nada (ver setLocked)
    if (N.isAndroid) startCamera();     // en el APK se pide el permiso al abrir
    renderEar();
    N.setBackground(S.cfg.bg); renderBg(); setInterval(renderBg, 15000);
    if (S.cfg.listenAlways) N.listenContinuous(true);   // escucha permanente desde que abre la app
  }
  // estado que se manda al servidor de tripulación (lo ven los demás teléfonos y el dashboard)
  function crewStatus() {
    const r = S.row || {}, live = S.watch.state === 'live' && S.watch.bpm;
    const hr = S.status !== 'OK' ? null : live ? S.watch.bpm : (S.cam.on && rppg.bpm) ? rppg.bpm : r.heart_rate_bpm;
    const src = S.status !== 'OK' ? '' : live ? 'reloj' : (S.cam.on && rppg.bpm) ? 'cámara' : 'simulado';
    const alert = S.em.phase === 'SENT' ? 'NO_VITALS' : S.sos.phase === 'SENT' ? 'SOS' : S.abs.phase === 'SENT' ? 'NO_PRESENCE'
      : (S.em.phase === 'CONFIRMING' || S.abs.phase === 'WARN' || S.sos.phase !== 'OK') ? 'AVISO' : '';
    const num = v => (typeof v === 'number' && isFinite(v)) ? Math.round(v * 10) / 10 : null;
    return {
      hr: num(hr), hr_src: src, spo2: S.status === 'OK' ? num(r.spo2_pct) : null, temp: S.status === 'OK' ? num(r.body_temp_c) : null,
      hrv: num(r.hrv_rmssd_ms), level: S.status !== 'OK' ? 'SIN SEÑAL' : (r.alert || 'NORMAL'),
      cam: !!S.cam.on, present: S.cam.on ? !!lock.box : null, watch: !!live, alert, bg: document.hidden,
      mood: lumaS.mood || '', music: S.music.active ? (S.music.title || 'música') : '', slot: S.crew,
    };
  }
  // Pantalla de inicio de sesión abierta: solo funciona el login (sin escucha, voz, cámara, alertas ni música)
  function setLocked(on) {
    on = !!on; if (S.locked === on) return;
    S.locked = on;
    const now = Date.now() / 1000;
    if (on) {
      N.listenContinuous(false); ear.continuous = false; ear.state = 'idle';
      N.stopSpeaking();
      if (S.cam.on && video.srcObject) { video.srcObject.getTracks().forEach(t => t.stop()); S.cam.on = false; S.cam.paused = true; }
      if (S.music.active && S.music.playing) { N.musicControl('pause'); S.musicLocked = true; }
      S.em = { phase: 'OK', missing: 0, deadline: 0, ackUntil: 0 }; S.sent = null;
      S.abs.phase = 'OK'; S.abs.sent = null; S.sos.phase = 'OK'; S.sos.sent = null;
      renderEmergency(); renderEar();
    } else {
      S.abs.lastSeen = now; S.abs.ackUntil = now + 10;
      if (!S.ready) return;              // init() todavía no termina: él arranca todo
      if (S.cam.paused || (N.isAndroid && !S.cam.on)) { S.cam.paused = false; startCamera(); }
      if (S.cfg.listenAlways) N.listenContinuous(true);
      if (S.musicLocked) { S.musicLocked = false; N.musicControl('resume'); }
      renderEar();
    }
  }
  function setCrew(c) {
    if (!ROSTER[c] || c === S.crew) return;
    $('crewSel').value = c; $('crewSel').onchange();
  }
  window.BioOrbitApp = { S, startDemoWatch, send, broadcast, lock, parseMusic, crewStatus, setCrew, setLocked, say, toast, botSays, showView, ROSTER,
    meSays: t => { chatHist().push(['me', t]); saveChat(); renderChat(); } };
  init();
})();
