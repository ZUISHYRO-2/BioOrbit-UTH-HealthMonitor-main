/* Puente entre la interfaz y el teléfono.
   - Dentro del APK: Kotlin expone window.Android (Bluetooth del reloj, alertas UDP, notificaciones)
     y responde llamando BioNative.emit(evento, datos).
   - En un navegador (pruebas): Web Bluetooth para el reloj y registro en consola para las alertas.

   Eventos: watch_devices [{name,address,rssi,hr}] · watch_status {state,name,msg}
            watch_hr {bpm,rr,contact} · alert_received {payload,from} · alert_sent {ok,msg}
            music_state {event,active,playing,mode,title,station} · music_result {source,count,query,station}   */
(function () {
  const A = window.Android;
  // dentro del APK, Kotlin ya deja el espacio de las barras del sistema: no se suma otra vez en CSS
  if (A) document.documentElement.classList.add('android');
  const handlers = {};
  const HR_SERVICE = 0x180d, HR_CHAR = 0x2a37;

  function emit(ev, data) { (handlers[ev] || []).forEach(fn => { try { fn(data); } catch (e) { console.error(e); } }); }

  // Decodifica la característica Bluetooth 0x2A37 (igual que src/ble_watch.py)
  function parseHR(dv) {
    const flags = dv.getUint8(0); let i = 1, bpm;
    if (flags & 1) { bpm = dv.getUint16(i, true); i += 2; } else { bpm = dv.getUint8(i); i += 1; }
    const cbits = (flags >> 1) & 3;
    if (flags & 8) i += 2;
    const rr = [];
    if (flags & 16) for (; i + 1 < dv.byteLength; i += 2) {
      const ms = dv.getUint16(i, true) / 1024 * 1000; if (ms >= 250 && ms <= 2200) rr.push(ms);
    }
    return { bpm, rr, contact: cbits === 2 ? 'Sin contacto' : cbits === 3 ? 'Contacto firme' : 'No soportado' };
  }

  // Radios por internet (SomaFM, sin anuncios). La misma lista está en MusicPlayer.kt
  const STATIONS = [
    { id: 'groovesalad', name: 'Groove Salad', desc: 'música relajante' },
    { id: 'dronezone', name: 'Drone Zone', desc: 'ambiente tranquilo para dormir o meditar' },
    { id: 'deepspaceone', name: 'Deep Space One', desc: 'música espacial' },
    { id: 'missioncontrol', name: 'Mission Control', desc: 'música espacial con audios de la NASA' },
    { id: 'spacestation', name: 'Space Station Soma', desc: 'electrónica espacial' },
    { id: 'indiepop', name: 'Indie Pop Rocks', desc: 'pop e indie' },
    { id: 'poptron', name: 'PopTron', desc: 'electropop para bailar' },
    { id: 'bagel', name: 'BAGeL Radio', desc: 'rock alternativo' },
    { id: 'u80s', name: 'Underground 80s', desc: 'música de los ochenta' },
    { id: 'seventies', name: 'Left Coast 70s', desc: 'música de los setenta' },
    { id: 'sonicuniverse', name: 'Sonic Universe', desc: 'jazz' },
    { id: 'folkfwd', name: 'Folk Forward', desc: 'folk y acústica' },
    { id: 'secretagent', name: 'Secret Agent', desc: 'música de misterio' },
    { id: 'dubstep', name: 'Dub Step Beyond', desc: 'dubstep' },
  ];

  let webDev = null;
  const web = {
    async watchScan() {
      if (!navigator.bluetooth) {
        emit('watch_status', { state: 'error', msg: 'Este navegador no tiene Bluetooth. Usa el APK o «Demo».' });
        return;
      }
      try {
        emit('watch_status', { state: 'scanning', msg: 'Elige tu reloj en la lista…' });
        webDev = await navigator.bluetooth.requestDevice({ filters: [{ services: [HR_SERVICE] }] });
        await web.watchConnect();
      } catch (e) { emit('watch_status', { state: 'off', msg: 'Búsqueda cancelada: ' + e.message }); }
    },
    async watchConnect() {
      if (!webDev) return;
      const name = webDev.name || 'Reloj';
      emit('watch_status', { state: 'connecting', name, msg: 'Conectando a ' + name + '…' });
      webDev.addEventListener('gattserverdisconnected', () =>
        emit('watch_status', { state: web._manual ? 'off' : 'lost', name, msg: web._manual ? 'Reloj desconectado.' : 'Se perdió la conexión con el reloj.' }));
      web._manual = false;
      const srv = await webDev.gatt.connect();
      const ch = await (await srv.getPrimaryService(HR_SERVICE)).getCharacteristic(HR_CHAR);
      ch.addEventListener('characteristicvaluechanged', e => emit('watch_hr', parseHR(e.target.value)));
      await ch.startNotifications();
      emit('watch_status', { state: 'connected', name, msg: 'Conectado a ' + name });
    },
    watchDisconnect() { web._manual = true; if (webDev && webDev.gatt.connected) webDev.gatt.disconnect(); else emit('watch_status', { state: 'off', msg: 'Reloj desconectado.' }); },
    sendAlert(p) { console.log('[BioOrbit] Alerta (sin red en navegador):', p); emit('alert_sent', { ok: false, msg: 'En el navegador no se envía por la red (solo en el APK).' }); },
    notify(title, text) { console.log('[BioOrbit]', title, text); },
    vibrate(ms) { if (navigator.vibrate) navigator.vibrate(ms); },
    vibratePattern(p) { if (navigator.vibrate) navigator.vibrate(p); },
    speak(text) {
      if (!window.speechSynthesis) return;
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text); u.lang = 'es-MX'; u.rate = 1.0;
      const v = speechSynthesis.getVoices().find(x => /^es/i.test(x.lang)); if (v) u.voice = v;
      if (web._cont) { web._paused = true; if (web._crec) { const r = web._crec; web._crec = null; r.abort(); } emit('listen_state', { state: 'paused' }); }
      const resume = () => { if (web._paused) { web._paused = false; if (web._cont && web._loop) setTimeout(web._loop, 300); } };
      u.onstart = () => emit('speak_state', { speaking: true });
      u.onend = () => { emit('speak_state', { speaking: false, done: true }); resume(); };
      u.onerror = () => emit('speak_state', { speaking: false });
      speechSynthesis.speak(u);
    },
    stopSpeaking() { if (window.speechSynthesis) speechSynthesis.cancel(); },
    listenAvailable() { return !!(window.SpeechRecognition || window.webkitSpeechRecognition); },
    listenStart() {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { emit('listen_error', { code: -1, msg: 'Este navegador no reconoce voz. Usa el APK.' }); return; }
      if (window.speechSynthesis) speechSynthesis.cancel();
      const r = new SR(); web._rec = r; r.lang = 'es-MX'; r.interimResults = true; r.maxAlternatives = 1;
      let final = '';
      r.onstart = () => emit('listen_state', { state: 'listening' });
      r.onresult = e => {
        let t = ''; for (const res of e.results) { t += res[0].transcript; if (res.isFinal) final = t; }
        emit('listen_partial', { text: t });
      };
      r.onerror = e => emit('listen_error', { code: e.error, msg: e.error === 'no-speech' ? 'No te escuché. Toca el micrófono y habla de nuevo.' : 'No pude reconocer la voz: ' + e.error });
      r.onend = () => { if (final) emit('listen_result', { text: final }); emit('listen_state', { state: 'idle' }); };
      r.start();
    },
    listenStop() { web.listenContinuous(false); if (web._rec) web._rec.abort(); emit('listen_state', { state: 'idle' }); },
    async listenContinuous(on) {
      web._cont = !!on;
      if (!on) {
        clearInterval(web._lvl); if (web._stream) web._stream.getTracks().forEach(t => t.stop()); web._stream = null;
        if (web._crec) { const r = web._crec; web._crec = null; r.abort(); }
        emit('listen_mode', { continuous: false, ondevice: false }); emit('listen_state', { state: 'idle' }); return;
      }
      try {   // nivel de sonido para la gráfica
        web._stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const ctx = new (window.AudioContext || window.webkitAudioContext)(), an = ctx.createAnalyser();
        an.fftSize = 512; ctx.createMediaStreamSource(web._stream).connect(an);
        const buf = new Float32Array(an.fftSize);
        web._lvl = setInterval(() => {
          an.getFloatTimeDomainData(buf); let s = 0; for (const x of buf) s += x * x;
          const db = 20 * Math.log10(Math.sqrt(s / buf.length) + 1e-6);          // -60..0 dBFS
          emit('listen_level', { v: Math.max(0, Math.min(1, (db + 55) / 45)) });
        }, 50);
      } catch (e) { emit('listen_error', { code: -3, msg: 'Sin permiso del micrófono: ' + e.message }); }
      emit('listen_mode', { continuous: true, ondevice: false });
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { emit('listen_state', { state: 'listening' }); return; }
      const loop = () => {
        if (!web._cont || web._paused) return;
        const r = new SR(); web._crec = r; r.lang = 'es-MX'; r.continuous = true; r.interimResults = true;
        r.onstart = () => emit('listen_state', { state: 'listening' });
        r.onresult = e => {
          const res = e.results[e.results.length - 1];
          if (res.isFinal) emit('listen_result', { text: res[0].transcript }); else emit('listen_partial', { text: res[0].transcript });
        };
        r.onend = () => { if (web._crec === r) setTimeout(loop, 250); };
        r.onerror = () => {};
        try { r.start(); } catch (e) { setTimeout(loop, 1000); }
      };
      web._loop = loop;
      loop();
    },
    // música en el navegador: solo radio por internet (la del teléfono y Spotify solo en el APK)
    musicPlay(query, station, generic) {
      const st = station || (generic ? 'groovesalad' : '');
      if (!st) { emit('music_result', { source: 'none', count: 0, query, station }); return; }
      const info = STATIONS.find(x => x.id === st) || STATIONS[0];
      if (!web._au) { web._au = new Audio(); web._au.onerror = () => { web._mus = null; emit('music_state', { event: 'error', active: false, playing: false, mode: 'radio', title: '', station: '' }); }; }
      web._au.src = 'https://ice1.somafm.com/' + info.id + '-128-mp3'; web._au.volume = 1;
      web._mus = { mode: 'radio', title: info.name, station: info.id, playing: true };
      web._au.play().catch(() => {});
      emit('music_result', { source: station ? 'radio' : 'radio_fallback', count: 0, query, station: info.id });
      web._musEmit('started');
    },
    musicControl(cmd) {
      const m = web._mus, a = web._au; if (!m || !a) { emit('music_state', { event: 'stopped', active: false, playing: false, mode: '', title: '', station: '' }); return; }
      if (cmd === 'pause') { a.pause(); m.playing = false; web._musEmit('paused'); }
      else if (cmd === 'resume') { a.play().catch(() => {}); m.playing = true; web._musEmit('resumed'); }
      else if (cmd === 'next') { const i = STATIONS.findIndex(x => x.id === m.station); web.musicPlay('', STATIONS[(i + 1) % STATIONS.length].id, false); }
      else if (cmd === 'stop') { a.pause(); a.removeAttribute('src'); web._mus = null; emit('music_state', { event: 'stopped', active: false, playing: false, mode: '', title: '', station: '' }); }
      else if (cmd === 'up' || cmd === 'down') { a.volume = Math.max(0.1, Math.min(1, a.volume + (cmd === 'up' ? 0.2 : -0.2))); web._musEmit('volume'); }
    },
    musicDuck(on) { if (web._au && web._mus) web._au.volume = on ? 0.2 : 1; },
    _musEmit(ev) { const m = web._mus; emit('music_state', { event: ev, active: !!m, playing: !!(m && m.playing), mode: m ? m.mode : '', title: m ? m.title : '', station: m ? m.station : '' }); },
    musicStations() { return STATIONS; },
    serverFound() { return ''; },
    setBackground() {}, backgroundInfo() { return { on: false, service: false, battery: false, web: true }; }, openBatterySettings() {},
    aiHasKey() { return false; }, aiSetKey() {}, aiClearKey() {}, aiModel() { return ''; },
    aiChat(id) { emit('ai_error', { id, msg: 'La IA solo funciona dentro del APK.' }); },
  };

  const native = A ? {
    watchScan: () => A.watchScan(),
    watchConnect: addr => A.watchConnect(addr),
    watchDisconnect: () => A.watchDisconnect(),
    sendAlert: p => A.sendAlert(JSON.stringify(p)),
    notify: (title, text, urgent) => A.showNotification(title, text, !!urgent),
    vibrate: ms => A.vibrate(ms | 0),
    // (si el APK es de una versión anterior sin estas funciones, no truena)
    vibratePattern: p => (A.vibratePattern ? A.vibratePattern(p.join(',')) : A.vibrate(p.reduce((x, y) => x + y, 0))),
    speak: (text, urgent) => A.speak && A.speak(String(text).slice(0, 400), !!urgent),
    stopSpeaking: () => A.stopSpeaking && A.stopSpeaking(),
    listenAvailable: () => !!A.listenStart,
    listenStart: () => A.listenStart && A.listenStart(),
    listenStop: () => A.listenStop && A.listenStop(),
    listenForceOnline: on => A.listenForceOnline && A.listenForceOnline(!!on),
    micGranted: () => (A.micGranted ? A.micGranted() : true),
    listenContinuous: on => (A.listenContinuous ? A.listenContinuous(!!on) : emit('listen_error', { code: -4, msg: 'Actualiza la app para la escucha permanente.' })),
    musicPlay: (q, st, generic, opts) => A.musicPlay2 ? A.musicPlay2(String(q || ''), String(st || ''), !!generic, JSON.stringify(opts || {})) : (A.musicPlay ? A.musicPlay(String(q || ''), String(st || ''), !!generic) : emit('music_result', { source: 'old', count: 0, query: q, station: st })),
    musicControl: cmd => A.musicControl && A.musicControl(String(cmd)),
    musicDuck: on => A.musicDuck && A.musicDuck(!!on),
    musicStations: () => { try { return A.musicStations ? JSON.parse(A.musicStations()) : STATIONS; } catch (e) { return STATIONS; } },
    serverFound: () => { try { return A.serverFound ? A.serverFound() : ''; } catch (e) { return ''; } },
    setBackground: on => A.setBackground && A.setBackground(!!on),
    backgroundInfo: () => { try { return A.backgroundInfo ? JSON.parse(A.backgroundInfo()) : { on: false, service: false, battery: false, old: true }; } catch (e) { return { on: false, service: false, battery: false }; } },
    openBatterySettings: () => A.openBatterySettings && A.openBatterySettings(),
    aiHasKey: () => !!(A.aiHasKey && A.aiHasKey()),
    aiSetKey: k => A.aiSetKey && A.aiSetKey(String(k)),
    aiClearKey: () => A.aiClearKey && A.aiClearKey(),
    aiModel: () => (A.aiModel ? A.aiModel() : ''),
    aiChat: (id, system, messages) => (A.aiChat ? A.aiChat(id, system, JSON.stringify(messages)) : emit('ai_error', { id, msg: 'Actualiza la app para usar la IA.' })),
  } : web;

  let id = '';
  try { id = A ? A.deviceId() : (localStorage.getItem('bio_id') || ''); } catch (e) { /* sin almacenamiento */ }
  if (!id) { id = 'web-' + Math.random().toString(36).slice(2, 10); try { localStorage.setItem('bio_id', id); } catch (e) { /* */ } }

  window.BioNative = Object.assign({
    isAndroid: !!A, deviceId: id, parseHR, STATIONS,
    on(ev, fn) { (handlers[ev] = handlers[ev] || []).push(fn); },
    emit(ev, data) { emit(ev, typeof data === 'string' ? JSON.parse(data) : data); },
  }, native);
})();
