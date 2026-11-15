"""
BioOrbit-UTH · Consola de cabina.

    streamlit run src/app.py

- Monitor de salud con telemetría en vivo (reproduce el CSV como si fuera un flujo real).
- Luma: robot compañero para toda la tripulación (chat, respiración, ánimo y check-in WHO-5).
- Alerta a tripulantes cercanos cuando se pierden los signos vitales (con cuenta de confirmación).
- Centro de control: toda la tripulación y todos los dispositivos (reloj, cámara, móvil) en una sola vista.
"""

import os
import time
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

import alerts
import ble_watch
import companion
import crew_link
import fleet
import nasa_data
from data_pipeline import calculate_health_scores, load_telemetry
from luma import luma_html, pick_mood

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WINDOW = 12  # registros recientes que analiza Luma
VITAL = ["heart_rate_bpm", "hrv_rmssd_ms", "spo2_pct"]
NO_DATA_COLS = ["heart_rate_bpm", "hrv_rmssd_ms", "spo2_pct", "body_temp_c", "cabin_co2_ppm",
                "radiation_rate_usv_h", "sleep_efficiency_pct"]
LEVEL_COLOR = ["#3ef0b0", "#ffc857", "#ff4d6d"]  # normal, precaución, crítico

st.set_page_config(page_title="BioOrbit-UTH", page_icon="🛰️", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=Sora:wght@300;400;600&display=swap');
:root{--cy:#38e1ff;--vi:#8b7cff;--txt:#e8f1ff;--mut:#8fb4d9}
.stApp{background:
  radial-gradient(900px 500px at 8% -8%,#1b2a7a66,transparent),
  radial-gradient(800px 480px at 100% 0%,#4b2fb055,transparent),#070a1f;
  color:var(--txt)}
.stApp,.stMarkdown,button,input,textarea,label{font-family:'Sora',sans-serif!important}
.stApp:before{content:"";position:fixed;inset:0;pointer-events:none;
  background-image:linear-gradient(#38e1ff0d 1px,transparent 1px),linear-gradient(90deg,#38e1ff0d 1px,transparent 1px);
  background-size:56px 56px;-webkit-mask-image:radial-gradient(circle at 50% 0%,#000,transparent 70%);
  mask-image:radial-gradient(circle at 50% 0%,#000,transparent 70%)}
header[data-testid="stHeader"]{background:transparent}
#MainMenu,footer{visibility:hidden}
h1,h2,h3,.ttl{font-family:'Chakra Petch',sans-serif!important;letter-spacing:.02em}
section[data-testid="stSidebar"]{background:#080d2acc;border-right:1px solid #38e1ff22}
.brand{font-family:'Chakra Petch';font-size:2.1rem;font-weight:700;line-height:1;
  background:linear-gradient(90deg,#38e1ff,#8b7cff);-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--mut);font-size:.9rem;margin:4px 0 14px}
.panel{background:#0c1233cc;border:1px solid #38e1ff26;border-radius:22px;padding:18px 20px;
  backdrop-filter:blur(10px);box-shadow:0 0 40px #38e1ff10}
.kpi{background:linear-gradient(160deg,#101a4088,#0a0f2b99);border:1px solid #38e1ff2e;border-radius:14px;
  padding:14px 16px;border-bottom:3px solid var(--c)}
.kpi .lb{font-size:.78rem;color:var(--mut)}
.kpi .vl{font-family:'Chakra Petch';font-size:1.9rem;font-weight:600;color:#fff;text-shadow:0 0 16px var(--c)}
.kpi .vl span{font-size:.8rem;color:var(--mut);margin-left:5px;text-shadow:none;font-weight:400}
.chip{display:inline-block;padding:4px 14px;border-radius:999px;border:1px solid var(--c);color:var(--c);
  font-family:'Chakra Petch';font-weight:600;background:#ffffff08}
.banner{border-radius:16px;padding:14px 18px;margin:10px 0}
.warn{background:#3a2a05;border:1px solid #ffc857}
.sos{background:linear-gradient(90deg,#5c0a1e,#a3123a);border:1px solid #ff4d6d;animation:glow 1.2s infinite alternate}
@keyframes glow{to{box-shadow:0 0 36px #ff4d6d}}
.breath{width:110px;height:110px;border-radius:50%;margin:18px auto 6px;border:2px solid var(--cy);
  box-shadow:0 0 30px #38e1ff66;animation:box 16s infinite}
@keyframes box{0%{transform:scale(.55)}25%{transform:scale(1)}50%{transform:scale(1)}75%{transform:scale(.55)}100%{transform:scale(.55)}}
table.near{width:100%;border-collapse:collapse;font-size:.9rem}
table.near td,table.near th{padding:6px 8px;border-bottom:1px solid #38e1ff1f;text-align:left;color:var(--txt)}
table.near th{color:var(--mut);font-weight:400}
div[data-testid="stChatMessage"]{background:#0e143299;border:1px solid #38e1ff22;border-radius:16px}
button[kind="primary"]{background:linear-gradient(90deg,#38e1ff,#8b7cff)!important;color:#05071a!important;border:0!important}
.fcard{background:linear-gradient(160deg,#101a4088,#0a0f2b99);border:1px solid #38e1ff2e;border-left:4px solid var(--c);
  border-radius:16px;padding:14px 16px;margin-bottom:6px}
.fcard.alarm{animation:glow 1.2s infinite alternate;border-color:#ff4d6d}
.fhead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.fgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0 8px}
.fgrid .lb{font-size:.7rem;color:var(--mut)}
.fgrid .vl{font-family:'Chakra Petch';font-size:1.25rem;font-weight:600;color:#fff;border-bottom:2px solid var(--c);display:inline-block}
.fgrid .vl span{font-size:.65rem;color:var(--mut);margin-left:3px;font-weight:400}
.badge{display:inline-block;font-size:.74rem;padding:2px 9px;border-radius:999px;border:1px solid var(--c);color:var(--c);margin:2px 4px 0 0}
.fmeta{color:var(--mut);font-size:.78rem;margin-top:6px}
.clog{display:flex;flex-direction:column;gap:8px;max-height:520px;overflow-y:auto;padding:6px 2px}
.cm{max-width:78%;padding:9px 13px;border-radius:14px;background:#38e1ff12;border:1px solid #38e1ff33;align-self:flex-start;white-space:pre-wrap}
.cm.me{align-self:flex-end;background:#8b7cff2e;border-color:#8b7cff66}
.cm.dm{border-style:dashed}
.cm small{display:block;font-size:.72rem;color:var(--mut);margin-bottom:2px}
.cm small b{color:var(--cy);font-weight:600}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
""",
    unsafe_allow_html=True,
)


def show_html(html, height):
    """Lienzo HTML propio (Luma). st.iframe en Streamlit nuevo; components.html en versiones viejas."""
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        components.html(html, height=height)


@st.cache_data
def load(name):
    df = calculate_health_scores(load_telemetry(str(DATA_DIR / name))).sort_values("timestamp")
    return {c: g.reset_index(drop=True) for c, g in df.groupby("crew_id")}


@st.cache_data(ttl=1800)
def cached_nasa_sep_events(start_date, end_date):
    return nasa_data.fetch_sep_events(start_date, end_date)


CSVS = sorted(p.name for p in DATA_DIR.glob("*.csv"))


def all_crew():
    """Toda la plantilla (ROSTER) más lo que traiga el CSV, sin repetir."""
    return list(dict.fromkeys(list(alerts.ROSTER) + list(data)))


ss = st.session_state
with st.sidebar:
    st.markdown('<div class="brand">BioOrbit</div><div class="sub">UTH · NASA Space Apps 2026</div>',
                unsafe_allow_html=True)
    dataset = st.selectbox("Telemetría (simulada)", CSVS,
                           index=CSVS.index("demo_stress_arc.csv") if "demo_stress_arc.csv" in CSVS else 0,
                           help="demo_stress_arc.csv: ASTRO-02 se desgasta poco a poco (ideal para el video).")
data = load(dataset)
if ss.get("dataset") != dataset:          # al cambiar de datos, se reinicia la reproducción
    for k in ("idx", "flat", "em", "cur"):
        ss.pop(k, None)
    ss.dataset = dataset
ss.setdefault("idx", {c: 0 for c in data})        # posición (sin recortar) en la reproducción
ss.setdefault("flat", {c: None for c in data})    # índice donde se simuló la pérdida de señal
ss.setdefault("em", {c: alerts.Emergency() for c in data})
ss.setdefault("chat", {})
ss.setdefault("crisis", {})
ss.setdefault("mood", [])
ss.setdefault("log", [])
ss.setdefault("checkins", {})
ss.setdefault("talk_at", 0.0)
ss.setdefault("cur", {})          # último estado calculado por astronauta
ss.setdefault("last_tick", 0.0)
ss.setdefault("playing", True)
ss.setdefault("radius", 20)
ss.setdefault("devs", [])
crew_link.get_link().start()      # enlace en segundo plano con el servidor de tripulación (teléfonos)

# ---------------------------------------------------------------- reloj Bluetooth
@st.fragment(run_every=2.0)
def watch_status():
    snap = ble_watch.get_watch_manager().get_snapshot()
    state, _ = ble_watch.watch_state()
    if state == "live":
        st.markdown(f'<span class="chip" style="--c:#3ef0b0">⌚ {snap.device_name[:22]} · '
                    f'{snap.heart_rate_bpm:.0f} bpm</span>', unsafe_allow_html=True)
    elif state == "lost":
        st.markdown('<span class="chip" style="--c:#ff4d6d">⌚ Reloj sin señal de pulso</span>',
                    unsafe_allow_html=True)
    st.caption(snap.status_message)


def watch_sidebar():
    """Conecta un reloj por Bluetooth LE (Pixel Watch con BioOrbit Watch Bridge u otro con perfil cardíaco)."""
    st.caption("Reloj inteligente (Bluetooth)")
    mgr = ble_watch.get_watch_manager()
    if not ble_watch.BLEAK_AVAILABLE:
        st.caption("Falta la librería `bleak`: `pip install -r requirements.txt`. Mientras, usa el modo demo.")
    elif st.button("Buscar relojes cercanos", width="stretch"):
        with st.spinner("Escaneando Bluetooth 10 s…"):
            try:
                found = ble_watch.scan_ble_devices_sync(timeout=10.0)
                ss.ble_devices = [d for d in found if d.is_watch_candidate or d.has_hr_service]
                if not ss.ble_devices:
                    st.warning("No encontré relojes. Abre BioOrbit Watch Bridge en el reloj y pulsa «Iniciar transmisión».")
            except Exception as exc:  # noqa: BLE001  (sin adaptador Bluetooth, permisos, etc.)
                st.error(f"No se pudo escanear: {exc}")
    devices = ss.get("ble_devices", [])
    if devices:
        k = st.selectbox("Reloj", range(len(devices)), key="ble_pick",
                         format_func=lambda j: f"{devices[j].name} · {devices[j].rssi} dBm"
                         + (" · ❤" if devices[j].has_hr_service else ""))
        if st.button("Conectar reloj", width="stretch", type="primary"):
            mgr.connect_ble(devices[k].address, devices[k].name)
    c1, c2 = st.columns(2)
    if c1.button("Demo reloj", width="stretch", help="Simula un Wear OS mandando pulso (sin reloj físico)."):
        mgr.start_wear_simulator(scenario="nominal")
    if c2.button("Desconectar", width="stretch"):
        mgr.disconnect()
    watch_status()
    st.selectbox("Reloj asignado a", all_crew(), key="watch_crew",
                 help="El reloj Bluetooth reemplaza la frecuencia cardíaca simulada de este astronauta.")


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    crew = st.selectbox("Astronauta monitoreado", list(data), key="crew_pick")
    playing = st.toggle("Telemetría en vivo", True)
    radius = st.slider("Radio de aviso (m)", 5, 60, 20)
    ss.playing, ss.radius = playing, radius
    st.divider()
    st.caption("Demostración")
    if st.button("Simular pérdida de signos vitales", width="stretch", type="primary"):
        ss.flat[crew] = ss.idx[crew]
    if st.button("Restablecer sensores", width="stretch"):
        ss.flat[crew] = None
    st.divider()
    watch_sidebar()
    st.divider()
    cam = companion.read_vision_status()
    if cam:
        bpm_txt = f"{cam['bpm']:.0f} bpm" if cam.get("bpm") else "midiendo…"
        st.caption(f"📷 HUD de cámara conectado · {cam['crew']} · "
                   f"{'rostro fijado' if cam.get('face_locked') else 'sin rostro'} · pulso {bpm_txt}")
    else:
        st.caption("📷 HUD de cámara apagado. Ábrelo con `python src/vision_monitor.py`.")
    st.caption("Prototipo educativo con telemetría simulada. No es un dispositivo médico.")

RULES = {
    "hr": lambda v: 0 if 60 <= v <= 90 else (1 if 50 <= v <= 105 else 2),
    "hrv": lambda v: 0 if v >= 40 else (1 if v >= 25 else 2),
    "spo2": lambda v: 0 if v >= 96 else (1 if v >= 93 else 2),
    "temp": lambda v: 0 if 36 <= v <= 37.5 else 1,
    "co2": lambda v: 0 if v < 4000 else (1 if v < 5000 else 2),
    "rad": lambda v: 0 if v < 35 else (1 if v < 60 else 2),
}


def kpi(label, key, v, unit, fmt):
    if pd.isna(v):
        color, val = LEVEL_COLOR[2], "—"
    else:
        color, val = LEVEL_COLOR[RULES[key](v)], fmt.format(v)
    return (f'<div class="kpi" style="--c:{color}"><div class="lb">{label}</div>'
            f'<div class="vl">{val}<span>{unit}</span></div></div>')


def style(fig, h=270):
    fig.update_layout(height=h, margin=dict(l=6, r=6, t=64, b=6), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9fb7d9", family="Sora"),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0))
    fig.update_xaxes(gridcolor="#38e1ff14", showline=False)
    fig.update_yaxes(gridcolor="#38e1ff14", showline=False)
    return fig


def dual(w, a, b, na, nb, ca, cb, title):
    f = make_subplots(specs=[[{"secondary_y": True}]])
    f.add_trace(go.Scatter(x=w.timestamp, y=w[a], name=na, connectgaps=False,
                           line=dict(color=ca, width=3, shape="spline")), secondary_y=False)
    f.add_trace(go.Scatter(x=w.timestamp, y=w[b], name=nb, connectgaps=False,
                           line=dict(color=cb, width=2, dash="dot")), secondary_y=True)
    f.update_layout(title=dict(text=title, font=dict(size=14, family="Chakra Petch"), x=0.01, y=0.97, yanchor="top"))
    return style(f)


# ---------------------------------------------------------------- monitor en vivo
def tick(force=False):
    """Un latido de la consola: calcula el estado de TODA la tripulación una vez por segundo.

    Lo llaman a la vez el monitor y el centro de control; el seguro de tiempo evita contar doble.
    """
    now = time.time()
    if ss.cur and not force and now - ss.last_tick < 0.9:
        return
    ss.last_tick = now
    devs = fleet.snapshot(ss.get("watch_crew"), now)
    link = crew_link.get_link()
    for c in all_crew():
        df = data.get(c)
        n = ss.idx.get(c, 0)
        if df is not None:
            i = n % len(df)
            row = df.iloc[i].copy()
        else:                                  # sin telemetría simulada: solo cuentan los dispositivos reales
            i, row = 0, pd.Series({k: np.nan for k in NO_DATA_COLS})
        wstate, wdata = "off", None
        if c == ss.get("watch_crew"):
            wstate, wdata = ble_watch.watch_state()
            row = ble_watch.apply_watch(row, wstate, wdata)
        fstate, fdata = fleet.vitals_state(c, devs)   # teléfonos u otros dispositivos que reportan
        if fstate != "off":
            row = ble_watch.apply_watch(row, fstate, fdata)
            wstate, wdata = fstate, fdata
        if ss.flat.get(c) is not None:
            row[VITAL] = np.nan
        em = ss.em.setdefault(c, alerts.Emergency())
        if df is None and wstate == "off":
            status = "NO_DATA"                 # nada que vigilar: no dispara alertas
        else:
            status = alerts.vitals_status(row)
        if alerts.step(em, status, now) == "DUE":
            ss.log.insert(0, alerts.broadcast("NO_VITALS", c, ss.radius))
            share_alert(ss.log[0])
            em.phase = "SENT"
        if em.phase == "OK" and link.has_open_key(c):
            link.resolve_key(c)                # volvieron las señales o «estoy bien»: se cierra en los teléfonos
        ss.cur[c] = dict(n=n, i=i, row=row, status=status, watch=wstate, watch_data=wdata)
        if ss.playing and df is not None:
            ss.idx[c] = n + 1
    ss.devs = devs


def share_alert(rec):
    """Además de la red local (UDP), manda la alerta a los teléfonos por el servidor de tripulación
    (así llega también a quien está con datos móviles)."""
    crew_link.get_link().send_alert(rec["kind"], rec["message"], key=rec["crew"] if rec["kind"] == "NO_VITALS" else None)
    rec.setdefault("channels", []).append(("Servidor de tripulación", "enviado"))


def last_alert(crew):
    """Último aviso enviado POR este astronauta (el registro es de toda la tripulación)."""
    return next((a for a in ss.log if a["crew"] == crew), None)


def monitor(crew, radius, playing):
    tick()
    df = data[crew]
    cur = ss.cur[crew]
    n, i, row, status = cur["n"], cur["i"], cur["row"], cur["status"]
    watch, watch_data = cur["watch"], cur["watch_data"]
    start = ss.flat[crew]
    em, now = ss.em[crew], time.time()

    info = alerts.ROSTER[crew]
    lvl = {"NORMAL": 0, "PRECAUCIÓN": 1, "CRÍTICO": 2}[row["alert_level"]]
    color = LEVEL_COLOR[2] if status != "OK" else LEVEL_COLOR[lvl]
    chip = "Sin señal" if status != "OK" else row["alert_level"].capitalize()
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin:4px 0 8px">'
        f'<div><div class="ttl" style="font-size:1.5rem;font-weight:600">{crew}</div>'
        f'<div class="sub" style="margin:0">{info["role"]} · {info["module"]}</div></div>'
        f'<span class="chip" style="--c:{color}">{chip}</span></div>',
        unsafe_allow_html=True,
    )

    if em.phase == "CONFIRMING":
        st.markdown(f'<div class="banner warn"><b>No detecto signos vitales de {crew}.</b> '
                    f'Aviso a la tripulación cercana en {max(0, em.deadline - now):.0f} s.</div>',
                    unsafe_allow_html=True)
        if st.button("Estoy bien, cancelar aviso", key="ack"):
            alerts.acknowledge(em, now)
            st.rerun(scope="fragment")
    elif em.phase == "SENT" and last_alert(crew):
        last = last_alert(crew)
        who = ", ".join(f"{c} ({r}, {d:.0f} m)" for c, r, d in last["notified"]) or "nadie dentro del radio"
        st.markdown(f'<div class="banner sos"><b>Alerta enviada a las {last["when"]}.</b> '
                    f'Avisados: {who}.</div>', unsafe_allow_html=True)
        with st.expander("Primeros pasos para quien acude", expanded=True):
            for k, s in enumerate(alerts.FIRST_RESPONSE, 1):
                st.markdown(f"{k}. {s}")
    elif status == "SENSOR_FAULT":
        st.markdown('<div class="banner warn">Un sensor dejó de reportar. Revisa que esté bien colocado.</div>',
                    unsafe_allow_html=True)

    cols = st.columns(6)
    if watch == "live":
        st.markdown(f'<div class="sub">⌚ Frecuencia cardíaca en vivo desde '
                    f'<b>{(watch_data or {}).get("device_name", "reloj")}</b>; el resto de la telemetría es simulada.</div>',
                    unsafe_allow_html=True)
    elif watch == "lost":
        st.markdown('<div class="banner warn"><b>El reloj dejó de mandar pulso.</b> '
                    'Si no vuelve, se activa la alerta de signos vitales.</div>', unsafe_allow_html=True)
    items = [("Frecuencia cardíaca" + (" · reloj" if watch == "live" else ""), "hr", row["heart_rate_bpm"], "bpm", "{:.0f}"),
             ("HRV", "hrv", row["hrv_rmssd_ms"], "ms", "{:.0f}"),
             ("SpO₂", "spo2", row["spo2_pct"], "%", "{:.1f}"),
             ("Temperatura", "temp", row["body_temp_c"], "°C", "{:.1f}"),
             ("CO₂ de cabina", "co2", row["cabin_co2_ppm"], "ppm", "{:.0f}"),
             ("Radiación", "rad", row["radiation_rate_usv_h"], "µSv/h", "{:.0f}")]
    for c, it in zip(cols, items):
        c.markdown(kpi(*it), unsafe_allow_html=True)

    w = df.iloc[max(0, i - 39): i + 1].copy()
    if start is not None:
        w.loc[(n - (i - w.index.to_numpy())) >= start, VITAL] = np.nan
    a, b = st.columns(2)
    a.plotly_chart(dual(w, "heart_rate_bpm", "hrv_rmssd_ms", "Frecuencia cardíaca (bpm)", "HRV (ms)",
                        "#38e1ff", "#8b7cff", "Sistema cardiovascular"), width="stretch", key="c1")
    b.plotly_chart(dual(w, "cabin_co2_ppm", "radiation_rate_usv_h", "CO₂ (ppm)", "Radiación (µSv/h)",
                        "#ffc857", "#ff4d6d", "Ambiente de cabina"), width="stretch", key="c2")

    near = alerts.nearby_crew(crew, radius)
    rows = "".join(f"<tr><td>{c}</td><td>{inf['role']}</td><td>{inf['module']}</td><td>{d:.0f} m</td></tr>"
                   for c, inf, d in near) or '<tr><td colspan="4">Nadie dentro del radio de aviso.</td></tr>'
    chans = ""
    if last_alert(crew):
        chans = "<br>Último aviso: " + " · ".join(f"{n_}: {s}" for n_, s in last_alert(crew)["channels"])
    st.markdown(f'<div class="panel"><div class="ttl" style="font-size:1.05rem;margin-bottom:8px">'
                f'Tripulantes que recibirían el aviso</div>'
                f'<table class="near"><tr><th>Persona</th><th>Rol</th><th>Módulo</th><th>Distancia</th></tr>{rows}</table>'
                f'<div class="sub" style="margin:10px 0 0">{chans}</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- compañero Luma
def chat_tab():
    who = st.selectbox("¿Quién habla con Luma?", list(alerts.ROSTER), key="who",
                       format_func=lambda c: f"{c} · {alerts.ROSTER[c]['role']}")
    hist = ss.chat.setdefault(who, [])
    row, physio = None, {"level": 0, "reasons": []}
    if who in data:
        i = ss.idx[who] % len(data[who])
        row = data[who].iloc[i]
        physio = companion.physio_state(data[who].iloc[max(0, i - WINDOW + 1): i + 1])
    last = ss.checkins.get(who)
    who_lvl = companion.who5_level(last["raw"]) if last else None
    level, escalate = companion.combine(physio["level"], who_lvl)
    if not hist:
        hist.append(("assistant", companion.greeting(who, row)))

    if escalate:
        st.markdown('<div class="banner warn"><b>Conviene avisar al cirujano de vuelo o al comandante.</b> '
                    'Por tu check-in y tus señales, lo mejor es que alguien de tu equipo te acompañe. '
                    'No es un diagnóstico: es una sugerencia de apoyo.</div>', unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="large")
    with left:
        for role, txt in hist:
            with st.chat_message(role, avatar="🛰️" if role == "assistant" else "🧑‍🚀"):
                st.markdown(txt)
        msg = st.chat_input("Cuéntale a Luma cómo te sientes", key="chat_in")
        if msg:
            hist.append(("user", msg))
            r = companion.reply(msg, who, row, hist)
            hist.append(("assistant", r.text))
            if r.crisis:
                ss.crisis[who] = True
            ss.talk_at = time.time()
            st.rerun()
    with right:
        talk_s = max(0.0, 4.0 - (time.time() - ss.talk_at))
        mood = pick_mood(level, emergency=bool(ss.crisis.get(who)), talking=talk_s > 0)
        bpm = None if row is None else row["heart_rate_bpm"]
        estado = {0: "estable", 1: "desgaste leve", 2: "desgaste alto"}[level]
        st.markdown(f'<div class="ttl" style="text-align:center;font-size:1.1rem">Luma · {mood}</div>'
                    f'<div class="sub" style="text-align:center;margin:0">{who} · {estado}</div>',
                    unsafe_allow_html=True)
        show_html(luma_html(mood, bpm if bpm == bpm else 70, talk_s, height=260), 266)
        with st.expander("Respiración guiada"):
            st.markdown('<div class="breath"></div><div class="sub" style="text-align:center">'
                        'Inhala, sostén, exhala, sostén. Cuatro segundos cada fase.</div>', unsafe_allow_html=True)
        mood = st.select_slider("¿Cómo te sientes hoy?", options=[1, 2, 3, 4, 5], value=3,
                                format_func=lambda v: ["😞", "😕", "😐", "🙂", "😄"][v - 1])
        if st.button("Guardar mi ánimo", width="stretch"):
            ss.mood.append((time.strftime("%H:%M"), who, mood))
            if mood <= 2:
                hist.append(("assistant", "Gracias por registrarlo. Parece un día difícil; aquí estoy si quieres hablar."))
            st.rerun()
        mine = [f"{t}: {['😞', '😕', '😐', '🙂', '😄'][m - 1]}" for t, w_, m in ss.mood if w_ == who][-5:]
        if mine:
            st.caption("Tus últimos registros — " + " · ".join(mine))
        if ss.crisis.get(who) or escalate:
            if st.button("Pedir apoyo humano ahora", type="primary", width="stretch"):
                res = alerts.broadcast("SUPPORT", who, radius)
                share_alert(res)
                ss.log.insert(0, res)
                names = ", ".join(c for c, _, _ in res["notified"]) or "nadie dentro del radio"
                st.success(f"Aviso enviado. Avisados: {names}.")

    who5_panel(who, last)


def who5_panel(who, last):
    """Check-in WHO-5: 5 preguntas de bienestar de la OMS, se combina con las señales."""
    st.divider()
    st.markdown('<div class="ttl" style="font-size:1.2rem">Check-in de bienestar (WHO-5)</div>',
                unsafe_allow_html=True)
    if last:
        st.markdown(f'<div class="sub">Último check-in de {who}: <b>{last["pct"]} %</b> · '
                    f'{companion.WHO5_BANDS[companion.who5_level(last["raw"])]} ({last["when"]})</div>',
                    unsafe_allow_html=True)
    with st.expander("Hacer check-in", expanded=False):
        st.markdown("Piensa en las **últimas dos semanas**. ¿Con qué frecuencia te has sentido así?")
        with st.form(f"who5_{who}"):
            answers = [st.radio(f"{k + 1}. {item}", options=list(range(6)), index=None, horizontal=True,
                                format_func=lambda v: companion.WHO5_SCALE[v], key=f"who5_{who}_{k}")
                       for k, item in enumerate(companion.WHO5_ITEMS)]
            sent = st.form_submit_button("Guardar check-in")
        if sent:
            if any(a is None for a in answers):
                st.warning("Responde las 5 preguntas.")
            else:
                raw, pct = companion.who5_score(answers)
                ss.checkins[who] = {"raw": raw, "pct": pct, "when": datetime.now().strftime("%H:%M")}
                st.rerun()


# ---------------------------------------------------------------- centro de control
STATE_COLOR = {"online": "#3ef0b0", "stale": "#ffc857", "offline": "#ff4d6d"}
STATE_TXT = {"online": "en línea", "stale": "retrasado", "offline": "sin señal"}


def spark(vals, color, w=150, h=34):
    """Mini gráfica SVG (sin dependencias) de los últimos valores."""
    pts = [float(v) for v in vals if v == v]
    if len(pts) < 2:
        return f'<svg width="{w}" height="{h}"></svg>'
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    xs = [k * (w - 4) / (len(pts) - 1) + 2 for k in range(len(pts))]
    ys = [h - 4 - (v - lo) / span * (h - 8) for v in pts]
    path = " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(zip(xs, ys)))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><path d="{path}" fill="none" '
            f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def crew_overview(c):
    """Todo lo que la tarjeta de un astronauta necesita saber."""
    cur, em = ss.cur[c], ss.em[c]
    if c not in data:                      # solo dispositivos reales
        empty = pd.DataFrame(columns=NO_DATA_COLS)
        if cur["status"] == "NO_DATA":
            return dict(cur=cur, em=em, win=empty, rank=0, label="Sin telemetría", color="#8fb4d9",
                        level=0, mood="reposo", who5=ss.checkins.get(c), nodata=True)
        df, i = empty, 0
    else:
        df, i = data[c], cur["i"]
    win = df.iloc[max(0, i - WINDOW + 1): i + 1]
    physio = companion.physio_state(win) if len(win) else {"level": 0, "reasons": []}
    last = ss.checkins.get(c)
    level, escalate = companion.combine(physio["level"], companion.who5_level(last["raw"]) if last else None)
    status, row = cur["status"], cur["row"]
    phone_alert = next((d["alert"] for d in ss.devs if d.get("crew") == c and d.get("alert")
                        and d["state"] != "offline"), None)
    if phone_alert:
        rank, label, color = 3, "Alerta: " + phone_alert, LEVEL_COLOR[2]
    elif status == "NO_VITALS" or em.phase in ("CONFIRMING", "SENT"):
        rank, label, color = 3, "Sin signos vitales", LEVEL_COLOR[2]
    elif status == "SENSOR_FAULT":
        rank, label, color = 2, "Sensor con falla", LEVEL_COLOR[1]
    else:
        lv = {"NORMAL": 0, "PRECAUCIÓN": 1, "CRÍTICO": 2}[row["alert_level"]]
        rank = 2 if lv == 2 else (1 if lv == 1 or level >= 1 else 0)
        label, color = row["alert_level"].capitalize(), LEVEL_COLOR[max(lv, min(level, 1))]
        if escalate:
            rank, label, color = max(rank, 2), "Apoyo sugerido", LEVEL_COLOR[1]
    mood = pick_mood(level, emergency=bool(ss.crisis.get(c)) or rank == 3)
    return dict(cur=cur, em=em, win=df.iloc[max(0, i - 39): i + 1], rank=rank, label=label, color=color,
                level=level, mood=mood, who5=last, nodata=False)


def crew_card(c, ov, devs):
    info, row = alerts.ROSTER[c], ov["cur"]["row"]
    vals = [("FC", "hr", row["heart_rate_bpm"], "bpm", "{:.0f}"), ("SpO₂", "spo2", row["spo2_pct"], "%", "{:.1f}"),
            ("HRV", "hrv", row["hrv_rmssd_ms"], "ms", "{:.0f}"), ("Temp", "temp", row["body_temp_c"], "°C", "{:.1f}")]
    cells = ""
    for lb, key, v, unit, fmt in vals:
        if pd.isna(v):
            col, txt = ("#8fb4d9" if ov["nodata"] else LEVEL_COLOR[2]), "—"
        else:
            col, txt = LEVEL_COLOR[RULES[key](v)], fmt.format(v)
        cells += f'<div style="--c:{col}"><div class="lb">{lb}</div><div class="vl">{txt}<span>{unit}</span></div></div>'
    badges = '<span class="badge" style="--c:#8fb4d9">🧪 Simulado</span>'
    for d in sorted((d for d in devs if d.get("crew") == c), key=lambda d: d["device_id"]):
        ico = fleet.KINDS[d["kind"]][0]
        badges += (f'<span class="badge" style="--c:{STATE_COLOR[d["state"]]}">{ico} {escape(str(d["name"]))} · '
                   f'{STATE_TXT[d["state"]]}</span>')
    who = ov["who5"]
    meta = f'Ánimo de Luma: {ov["mood"]}' + (f' · WHO-5 {who["pct"]} %' if who else " · sin check-in")
    if not pd.isna(row["cabin_co2_ppm"]):
        meta += f' · {row["cabin_co2_ppm"]:.0f} ppm CO₂ · {row["radiation_rate_usv_h"]:.0f} µSv/h'
    spk = (spark(ov["win"]["heart_rate_bpm"], "#38e1ff") + spark(ov["win"]["hrv_rmssd_ms"], "#8b7cff"))
    alarm = " alarm" if ov["rank"] == 3 else ""
    return (f'<div class="fcard{alarm}" style="--c:{ov["color"]}"><div class="fhead"><div>'
            f'<div class="ttl" style="font-size:1.25rem;font-weight:600">{escape(c)}</div>'
            f'<div class="sub" style="margin:0">{escape(info["role"])} · {escape(info["module"])}</div></div>'
            f'<span class="chip" style="--c:{ov["color"]}">{escape(ov["label"])}</span></div>'
            f'<div class="fgrid">{cells}</div>{spk}<div style="margin-top:4px">{badges}</div>'
            f'<div class="fmeta">{escape(meta)}</div></div>')


def pick_crew(c):
    """Callback del botón «Monitorear»: cambia el astronauta de la pestaña Monitor de salud."""
    ss.crew_pick = c


def fleet_table(devs):
    rows = []
    for c in ss.cur:
        if c not in data:
            continue
        rows.append({"Dispositivo": "Sensores simulados (CSV)", "Tipo": "🧪 Simulado", "Astronauta": c,
                     "Estado": "🟢 en línea" if ss.playing else "⏸ en pausa", "Último dato": "ahora",
                     "FC (bpm)": None, "Batería (%)": None, "Detalle": "Telemetría de demostración"})
    for d in devs:
        age = d["age"]
        rows.append({
            "Dispositivo": str(d["name"]), "Tipo": " ".join(fleet.KINDS[d["kind"]]),
            "Astronauta": d.get("crew") or "—",
            "Estado": {"online": "🟢", "stale": "🟡", "offline": "🔴"}[d["state"]] + " " + STATE_TXT[d["state"]],
            "Último dato": f"hace {age:.0f} s" if age < 90 else f"hace {age / 60:.0f} min",
            "FC (bpm)": d.get("heart_rate_bpm"), "Batería (%)": d.get("battery_pct"),
            "Detalle": d.get("detail") or ("Pulso por cámara (experimental)" if d["kind"] == "camera" else "")})
    return pd.DataFrame(rows)


def fleet_chart(ov_all, col, title, unit):
    f = go.Figure()
    for c, ov in ov_all.items():
        y = ov["win"][col]
        if not len(y):
            continue
        f.add_trace(go.Scatter(x=list(range(-len(y) + 1, 1)), y=y, name=c, mode="lines",
                               line=dict(width=3 if ov["rank"] >= 2 else 2, shape="spline")))
    f.update_layout(title=dict(text=f"{title} ({unit})", font=dict(size=14, family="Chakra Petch"),
                               x=0.01, y=0.97, yanchor="top"))
    f.update_xaxes(title="registros atrás")
    return style(f, 250)


@st.fragment(run_every=1.0)
def control_center():
    """Vista de toda la tripulación y todos los dispositivos."""
    tick()
    devs = ss.devs
    crews = all_crew()
    ov_all = {c: crew_overview(c) for c in crews}
    reporting = [d for d in devs]
    online = sum(d["state"] == "online" for d in reporting)
    ok = sum(ov["rank"] == 0 for ov in ov_all.values())
    alarms = sum(ov["rank"] >= 2 for ov in ov_all.values())
    rows = [ss.cur[c]["row"] for c in crews]
    co2s = [r["cabin_co2_ppm"] for r in rows if not pd.isna(r["cabin_co2_ppm"])]
    rads = [r["radiation_rate_usv_h"] for r in rows if not pd.isna(r["radiation_rate_usv_h"])]
    top_co2, top_rad = (max(co2s) if co2s else np.nan), (max(rads) if rads else np.nan)

    k = st.columns(4)
    k[0].markdown(f'<div class="kpi" style="--c:{LEVEL_COLOR[0] if ok == len(crews) else LEVEL_COLOR[1]}">'
                  f'<div class="lb">Tripulantes estables</div><div class="vl">{ok}<span>de {len(crews)}</span></div></div>',
                  unsafe_allow_html=True)
    k[1].markdown(f'<div class="kpi" style="--c:{LEVEL_COLOR[2] if alarms else LEVEL_COLOR[0]}">'
                  f'<div class="lb">Con alerta o apoyo sugerido</div><div class="vl">{alarms}<span>personas</span></div></div>',
                  unsafe_allow_html=True)
    k[2].markdown(f'<div class="kpi" style="--c:{LEVEL_COLOR[0] if online == len(reporting) else LEVEL_COLOR[1]}">'
                  f'<div class="lb">Dispositivos en línea</div><div class="vl">{online}<span>de {len(reporting)} conectados</span></div></div>',
                  unsafe_allow_html=True)
    k[3].markdown(kpi("Peor CO₂ de cabina", "co2", top_co2, "ppm", "{:.0f}"),
                  unsafe_allow_html=True)
    rad_txt = "—" if pd.isna(top_rad) else f"{top_rad:.0f} µSv/h"
    st.markdown(f'<div class="sub" style="margin:6px 0 2px">Radiación más alta ahora: <b>{rad_txt}</b> · '
                f'Luma acompaña a cada astronauta; el dato de pulso real viene solo de relojes y teléfonos conectados.</div>',
                unsafe_allow_html=True)

    link_state, link_msg = crew_link.get_link().status()
    st.caption(("🟢 " if link_state == "ok" else "🟠 ") + link_msg)

    # Alertas que mandaron los teléfonos (servidor de tripulación)
    for a_ in crew_link.get_link().open_alerts():
        acks = " · ".join(f"{escape(str(k.get('callsign', '')))}: {escape(str(k.get('text', '')))}"
                          for k in a_.get("acks", []))
        st.markdown(f'<div class="banner sos"><b>📲 {escape(str(a_.get("kind", "ALERTA")))}</b> · '
                    f'{escape(str(a_.get("message", "")))}' + (f'<br><small>{acks}</small>' if acks else "") + '</div>',
                    unsafe_allow_html=True)
        b1, b2, _ = st.columns([1, 1, 3])
        mine = any(k.get("username") == "control" for k in a_.get("acks", []))
        if not mine and b1.button("Enterado", key=f"cc_ack_srv_{a_['id']}", width="stretch"):
            crew_link.get_link().ack(a_["id"])
            st.rerun(scope="fragment")
        if b2.button("Marcar resuelta", key=f"cc_res_{a_['id']}", width="stretch"):
            crew_link.get_link().resolve(a_["id"])
            st.rerun(scope="fragment")

    # Avisos activos, del más urgente al menos
    for c in sorted(crews, key=lambda c: -ov_all[c]["rank"]):
        em, now = ov_all[c]["em"], time.time()
        if em.phase == "CONFIRMING":
            st.markdown(f'<div class="banner warn"><b>No detecto signos vitales de {escape(c)}.</b> '
                        f'Aviso a la tripulación cercana en {max(0, em.deadline - now):.0f} s.</div>', unsafe_allow_html=True)
            if st.button(f"{c}: estoy bien, cancelar aviso", key=f"cc_ack_{c}"):
                alerts.acknowledge(em, now)
                st.rerun(scope="fragment")
        elif em.phase == "SENT" and last_alert(c):
            la = last_alert(c)
            who = ", ".join(f"{x} ({r}, {d:.0f} m)" for x, r, d in la["notified"]) or "nadie dentro del radio"
            st.markdown(f'<div class="banner sos"><b>{escape(c)}: alerta enviada a las {la["when"]}.</b> '
                        f'Avisados: {escape(who)}.</div>', unsafe_allow_html=True)

    # Tarjetas: las más urgentes primero
    order = sorted(crews, key=lambda c: (-ov_all[c]["rank"], c))
    per_row = 2 if len(order) <= 4 else 3
    for r0 in range(0, len(order), per_row):
        cols = st.columns(per_row, gap="medium")
        for col, c in zip(cols, order[r0:r0 + per_row]):
            with col:
                st.markdown(crew_card(c, ov_all[c], devs), unsafe_allow_html=True)
                if st.button("Monitorear a " + c, key=f"cc_pick_{c}", on_click=pick_crew, args=(c,)):
                    st.rerun()  # recarga completa para que cambie la pestaña Monitor de salud

    a, b = st.columns(2)
    a.plotly_chart(fleet_chart(ov_all, "heart_rate_bpm", "Frecuencia cardíaca de toda la tripulación", "bpm"),
                   width="stretch", key="cc_hr")
    b.plotly_chart(fleet_chart(ov_all, "hrv_rmssd_ms", "HRV de toda la tripulación", "ms"),
                   width="stretch", key="cc_hrv")

    st.markdown('<div class="ttl" style="font-size:1.1rem;margin:6px 0">Dispositivos</div>', unsafe_allow_html=True)
    st.dataframe(fleet_table(devs), hide_index=True, width="stretch")
    if not devs:
        st.caption("Aún no hay dispositivos reales conectados: todo lo que ves viene del CSV simulado.")

    with st.expander("Conectar teléfonos y otras laptops"):
        ip = fleet.lan_ip()
        st.markdown(
            "**Teléfonos (app BioOrbit):**\n\n"
            "1. En otra terminal con el venv activo: `python crew_server/server.py` (puerto 8765).\n"
            f"2. Cada astronauta abre la app en el mismo Wi-Fi, crea su cuenta y elige su puesto (ASTRO-01 a 04). "
            f"Si no encuentra el servidor, escribe `{ip}:8765`.\n"
            "3. Esta consola entra sola como «control» y muestra los teléfonos en cuanto sincronizan.\n"
            "4. Datos móviles: `py crew_server/tunel.py` (Cloudflare). "
            + (f"Dirección actual: `{crew_link.get_link().public_url()}`." if crew_link.get_link().public_url()
               else "Los teléfonos aprenden la dirección solos.") + "\n\n"
            "**Otra laptop con el HUD de cámara:**\n\n"
            f"1. Aquí: `python src/fleet_server.py` (puerto {fleet.PORT}).\n"
            f"2. En la otra laptop: `$env:BIOORBIT_FLEET_URL=\"http://{ip}:{fleet.PORT}\"` y luego el HUD.")
        st.caption("Solo para una red local de confianza. Un reloj o teléfono con reloj que mandaba pulso y se calla "
                   "cuenta como pérdida de signos vitales (con cuenta regresiva). El pulso por cámara no dispara alertas.")

    with st.expander("Historial de avisos"):
        if ss.log:
            st.dataframe(pd.DataFrame([{"Hora": a_["when"], "Tipo": a_["kind"], "Astronauta": a_["crew"],
                                        "Avisados": ", ".join(x for x, _, _ in a_["notified"]) or "nadie"}
                                       for a_ in ss.log[:10]]), hide_index=True, width="stretch")
        else:
            st.caption("Sin avisos todavía.")


# ---------------------------------------------------------------- chat con la tripulación (app del teléfono)
def chat_label(u, accounts):
    if not u:
        return "Toda la tripulación"
    if u == "control":
        return "Control"
    a = next((x for x in accounts if x["username"] == u), None)
    return f"{a['name']} ({a['callsign']})" if a else u


@st.fragment(run_every=2.0)
def crew_chat_log(chan):
    link = crew_link.get_link()
    state, msg = link.status()
    accounts = link.accounts()
    msgs = [m for m in link.messages()
            if (not chan and not m.get("to")) or (chan and m.get("to") and chan in (m.get("from"), m.get("to")))]
    if state != "ok":
        st.caption("🟠 " + msg)
    online = [a for a in accounts if a["online"]]
    st.caption(f"{len(online)} de {len(accounts)} astronautas en línea · "
               + (", ".join(f"{a['name']} ({a['callsign']})" for a in online) or "nadie conectado"))
    parts = []
    for m in msgs[-120:]:
        me, dm = m.get("from") == "control", bool(m.get("to"))
        when = datetime.fromtimestamp(float(m.get("ts", 0))).strftime("%H:%M")
        head = f"<b>{escape(chat_label(m.get('from'), accounts))}</b>" + (
            f" → {escape(chat_label(m.get('to'), accounts))}" if dm else "") + f" · {when}"
        parts.append(f'<div class="cm{" me" if me else ""}{" dm" if dm else ""}"><small>{head}</small>'
                     f'{escape(str(m.get("text", "")))}</div>')
    if not parts:
        parts.append('<div class="sub">Sin mensajes todavía.</div>')
    # lo más nuevo abajo: se invierte el orden visual para que la caja quede pegada al final
    st.markdown('<div class="clog" style="flex-direction:column-reverse"><div style="display:flex;flex-direction:column;gap:8px">'
                + "".join(parts) + "</div></div>", unsafe_allow_html=True)


def crew_chat():
    link = crew_link.get_link()
    accounts = link.accounts()
    st.markdown('<div class="ttl" style="font-size:1.25rem">Chat con la tripulación</div>'
                '<div class="sub">Los mismos mensajes que ven los astronautas en la pestaña «Equipo» de la app. '
                'Luma los lee en voz alta en el teléfono.</div>', unsafe_allow_html=True)
    options = [""] + [a["username"] for a in accounts]
    chan = st.radio("Conversación", options, horizontal=True, key="crew_chan",
                    format_func=lambda u: "💬 Toda la tripulación" if not u else "✉ " + chat_label(u, accounts))
    crew_chat_log(chan)
    with st.form("crew_chat_form", clear_on_submit=True, border=False):
        a, b = st.columns([6, 1])
        txt = a.text_input("Mensaje", label_visibility="collapsed",
                           placeholder="Mensaje para toda la tripulación…" if not chan else
                           f"Mensaje privado para {chat_label(chan, accounts)}…")
        sent = b.form_submit_button("Enviar", type="primary", width="stretch")
    if sent and txt.strip():
        ok, err = link.send_chat(txt, chan)
        if not ok:
            st.error("No se envió: " + err)


def nasa_data_tab():
    st.markdown('<div class="ttl" style="font-size:1.35rem">Datos espaciales y datasets NASA</div>',
                unsafe_allow_html=True)
    st.markdown(
        "Los eventos DONKI aportan contexto de actividad solar; **no son mediciones de dosis de radiación "
        "ni datos fisiológicos de la tripulación**."
    )
    days = st.selectbox("Consultar eventos SEP de los últimos", [7, 30], format_func=lambda n: f"{n} días",
                        key="nasa_sep_days")
    if st.button("Actualizar datos de NASA", key="nasa_sep_refresh"):
        cached_nasa_sep_events.clear()

    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    st.caption(f"Fuente: NASA DONKI · SEP · {start_date.isoformat()} a {end_date.isoformat()}. "
               + ("Usando NASA_API_KEY." if os.getenv("NASA_API_KEY") else
                  "Sin NASA_API_KEY se usa DEMO_KEY, sujeta a límites de solicitudes."))
    try:
        events = cached_nasa_sep_events(start_date.isoformat(), end_date.isoformat())
    except requests.RequestException:
        st.error("No se pudo consultar NASA DONKI. Revisa la conexión y, si usas una, la variable NASA_API_KEY.")
    except ValueError as exc:
        st.error(f"La respuesta de NASA no tiene el formato esperado: {exc}")
    else:
        if events:
            st.metric("Eventos de partículas solares", len(events))
            st.dataframe(
                pd.DataFrame(events),
                column_config={"Ficha NASA": st.column_config.LinkColumn("Ficha NASA", display_text="Abrir")},
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("NASA DONKI no reporta eventos SEP en este intervalo.")

    st.divider()
    st.markdown('<div class="ttl" style="font-size:1.15rem">Importar un dataset OSDR / LSDA</div>',
                unsafe_allow_html=True)
    st.markdown(
        "Descarga un archivo **CSV o TSV** de acceso abierto desde "
        "[NASA OSDR](https://osdr.nasa.gov/bio/repo/data/studies/) o "
        "[NASA Life Sciences Portal](https://nlsp.nasa.gov/explore) y cárgalo aquí. "
        "No se admiten archivos ZIP."
    )
    uploaded = st.file_uploader("Dataset de referencia", type=["csv", "tsv", "txt"], key="nasa_dataset_upload")
    if uploaded is not None:
        if uploaded.size > 25 * 1024 * 1024:
            st.error("El archivo supera el límite de 25 MB. Descarga una tabla más pequeña en CSV/TSV.")
            return
        try:
            dataset = nasa_data.read_reference_dataset(uploaded)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.caption(f"{uploaded.name} · {len(dataset):,} filas · {len(dataset.columns)} columnas")
            st.dataframe(dataset.head(100), hide_index=True, width="stretch")
            numeric_columns = dataset.select_dtypes(include=np.number).columns.tolist()
            if numeric_columns:
                with st.expander("Resumen estadístico de columnas numéricas"):
                    st.dataframe(dataset[numeric_columns].describe().T, width="stretch")
            st.info("Este dataset se muestra como referencia y no se mezcla con la telemetría ni altera las alertas.")


tick()
tab0, tabc, tab1, tab2, tab_nasa = st.tabs(
    ["Centro de control", "Chat de tripulación", "Monitor de salud", "Luma, tu compañero", "NASA y datasets"]
)
with tab0:
    control_center()
with tabc:
    crew_chat()
with tab1:
    st.fragment(monitor, run_every=1.0 if playing else None)(crew, radius, playing)
with tab2:
    chat_tab()
with tab_nasa:
    nasa_data_tab()
