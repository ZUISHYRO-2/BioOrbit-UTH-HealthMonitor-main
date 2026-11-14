"""
BioOrbit-UTH · Consola de cabina.

    streamlit run src/app.py

- Monitor de salud con telemetría en vivo (reproduce el CSV como si fuera un flujo real).
- ORBI: compañero virtual para toda la tripulación.
- Alerta a tripulantes cercanos cuando se pierden los signos vitales (con cuenta de confirmación).
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import alerts
import companion
from data_pipeline import calculate_health_scores, load_telemetry

DATA = Path(__file__).resolve().parent.parent / "data" / "sample_astronaut_telemetry.csv"
VITAL = ["heart_rate_bpm", "hrv_rmssd_ms", "spo2_pct"]
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
.orbi{width:84px;height:84px;border-radius:50%;margin:4px auto 14px;
  background:radial-gradient(circle at 35% 30%,#fff,#38e1ff 30%,#8b7cff 65%,#1a1650);
  box-shadow:0 0 40px #38e1ff66,0 0 90px #8b7cff44;animation:float 5s ease-in-out infinite}
@keyframes float{50%{transform:translateY(-6px) scale(1.04)}}
.breath{width:110px;height:110px;border-radius:50%;margin:18px auto 6px;border:2px solid var(--cy);
  box-shadow:0 0 30px #38e1ff66;animation:box 16s infinite}
@keyframes box{0%{transform:scale(.55)}25%{transform:scale(1)}50%{transform:scale(1)}75%{transform:scale(.55)}100%{transform:scale(.55)}}
table.near{width:100%;border-collapse:collapse;font-size:.9rem}
table.near td,table.near th{padding:6px 8px;border-bottom:1px solid #38e1ff1f;text-align:left;color:var(--txt)}
table.near th{color:var(--mut);font-weight:400}
div[data-testid="stChatMessage"]{background:#0e143299;border:1px solid #38e1ff22;border-radius:16px}
button[kind="primary"]{background:linear-gradient(90deg,#38e1ff,#8b7cff)!important;color:#05071a!important;border:0!important}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data
def load():
    df = calculate_health_scores(load_telemetry(str(DATA)))
    return {c: g.reset_index(drop=True) for c, g in df.groupby("crew_id")}


data = load()
ss = st.session_state
ss.setdefault("idx", {c: 0 for c in data})        # posición (sin recortar) en la reproducción
ss.setdefault("flat", {c: None for c in data})    # índice donde se simuló la pérdida de señal
ss.setdefault("em", {c: alerts.Emergency() for c in data})
ss.setdefault("chat", {})
ss.setdefault("crisis", {})
ss.setdefault("mood", [])
ss.setdefault("log", [])

# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.markdown('<div class="brand">BioOrbit</div><div class="sub">UTH · NASA Space Apps 2026</div>',
                unsafe_allow_html=True)
    crew = st.selectbox("Astronauta monitoreado", list(data))
    playing = st.toggle("Telemetría en vivo", True)
    radius = st.slider("Radio de aviso (m)", 5, 60, 20)
    st.divider()
    st.caption("Demostración")
    if st.button("Simular pérdida de signos vitales", width="stretch", type="primary"):
        ss.flat[crew] = ss.idx[crew]
    if st.button("Restablecer sensores", width="stretch"):
        ss.flat[crew] = None

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
    fig.update_layout(height=h, margin=dict(l=6, r=6, t=34, b=6), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9fb7d9", family="Sora"),
                      legend=dict(orientation="h", y=1.18, x=0))
    fig.update_xaxes(gridcolor="#38e1ff14", showline=False)
    fig.update_yaxes(gridcolor="#38e1ff14", showline=False)
    return fig


def dual(w, a, b, na, nb, ca, cb, title):
    f = make_subplots(specs=[[{"secondary_y": True}]])
    f.add_trace(go.Scatter(x=w.timestamp, y=w[a], name=na, connectgaps=False,
                           line=dict(color=ca, width=3, shape="spline")), secondary_y=False)
    f.add_trace(go.Scatter(x=w.timestamp, y=w[b], name=nb, connectgaps=False,
                           line=dict(color=cb, width=2, dash="dot")), secondary_y=True)
    f.update_layout(title=dict(text=title, font=dict(size=14, family="Chakra Petch"), x=0.01))
    return style(f)


# ---------------------------------------------------------------- monitor en vivo
def monitor(crew, radius, playing):
    df = data[crew]
    n = ss.idx[crew]
    i = n % len(df)
    row = df.iloc[i].copy()
    start = ss.flat[crew]
    if start is not None:
        row[VITAL] = np.nan

    status = alerts.vitals_status(row)
    em, now = ss.em[crew], time.time()
    if alerts.step(em, status, now) == "DUE":
        ss.log.insert(0, alerts.broadcast("NO_VITALS", crew, radius))
        em.phase = "SENT"
    if playing:
        ss.idx[crew] = n + 1

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
    elif em.phase == "SENT" and ss.log:
        last = ss.log[0]
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
    items = [("Frecuencia cardíaca", "hr", row["heart_rate_bpm"], "bpm", "{:.0f}"),
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
    if ss.log:
        chans = "<br>Último aviso: " + " · ".join(f"{n_}: {s}" for n_, s in ss.log[0]["channels"])
    st.markdown(f'<div class="panel"><div class="ttl" style="font-size:1.05rem;margin-bottom:8px">'
                f'Tripulantes que recibirían el aviso</div>'
                f'<table class="near"><tr><th>Persona</th><th>Rol</th><th>Módulo</th><th>Distancia</th></tr>{rows}</table>'
                f'<div class="sub" style="margin:10px 0 0">{chans}</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- compañero ORBI
def chat_tab():
    who = st.selectbox("¿Quién habla con ORBI?", list(alerts.ROSTER), key="who",
                       format_func=lambda c: f"{c} · {alerts.ROSTER[c]['role']}")
    hist = ss.chat.setdefault(who, [])
    row = data[who].iloc[ss.idx[who] % len(data[who])] if who in data else None
    if not hist:
        hist.append(("assistant", companion.greeting(who, row)))

    left, right = st.columns([3, 2], gap="large")
    with left:
        for role, txt in hist:
            with st.chat_message(role, avatar="🛰️" if role == "assistant" else "🧑‍🚀"):
                st.markdown(txt)
        msg = st.chat_input("Cuéntale a ORBI cómo te sientes", key="chat_in")
        if msg:
            hist.append(("user", msg))
            r = companion.reply(msg, who, row, hist)
            hist.append(("assistant", r.text))
            if r.crisis:
                ss.crisis[who] = True
            st.rerun()
    with right:
        st.markdown('<div class="panel"><div class="orbi"></div>'
                    '<div class="ttl" style="text-align:center;font-size:1.1rem">Respiración guiada</div>'
                    '<div class="breath"></div>'
                    '<div class="sub" style="text-align:center">Inhala, sostén, exhala, sostén. Cuatro segundos cada fase.</div></div>',
                    unsafe_allow_html=True)
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
        if ss.crisis.get(who):
            if st.button("Pedir apoyo humano ahora", type="primary", width="stretch"):
                res = alerts.broadcast("SUPPORT", who, radius)
                ss.log.insert(0, res)
                names = ", ".join(c for c, _, _ in res["notified"]) or "nadie dentro del radio"
                st.success(f"Aviso enviado. Avisados: {names}.")


tab1, tab2 = st.tabs(["Monitor de salud", "ORBI, tu compañero"])
with tab1:
    st.fragment(monitor, run_every=1.0 if playing else None)(crew, radius, playing)
with tab2:
    chat_tab()
