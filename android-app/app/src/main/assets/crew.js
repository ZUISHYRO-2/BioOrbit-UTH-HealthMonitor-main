/* BioOrbit · Tripulación: cuentas de astronautas, estado compartido y chat interno.
   Habla con crew_server/server.py (en la PC del control de misión):
   - mismo Wi-Fi: el servidor se anuncia solo (UDP 50506) y el teléfono lo encuentra
   - datos móviles: dirección https del túnel (se aprende sola o se escribe a mano)
   Cada ~2 s manda el estado de este teléfono y recibe la tripulación, mensajes y alertas. */
(() => {
  'use strict';
  const N = window.BioNative, A = window.BioOrbitApp;
  if (!N || !A) return;
  const S = A.S, $ = id => document.getElementById(id);
  const K = 'bo_crew_';
  const store = {
    get(k, d) { try { const v = localStorage.getItem(K + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(K + k, JSON.stringify(v)); } catch (e) { /* sin espacio */ } },
    del(k) { try { localStorage.removeItem(K + k); } catch (e) { /* */ } },
  };
  const C = {
    token: store.get('token', ''), user: store.get('user', null), offline: store.get('offline', false),
    manual: store.get('server', ''), lan: '', lanAt: 0, base: '', online: false, fails: 0, lastOk: 0,
    crew: [], msgs: store.get('msgs', []), since: store.get('since', 0), alerts: new Map(),
    seenAlerts: new Set(store.get('seenAlerts', [])), chan: '', unread: store.get('unread', {}),
    serverId: store.get('serverId', ''), view: '', readAloud: store.get('readAloud', true), first: true, wasAlert: '', pending: [], timer: 0, mode: 'in',
  };
  const KIND = { NO_VITALS: 'Sin signos vitales', NO_PRESENCE: 'No aparece en cámara', SOS: 'SOS por voz', SUPPORT: 'Pide apoyo humano', AVISO: 'Aviso en curso' };
  const LEVEL = { NORMAL: ['Estable', 'var(--ok)'], 'PRECAUCIÓN': ['Precaución', 'var(--wa)'], 'CRÍTICO': ['Crítico', 'var(--cr)'], 'SIN SEÑAL': ['Sin señal', 'var(--cr)'] };
  const plain = t => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const fmtT = ts => new Date(ts * 1000).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
  const logged = () => !!(C.token && C.user);

  // ------------------------------------------------------------------ dirección del servidor
  function normUrl(u) {
    u = String(u || '').trim().replace(/\s+/g, '');
    if (!u) return '';
    if (!/^https?:\/\//i.test(u)) u = (/^[\d.]+(:\d+)?$/.test(u) || /^localhost/i.test(u) ? 'http://' : 'https://') + u;
    try {
      const x = new URL(u);
      if (x.protocol === 'http:' && !x.port && (/^[\d.]+$/.test(x.hostname) || x.hostname === 'localhost')) x.port = '8765';   // IP sin puerto -> 8765
      return x.origin;
    } catch (e) { return ''; }
  }
  function candidates() {
    const out = [];
    if (C.lan && Date.now() - C.lanAt < 120000) out.push(C.lan);
    if (C.manual) out.push(C.manual);
    if (C.lan) out.push(C.lan);
    return [...new Set(out)];
  }
  async function ping(base) {
    try {
      const r = await fetchT(base + '/api/ping', { method: 'GET' }, 4000);
      const j = await r.json(); return j && j.app === 'bioorbit-crew' ? j : null;
    } catch (e) { return null; }
  }
  function fetchT(url, opt, ms) {
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
    return fetch(url, Object.assign({ signal: ctl.signal, cache: 'no-store' }, opt)).finally(() => clearTimeout(t));
  }
  async function api(path, body, base) {
    base = base || C.base;
    if (!base) throw new Error('Sin servidor');
    const r = await fetchT(base + path, {
      method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, C.token ? { Authorization: 'Bearer ' + C.token } : {}),
      body: JSON.stringify(body || {}),
    }, 8000);
    const j = await r.json().catch(() => ({ ok: false, error: 'Respuesta inválida del servidor' }));
    if (!j.ok) { const e = new Error(j.error || 'Error ' + r.status); e.status = r.status; throw e; }
    return j;
  }
  // busca un servidor que conteste (primero el del Wi-Fi, luego el de datos móviles)
  async function pickServer() {
    for (const b of candidates()) { if (await ping(b)) { C.base = b; return b; } }
    return '';
  }

  N.on('server_found', d => {
    if (!d || !d.url) return;
    const fresh = C.lan !== d.url;
    C.lan = d.url; C.lanAt = Date.now();
    if (!C.online) C.base = d.url;
    if (fresh) renderAuthSrv();
  });

  // ------------------------------------------------------------------ sincronización
  function schedule(ms) { clearTimeout(C.timer); C.timer = setTimeout(sync, ms); }
  async function sync() {
    if (!logged()) return;
    const every = document.hidden ? 5000 : 2000;
    if (!C.base && !(await pickServer())) { setOnline(false, 'Buscando el servidor…'); return schedule(5000); }
    let j;
    try {
      j = await api('/api/sync', { status: A.crewStatus(), since_msg: C.since, device: N.deviceId });
    } catch (e) {
      if (e.status === 401) { sessionExpired(); return; }
      C.fails++;
      if (C.fails >= 2) { setOnline(false, 'Sin conexión con el servidor · reintentando'); C.base = ''; }
      return schedule(C.fails > 5 ? 8000 : 3000);
    }
    C.fails = 0; C.lastOk = Date.now(); setOnline(true);
    // ¿otra base de datos en el servidor (se borró o cambió)? -> tirar el caché del chat y bajarlo completo
    const sid = j.server_id || '', last = Number(j.last_msg_id || 0);
    // (sin serverId guardado = viene de una versión anterior de la app: también se limpia una vez)
    if ((sid && sid !== C.serverId) || last < C.since) {
      C.serverId = sid; store.set('serverId', sid); resetCache();
      return schedule(0);
    }
    if (j.public && j.public !== C.manual && /^https:\/\//.test(j.public)) { C.manual = j.public; store.set('server', C.manual); }
    C.user = Object.assign({}, C.user, j.me); store.set('user', C.user);
    C.crew = j.crew || [];
    onMessages(j.messages || []);
    onAlerts(j.alerts || []);
    flushPending();
    trackOwnAlert();
    C.first = false;
    render();
    schedule(every);
  }
  function resetCache() {
    C.msgs = []; C.since = 0; C.unread = {}; C.seenAlerts = new Set(); C.alerts = new Map(); C.first = true;
    store.set('msgs', []); store.set('since', 0); store.set('unread', {}); store.set('seenAlerts', []);
  }
  function setOnline(on, why) {
    const was = C.online; C.online = on;
    const sub = $('srvSub'); if (!sub) return;
    sub.textContent = on ? `Conectado · ${C.crew.filter(c => c.online).length} en línea · ${C.msgs.length} mensajes · al día ${new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}` : (why || 'Sin conexión');
    $('srvDot').classList.toggle('on', on);
    $('srvUrl').textContent = C.base || C.manual || C.lan || '—';
    if (was && !on && !C.first) A.toast('Se perdió la conexión con el servidor de tripulación.');
  }
  function sessionExpired() {
    C.token = ''; store.del('token'); C.online = false;
    A.toast('Tu sesión venció: vuelve a iniciar sesión.', 5000);
    showAuth('in');
  }

  // ------------------------------------------------------------------ mensajes
  function nameOf(u, short) {
    if (!u) return 'Todos';
    if (u === 'control') return 'Control de misión';
    if (C.user && u === C.user.username) return 'Tú';
    const c = C.crew.find(x => x.username === u);
    return c ? (short ? c.name.split(' ')[0] : `${c.name} (${c.callsign})`) : u;
  }
  function chanOf(m) { if (!m.to) return ''; return m.from === C.user.username ? m.to : m.from; }
  function onMessages(list) {
    if (!list.length) return;
    const me = C.user.username;
    for (const m of list) {
      if (C.msgs.some(x => x.id === m.id)) continue;
      C.msgs.push(m); C.since = Math.max(C.since, m.id);
      if (C.first || m.from === me) continue;
      const ch = chanOf(m), looking = C.view === 'crew' && C.chan === ch && !document.hidden;
      if (!looking) C.unread[ch] = (C.unread[ch] || 0) + 1;
      if (Date.now() / 1000 - m.ts < 120) announce(m);     // los viejos (app cerrada) solo se marcan sin leer
    }
    C.msgs = C.msgs.slice(-300);
    store.set('msgs', C.msgs); store.set('since', C.since); store.set('unread', C.unread);
  }
  function announce(m) {
    const who = nameOf(m.from, true), priv = m.to ? ' (privado)' : '';
    if (document.hidden) N.notify(`💬 ${nameOf(m.from)}${priv}`, m.text, false);
    else if (C.view !== 'crew') A.toast(`💬 ${who}: ${m.text.slice(0, 90)}`, 4500);
    N.vibrate(70);
    if (C.readAloud && S.cfg.voice && !(S.em.phase !== 'OK' || S.sos.phase !== 'OK' || S.abs.phase !== 'OK'))
      A.say(`Mensaje${priv ? ' privado' : ''} de ${who}: ${m.text.slice(0, 220)}`);
  }
  async function sendMsg(text, to) {
    text = String(text || '').trim(); if (!text) return false;
    const m = { text, to: to || '' };
    try { const j = await api('/api/chat', m); C.msgs.push(j.message); C.since = Math.max(C.since, j.message.id); store.set('msgs', C.msgs); renderLog(); return true; }
    catch (e) { if (e.status === 401) sessionExpired(); else A.toast('No se envió: ' + (C.online ? e.message : 'sin conexión con el servidor')); return false; }
  }

  // ------------------------------------------------------------------ alertas
  function onAlerts(list) {
    const me = C.user.username;
    for (const a of list) {
      C.alerts.set(a.id, a);
      if (C.seenAlerts.has(a.id)) continue;
      C.seenAlerts.add(a.id);
      if (C.first || a.username === me || a.resolved) continue;
      const who = C.crew.find(c => c.username === a.username);
      // mismo camino que una alerta del Wi-Fi: lista de alertas, vibración y voz de Luma
      N.emit('alert_received', { from: 'servidor', payload: { kind: a.kind, message: a.message, crew: who ? who.callsign : a.username, origin: 'srv' } });
    }
    store.set('seenAlerts', [...C.seenAlerts].slice(-200));
  }
  // si mi alerta se apagó sola («estoy aquí» por voz, volvió el pulso…), avisar que ya estoy bien
  function trackOwnAlert() {
    const st = A.crewStatus().alert, real = ['NO_VITALS', 'SOS', 'NO_PRESENCE'].includes(st) ? st : '';
    if (C.wasAlert && !real) resolved();
    C.wasAlert = real;
  }
  function resolved() {
    if (!logged()) return;
    api('/api/alert', { kind: 'RESOLVED' }).catch(() => C.pending.push(['/api/alert', { kind: 'RESOLVED' }]));
  }
  function alert(kind, message) {
    if (!logged()) return;
    const body = { kind, message };
    api('/api/alert', body).catch(() => C.pending.push(['/api/alert', body]));   // se reintenta al volver la conexión
  }
  function flushPending() {
    const p = C.pending.splice(0, C.pending.length);
    p.forEach(([path, body]) => api(path, body).catch(() => C.pending.push([path, body])));
  }
  async function ackAlert(a, text) {
    try { await api('/api/alert_ack', { id: a.id, text }); A.toast('Avisé a la tripulación: ' + text); sync(); }
    catch (e) { A.toast('No se pudo avisar: ' + e.message); }
  }

  // ------------------------------------------------------------------ voz: «dile a Ana que…», «manda mensaje a la tripulación: …»
  const MSG_RES = [
    /^(?:luma[\s,]+)?(?:manda(?:le)?|m[aá]ndale|env[ií]a(?:le)?|escr[ií]be(?:le)?)\s+(?:un\s+)?(?:mensaje|recado|aviso)\s+(?:a|para)\s+(.+?)(?:\s*[:,]\s*|\s+que\s+|\s+diciendo\s+)(.+)$/i,
    /^(?:luma[\s,]+)?(?:dile|av[ií]sale|d[ií]gale)\s+a\s+(.+?)\s+que\s+(.+)$/i,
    /^(?:luma[\s,]+)?(?:mensaje|aviso)\s+(?:a|para)\s+(.+?)\s*[:,]\s*(.+)$/i,
  ];
  function findTarget(raw) {
    const t = plain(raw).replace(/^(el|la|los|las)\s+/, '');
    if (/^(tripulacion|todos|todas|todo el equipo|equipo|la tripulacion|los demas|la mision|todo mundo)$/.test(t)) return { to: '', label: 'toda la tripulación' };
    if (/^(control|control de mision|tierra|houston|la base|base)$/.test(t)) return { to: 'control', label: 'control de misión' };
    const words = t.split(/\s+/);
    const c = C.crew.find(x => plain(x.callsign) === t || plain(x.callsign).replace('-', ' ') === t || plain(x.username) === t)
      || C.crew.find(x => plain(x.name) === t)
      || C.crew.find(x => plain(x.name).split(/\s+/)[0] === words[0]);
    return c ? { to: c.username, label: c.name.split(' ')[0] } : null;
  }
  function voiceCommand(text, spoken) {
    const say = t => A.botSays(t, spoken);
    // «¿tengo mensajes?», «lee mis mensajes»
    if (/\b(lee(me)?|leer|tengo|hay)\b.*\bmensajes?\b/.test(plain(text)) && !/\b(manda|envia|dile)\b/.test(plain(text))) {
      A.meSays(text);
      if (!logged()) { say('Primero inicia sesión en la pestaña Equipo.'); return true; }
      const unread = Object.values(C.unread).reduce((a, b) => a + b, 0);
      const last = C.msgs.filter(m => m.from !== C.user.username).slice(-Math.max(1, Math.min(3, unread || 1)));
      if (!last.length) { say('No tienes mensajes de la tripulación.'); return true; }
      say((unread ? `Tienes ${unread} sin leer. ` : 'El último: ') + last.map(m => `${nameOf(m.from, true)} dice: ${m.text}`).join('. '));
      C.unread = {}; store.set('unread', C.unread); renderBadge();
      return true;
    }
    let m = null;
    for (const re of MSG_RES) { m = String(text).trim().match(re); if (m) break; }
    if (!m) return false;
    A.meSays(text);
    if (!logged()) { say('Para mandar mensajes primero inicia sesión en la pestaña Equipo.'); return true; }
    const tg = findTarget(m[1]);
    if (!tg) { say(`No encontré a «${m[1]}» en la tripulación. Puedes decir su nombre o «la tripulación».`); return true; }
    const body = m[2].trim().replace(/^[«"]|[»"]$/g, '');
    sendMsg(body.charAt(0).toUpperCase() + body.slice(1), tg.to).then(ok => say(ok ? `Listo, le mandé a ${tg.label}: «${body}».` : 'No pude mandarlo, no hay conexión con el servidor.'));
    return true;
  }

  // ------------------------------------------------------------------ pantalla de inicio de sesión
  function showAuth(mode) {
    C.mode = mode || C.mode || 'in';
    $('auth').classList.remove('hidden');
    A.setLocked(true);                          // en el login solo funciona el login
    $('aSrv').value = $('aSrv').value || C.manual || C.lan || '';
    renderAuth();
  }
  function hideAuth() { $('auth').classList.add('hidden'); A.setLocked(false); }
  function renderAuth() {
    const up = C.mode === 'up';
    $('authIn').classList.toggle('on', !up); $('authUp').classList.toggle('on', up);
    $('aUpOnly').classList.toggle('hidden', !up);
    $('aGo').textContent = up ? 'Crear cuenta' : 'Entrar';
    $('aPass').autocomplete = up ? 'new-password' : 'current-password';
    $('aErr').textContent = '';
    renderAuthSrv();
  }
  function renderAuthSrv() {
    const box = $('aSrvState'); if (!box) return;
    if (!$('aSrv').value && C.lan) $('aSrv').value = C.lan;
    box.textContent = C.lan ? `✓ Servidor encontrado en el Wi-Fi: ${C.lan}` : 'Buscando el servidor en el Wi-Fi… (con datos móviles escribe la dirección https)';
    box.style.color = C.lan ? 'var(--ok)' : '';
  }
  async function submitAuth(e) {
    e.preventDefault();
    const up = C.mode === 'up', err = $('aErr'), go = $('aGo');
    const base = normUrl($('aSrv').value);
    if (!base) { err.textContent = 'Escribe la dirección del servidor (la muestra la ventana del servidor en la PC).'; return; }
    const body = { username: $('aUser').value.trim().toLowerCase(), password: $('aPass').value };
    if (up) {
      const slot = $('aSlot').value, r = A.ROSTER[slot] || {};
      Object.assign(body, { name: $('aName').value.trim(), callsign: slot, role: r.role || 'Astronauta', module: r.module || 'Hábitat' });
      if (!body.name) { err.textContent = 'Escribe tu nombre.'; return; }
    }
    if (!body.username || !body.password) { err.textContent = 'Escribe usuario y contraseña.'; return; }
    go.disabled = true; err.textContent = ''; err.style.color = 'var(--mu)'; err.textContent = 'Conectando…';
    try {
      if (!(await ping(base))) throw new Error(`No hay servidor BioOrbit en ${base}. ¿Está abierto server.py en la PC y estás en el mismo Wi-Fi?`);
      const j = await api(up ? '/api/register' : '/api/login', body, base);
      if (j.user.kind !== 'astronauta') throw new Error('La cuenta «control» es para el dashboard de la PC. Crea una cuenta de astronauta.');
      C.token = j.token; C.user = j.user; C.base = base; C.offline = false;
      if (base !== C.lan) { C.manual = base; store.set('server', base); }
      store.set('token', C.token); store.set('user', C.user); store.set('offline', false);
      resetCache();                         // al entrar se baja el chat completo del servidor
      store.set('lastUser', C.user.username);
      $('aPass').value = ''; hideAuth(); applyUser(); C.first = true; sync();
      A.toast(up ? `Cuenta creada. Bienvenido, ${C.user.name.split(' ')[0]}.` : `Hola, ${C.user.name.split(' ')[0]}.`);
    } catch (e2) {
      err.style.color = 'var(--cr)'; err.textContent = e2.name === 'AbortError' ? 'El servidor no contestó a tiempo.' : (e2.message === 'Failed to fetch' ? 'No me pude conectar a ' + base : e2.message);
    } finally { go.disabled = false; }
  }
  function applyUser() {
    if (!logged()) return;
    A.setCrew(C.user.callsign);
    const sel = $('crewSel'); sel.disabled = true; sel.title = 'Lo define tu cuenta';
    $('meName').textContent = `${C.user.name} · ${C.user.callsign}`;
    render();
  }
  function logout() {
    if (!confirm('¿Cerrar sesión en este teléfono?')) return;
    api('/api/logout').catch(() => {});
    C.token = ''; C.user = null; C.online = false; C.crew = []; clearTimeout(C.timer);
    store.del('token'); store.del('user');
    $('crewSel').disabled = false;
    render(); showAuth('in');
  }

  // ------------------------------------------------------------------ pestaña Equipo
  function render() {
    renderBadge();
    const on = logged();
    $('crewOut').classList.toggle('hidden', on); $('crewIn').classList.toggle('hidden', !on);
    if (!on) return;
    $('meName').textContent = `${C.user.name} · ${C.user.callsign}`;
    $('srvUrl').textContent = C.base || C.manual || C.lan || '—';
    if (C.view !== 'crew') return;          // no redibujar lo que no se ve
    renderList(); renderOpenAlerts(); renderChans(); renderLog();
  }
  function renderBadge() {
    const n = Object.values(C.unread).reduce((a, b) => a + b, 0);
    const open = [...C.alerts.values()].some(a => !a.resolved && C.user && a.username !== C.user.username);
    $('crewDot').classList.toggle('hidden', !(n || open));
  }
  function renderList() {
    const box = $('crewList'); box.textContent = '';
    const others = C.crew.filter(c => c.username !== C.user.username);
    if (!others.length) { box.append(el('div', 'empty', 'Todavía no hay más astronautas. Cada quien crea su cuenta en su teléfono.')); return; }
    const open = [...C.alerts.values()].filter(a => !a.resolved);
    for (const c of others) {
      const s = c.status || {}, alarm = open.some(a => a.username === c.username);
      const [lv, col] = !c.online ? ['Desconectado', 'var(--mu)'] : (LEVEL[s.level] || LEVEL.NORMAL);
      const row = el('button', 'mate' + (c.online ? '' : ' off') + (alarm ? ' alarm' : ''));
      row.type = 'button'; row.style.setProperty('--c', alarm ? 'var(--cr)' : col);
      const av = el('span', 'av', (c.callsign || '?').replace(/[^A-Z0-9]/gi, '').slice(-2)); av.append(el('i', c.online ? 'on' : ''));
      const info = el('span', 'mi');
      info.append(el('b', '', c.name));
      const bits = [c.callsign, c.role];
      if (c.online) {
        if (s.alert && KIND[s.alert]) bits.unshift('⚠ ' + KIND[s.alert]);
        else bits.push(s.cam ? (s.present ? 'en cámara' : 'no está en cámara') : 'cámara apagada');
      } else bits.push('desconectado');
      info.append(el('small', '', bits.join(' · ')));
      const hr = el('span', 'mh'); hr.append(el('b', '', c.online && s.hr != null ? Math.round(s.hr) : '—')); hr.append(el('small', '', alarm ? 'ALERTA' : lv));
      row.append(av, info, hr);
      row.onclick = () => { C.chan = c.username; C.unread[c.username] = 0; store.set('unread', C.unread); renderChans(); renderLog(); renderBadge(); $('crewMsg').focus(); };
      box.append(row);
    }
  }
  function renderOpenAlerts() {
    const box = $('crewAlerts'); box.textContent = '';
    const list = [...C.alerts.values()].filter(a => !a.resolved && a.username !== C.user.username).sort((a, b) => b.ts - a.ts);
    for (const a of list) {
      const d = el('div', 'banner crit crew-al');
      d.append(el('b', '', `${KIND[a.kind] || a.kind} · ${fmtT(a.ts)}`));
      d.append(el('div', '', a.message));
      if (a.acks && a.acks.length) d.append(el('small', 'acks', a.acks.map(k => `${k.callsign}: ${k.text}`).join(' · ')));
      const mine = a.acks && a.acks.some(k => k.username === C.user.username);
      if (!mine) {
        const bts = el('div', 'btns');
        const b1 = el('button', 'btn ok', 'Voy en camino'); b1.onclick = () => ackAlert(a, 'Voy en camino');
        const b2 = el('button', 'btn', 'No puedo ir'); b2.onclick = () => ackAlert(a, 'No puedo ir');
        bts.append(b1, b2); d.append(bts);
      }
      box.append(d);
    }
  }
  function renderChans() {
    const box = $('crewChans'); box.textContent = '';
    const mk = (id, label) => {
      const b = el('button', id === C.chan ? 'on' : '', label); b.type = 'button';
      if (C.unread[id] && id !== C.chan) b.append(el('i', '', C.unread[id]));
      b.onclick = () => { C.chan = id; C.unread[id] = 0; store.set('unread', C.unread); renderChans(); renderLog(); renderBadge(); };
      box.append(b);
    };
    mk('', '# Tripulación');
    mk('control', '✉ Control');
    C.crew.filter(c => c.username !== C.user.username).forEach(c => mk(c.username, '✉ ' + c.name.split(' ')[0]));
    $('crewMsg').placeholder = C.chan ? `Privado para ${nameOf(C.chan)}…` : 'Mensaje para toda la tripulación…';
  }
  function renderLog() {
    if (!logged()) return;
    const log = $('crewLog'), me = C.user.username;
    const list = C.msgs.filter(m => C.chan === '' ? !m.to : (m.to && (m.from === C.chan || m.to === C.chan)));
    log.textContent = '';
    if (!list.length) log.append(el('div', 'empty', C.chan ? 'Sin mensajes privados todavía.' : 'Sin mensajes todavía. ¡Saluda a la tripulación!'));
    for (const m of list) {
      const d = el('div', 'msg ' + (m.from === me ? 'me' : 'bot crewmsg'));
      if (m.from !== me) d.append(el('small', 'from', nameOf(m.from)));
      d.append(document.createTextNode(m.text));
      d.append(el('small', 'at', fmtT(m.ts)));
      log.append(d);
    }
    log.scrollTop = log.scrollHeight;
  }
  function onView(v) {
    C.view = v;
    if (v === 'crew') {
      C.unread[C.chan] = 0; store.set('unread', C.unread);
      if (!logged() && !C.offline) showAuth('in');
      render();
    }
  }

  // ------------------------------------------------------------------ arranque
  function bind() {
    const slot = $('aSlot');
    Object.entries(A.ROSTER).forEach(([c, r]) => { const o = el('option', '', `${c} · ${r.role} (${r.module})`); o.value = c; slot.append(o); });
    $('authIn').onclick = () => { C.mode = 'in'; renderAuth(); };
    $('authUp').onclick = () => { C.mode = 'up'; renderAuth(); };
    $('authForm').onsubmit = submitAuth;
    $('aSkip').onclick = () => { C.offline = true; store.set('offline', true); hideAuth(); A.toast('Sin cuenta: Luma y las alertas por Wi-Fi siguen funcionando. Inicia sesión cuando quieras en «Equipo».', 5000); };
    $('btnLogin').onclick = () => showAuth('in');
    $('btnLogout').onclick = logout;
    $('btnSrv').onclick = () => {
      const u = prompt('Dirección del servidor (Wi-Fi: http://IP:8765 · datos móviles: https://…)', C.manual || C.base || '');
      if (u == null) return;
      const b = normUrl(u); if (!b) { A.toast('Dirección no válida.'); return; }
      C.manual = b; store.set('server', b); C.base = b; C.fails = 0; sync();
    };
    $('crewForm').onsubmit = async e => {
      e.preventDefault(); const t = $('crewMsg').value; $('crewMsg').value = '';
      if (!(await sendMsg(t, C.chan))) $('crewMsg').value = t;
    };
    $('optReadMsgs').checked = C.readAloud;
    $('optReadMsgs').onchange = e => { C.readAloud = e.target.checked; store.set('readAloud', C.readAloud); };
    document.addEventListener('visibilitychange', () => { if (!document.hidden && logged()) { C.fails = 0; sync(); } });
  }
  bind();
  try { const f = N.serverFound && N.serverFound(); if (f) { C.lan = f; C.lanAt = Date.now(); } } catch (e) { /* */ }
  if (logged()) { applyUser(); C.first = !C.msgs.length; sync(); }
  else if (!C.offline) showAuth('in');
  render();

  window.BioCrew = { alert, resolved, voiceCommand, onView, sync, state: C, normUrl };
})();
