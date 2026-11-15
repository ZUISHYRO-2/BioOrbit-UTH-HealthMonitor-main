# BioOrbit-UTH / Astronaut Health & Dev 🚀
**NASA Space Apps Challenge 2026 — Sede Hermosillo, Sonora, México**  
**Desafío Oficial:** *Create Health Monitoring Software for Astronauts on Space Missions*  
**Equipo:** BioOrbit UTH (`yovani28`, líder mecatrónico)

---

## 🛰️ Resumen del Proyecto

Durante misiones de espacio profundo hacia la Luna y Marte, las tripulaciones enfrentan ambientes hostiles caracterizados por microgravedad constante, radiación ionizante acumulada, confinamiento y estrés fisiológico. Debido a los retrasos en las comunicaciones tierra-espacio (hasta 20 minutos en Marte), los astronautas requieren autonomía médica inmediata para monitorear, diagnosticar y responder a riesgos de salud sin asistencia en tiempo real de los cirujanos de vuelo.

**BioOrbit-UTH** es una plataforma de software distribuida y predictiva que integra:
1. **Pipeline de Telemetría Fisiológica:** Ingesta de bioseñales clave (Frecuencia Cardíaca, Variabilidad de Frecuencia Cardíaca - HRV RMSSD, SpO2, Temperatura y Dosimetría de Radiación).
2. **Motor de Inferencia de Riesgo Multivariable:** Algoritmos que calculan índices compuestos de estrés cardiovascular, recuperación autonómica y amenaza ambiental.
3. **Monitor Óptico en Cabina (OpenCV):** Detección sin contacto de fatiga visual, microexpresiones de estrés y desalineación postural durante ejercicios en microgravedad.
4. **Consola Táctica de Cabina:** Dashboard interactivo optimizado para alta visibilidad y toma de decisiones preventiva.

---

## 🤖 Luma, el compañero a bordo (nuevo)

Luma es un pequeño robot flotante (diseño original del equipo) que acompaña a la tripulación en el
aislamiento de una misión larga. Tiene 5 estados de ánimo que cambian solos según la situación:

| Estado | Cuándo aparece |
|---|---|
| **Reposo** (verde) | Señales estables |
| **Curioso** (azul) | Desgaste leve o cuando aún no encuentra tu rostro |
| **Preocupado** (ámbar) | Desgaste alto, pérdida de signos vitales o frases de crisis |
| **Calma** (ojos felices) | Durante la respiración guiada |
| **Hablando** | Cuando te acaba de decir algo |

- **En el HUD de cámara** (`vision_monitor.py`): Luma vive en la tarjeta inferior izquierda, **te mira** (sus ojos siguen tu rostro),
  su corazón late al ritmo de tu pulso y te da consejos según tu HRV, sueño, alertas y estabilidad de cabeza.
- **En la consola web** (`app.py`): conversa con cada tripulante (`ASTRO-01…04`), respiración guiada, registro de ánimo
  y **check-in WHO-5** (índice de bienestar de la OMS). Si el check-in sale muy bajo, o bajo con desgaste fisiológico alto,
  sugiere avisar al cirujano de vuelo y activa "Pedir apoyo humano ahora".
- Funciona **sin internet** con reglas. Si defines `ANTHROPIC_API_KEY`, conversa con un modelo de lenguaje (se envía el chat
  y un resumen biométrico: úsalo solo con consentimiento).
- Es un acompañante: **no diagnostica** ni sustituye a la tripulación ni al equipo médico.

## 🎯 Rostro fijado en el HUD

El HUD detecta tu cara con OpenCV (dos modelos Haar, imagen ecualizada) y la **deja enclavada**: una retícula se cierra
sobre tu rostro, con anillo giratorio y barrido. Una vez fijada, sigue a esa misma cara e ignora detecciones falsas de un
instante; solo cambia de cara si la otra persiste ~0.5 s. Sobre esa región mide el pulso por rPPG.

## 🛰️ Centro de control multi-astronauta (nuevo)

La primera pestaña de la consola (`streamlit run src/app.py`) muestra a **toda la tripulación a la vez**: una tarjeta por
astronauta (estado, FC, SpO₂, HRV, temperatura, ánimo de Luma, dispositivos conectados), los más urgentes primero, gráficas
comparativas, tabla de dispositivos con su estado (en línea / retrasado / sin señal) e historial de avisos. Las alertas por
pérdida de signos vitales ahora se vigilan para **todos** los astronautas, no solo el que estás monitoreando.
Los teléfonos se enlazan con `python crew_server/server.py` y otras laptops con `python src/fleet_server.py`; detalles en [`docs/fleet_api.md`](docs/fleet_api.md).

La consola y los teléfonos están **enlazados en los dos sentidos**: la consola ve el estado y las alertas de cada teléfono,
y en la pestaña **Chat de tripulación** el control de misión escribe a todos o en privado. Las alertas que detecta la consola
(pérdida de signos, apoyo humano) llegan también a los teléfonos y se cierran solas cuando vuelven las señales.

## 📱 App para teléfono y servidor de tripulación (nuevo)

- **App Android** (`android-app/`): Luma por voz (escucha permanente, IA opcional con tu propia clave), cámara con pulso y
  alerta «nadie en cámara», reloj por Bluetooth, SOS por voz, música por voz y funcionamiento en segundo plano.
- **Cuentas de astronauta:** cada quien inicia sesión en su teléfono (mientras está el login, todo lo demás queda apagado).
- **Pestaña Equipo:** quién está en línea, su pulso y alertas («Voy en camino»), chat general, privado y con Control.
  Por voz: «dile a Ana que ya voy», «¿tengo mensajes?».
- **Servidor de tripulación** (`crew_server/`): guarda cuentas y chat, y sirve un **dashboard web** en `http://localhost:8765`
  con tarjetas por astronauta, **Dispositivos conectados**, alertas y chat. En el mismo Wi-Fi los teléfonos lo encuentran solos;
  con datos móviles se usa un túnel https (`crew_server/tunel.py`). Detalles en [`crew_server/README.md`](crew_server/README.md).

## ⌚ Reloj inteligente por Bluetooth (nuevo)

La frecuencia cardíaca puede venir de un **reloj real** en lugar del CSV simulado:

1. **En el reloj (Pixel Watch / Wear OS):** instala la app `wear-os-bridge/` (ábrela en Android Studio y córrela en el reloj).
   Abre **BioOrbit Watch Bridge**, pulsa **Iniciar transmisión** y acepta los permisos. El reloj anuncia el perfil
   estándar Bluetooth *Heart Rate* (0x180D) con tu pulso cada segundo.
2. **En la laptop**, conéctalo de cualquiera de estas formas:
   - **HUD de cámara** → botón **Conectar reloj** arriba (o tecla **W**): busca 10 s y se conecta solo al reloj.
     El botón **Demo** simula un reloj; **Desconectar reloj** lo suelta.
   - Consola web → barra lateral → **Buscar relojes cercanos** → elige el reloj → **Conectar reloj**.
   - Terminal: `python src/watch_connect.py` (Q o Esc para desconectar).
3. El HUD de cámara y la consola leen el reloj solos (archivo `data/live_watch_telemetry.json`).
   El reloj se asigna al astronauta que estás monitoreando.

Sin reloj físico, el botón **Demo reloj** simula uno mandando pulso.

**Pérdida de signos vitales con el reloj:** si el reloj estaba conectado y **deja de mandar pulso** (se lo quitan, se
queda sin batería, sale de alcance) por más de 8 s, cuenta como pérdida de signos vitales: cuenta regresiva de 10 s y,
si nadie pulsa "Estoy bien", aviso a los tripulantes cercanos. Si lo desconectas a propósito, no hay alarma.

El Pixel Watch solo manda frecuencia cardíaca (sin intervalos RR), así que la HRV se queda con la telemetría simulada;
con una banda o reloj que mande intervalos RR, la HRV se calcula en vivo (RMSSD). Funciona con cualquier dispositivo
que tenga el perfil cardíaco estándar (bandas Polar, Garmin, etc.). En Windows usa el Bluetooth de la laptop (librería `bleak`).

Pruebas: `python -m unittest tests.test_ble_watch`

## 🚨 Alerta a tripulantes cercanos

Si faltan frecuencia cardíaca y SpO₂ varias lecturas seguidas, aparece una cuenta regresiva de 10 s ("Estoy bien").
Si nadie la cancela, avisa a los tripulantes dentro del radio configurado por registro local, difusión UDP en la red
(`python src/alert_listener.py` en los equipos receptores) y, opcionalmente, push con `BIOORBIT_NTFY_TOPIC`.

> ⚠️ **Alcance:** prototipo educativo, no un dispositivo médico ni un servicio de salud mental. La proximidad entre
> tripulantes está configurada en `src/alerts.py` (en un sistema real vendría de balizas BLE/UWB) y la telemetría es
> **simulada**: `data/demo_stress_arc.csv` (generado con `src/generate_demo_data.py`, ASTRO-02 se desgasta poco a poco)
> y `data/sample_astronaut_telemetry.csv`. No son datos reales de la NASA.

---

## 📊 Fuentes de Datos Abiertas de la NASA Utilizadas

- **[NASA Open Science Data Repository (OSDR)](https://science.nasa.gov/biological-physical/data/osdr/):** Parámetros de referencia omicos y biomarcadores de astronautas en misiones de larga duración.
- **[NASA Life Sciences Portal (NLSP / LSDA)](https://www.nasa.gov/hrp/nlsp/):** Datos fisiológicos de misiones análogas de reposo en cama (*bedrest studies*) y telemetría histórica de la ISS.
- **[NASA Open APIs](https://api.nasa.gov/):** Variables de radiación y clima espacial para correlación ambiental.

---

## 🛠️ Arquitectura de Software y Stack Tecnológico

El proyecto sigue las directrices técnicas de ingeniería y digitalización de `@gemini-spark-instructions`:
- **Entorno de Programación:** Python 3.10+ en VS Code.
- **Procesamiento de Bioseñales:** `pandas`, `numpy`, `scipy`.
- **Visión Computacional:** `OpenCV` (detección óptica de fatiga y monitoreo biomecánico).
- **Consola / UI:** Streamlit / Plotly con interfaz táctil en modo nocturno de baja luminancia para cabina espacial.

---

## 📁 Estructura del Repositorio

```text
BioOrbit-UTH-HealthMonitor/
├── .streamlit/config.toml               # Tema oscuro de la consola
├── data/
│   ├── demo_stress_arc.csv              # Escenario simulado para el demo (4 astronautas; ASTRO-02 se desgasta)
│   └── sample_astronaut_telemetry.csv   # Telemetría simulada (4 tripulantes)
├── src/
│   ├── app.py                           # Consola de cabina (Streamlit) + Luma + WHO-5
│   ├── vision_monitor.py                # HUD de cámara: rostro fijado, pulso rPPG, Luma, alertas
│   ├── luma.py                          # Luma: dibujo animado (OpenCV y HTML) y estados de ánimo
│   ├── companion.py                     # Cerebro de Luma: chat, consejos, WHO-5, lectura de señales
│   ├── alerts.py                        # Pérdida de signos vitales y avisos a cercanos
│   ├── alert_listener.py                # Receptor de alertas para equipos cercanos
│   ├── ble_watch.py                     # Reloj por Bluetooth LE: escaneo, conexión, pulso, HRV
│   ├── watch_connect.py                 # Conectar el reloj desde la terminal
│   ├── data_pipeline.py                 # Pipeline de ingesta, HRV, alertas y dosis de radiación
│   ├── generate_demo_data.py            # Genera demo_stress_arc.csv
│   ├── crew_link.py                     # Enlace consola <-> teléfonos (estado, alertas, chat)
│   ├── fleet.py / fleet_server.py       # Dispositivos: reloj, HUD de otras laptops (puerto 8766)
│   └── luma_avatar.py                   # Avatar de Luma
├── crew_server/                         # Servidor de tripulación: cuentas, chat, alertas, dashboard web (8765)
├── android-app/                         # App del teléfono (APK): Luma, cámara, reloj, alertas, pestaña Equipo
├── tests/                               # Pruebas: reloj, dispositivos, enlace con teléfonos
├── wear-os-bridge/                      # App para el reloj (Kotlin): transmite el pulso por BLE
├── docs/
│   ├── fleet_api.md                     # Cómo se conecta cada dispositivo
│   ├── pitch_script_30s.md              # Guion de pitch de 30 segundos en inglés
│   └── vista_previa_hud.png             # Captura del HUD
├── requirements.txt
└── README.md
```

---

## 🚀 Guía de Instalación y Ejecución Rápida

### 1. Clonar y preparar entorno
```bash
git clone https://github.com/yovani28/BioOrbit-UTH-HealthMonitor.git
cd BioOrbit-UTH-HealthMonitor
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Ejecutar el Pipeline de Telemetría Biomédica
```bash
python src/data_pipeline.py data/sample_astronaut_telemetry.csv
```

### 3. HUD de cámara con Luma
```bash
python src/vision_monitor.py                      # cámara automática, demo_stress_arc.csv, ASTRO-02
python src/vision_monitor.py 0 ASTRO-01 --csv=data/sample_astronaut_telemetry.csv
```
| Tecla | Acción |
|---|---|
| **S** | Simular pérdida de signos vitales |
| **C** | "Estoy bien" (cancela el aviso) |
| **B** | Respiración guiada (Luma pasa a calma) |
| **P** | Pausar / reanudar la telemetría |
| **A / D** | Retroceder / avanzar en la misión |
| **W** | Conectar / desconectar el reloj (igual que el botón) |
| **N** | Siguiente astronauta |
| **Q / Esc** | Salir |

Pulso por rPPG experimental (real, con la cámara; necesita buena luz y quedarte quieto). SpO₂, temperatura, CO₂,
radiación, HRV y sueño son telemetría simulada del CSV y el HUD lo indica.

### 4. Consola web con Luma
```bash
streamlit run src/app.py
```
Se pueden correr los dos a la vez: la consola muestra en la barra lateral si el HUD está conectado y el pulso que mide la cámara.

### 5. Teléfonos de la tripulación
```bash
python crew_server/server.py          # en otra terminal; la primera vez crea la contraseña de «control»
```
1. Instala el APK de `android-app/` en cada teléfono (Android Studio → Build → Generate APKs).
2. En la app: **Crear cuenta** (nombre, puesto ASTRO-01…04, usuario y contraseña). En el mismo Wi-Fi el servidor aparece solo.
3. La consola (`streamlit run src/app.py`) entra sola como «control»: tarjetas de cada teléfono en **Centro de control** y
   chat en **Chat de tripulación**. También está el dashboard web en `http://localhost:8765`.
4. Windows Firewall: permite Python en **redes privadas**, si no, los teléfonos no se conectan.

### 6. Pruebas
```bash
python -m pytest tests -q
```

---

## 🏆 Alineación con los Criterios de Evaluación de la NASA

- **Impacto (Impact):** Reduce la dependencia de telemedicina terrestre y mitiga riesgos de arritmias, pérdida ósea y fatiga crónica en misiones interplanetarias.
- **Creatividad (Creativity):** Fusión única de datos biomédicos tradicionales con visión artificial embebida en cabina para evaluación ergonómica y cognitiva sin contacto.
- **Validez (Validity):** Rangos normales y umbrales de alerta calibrados con literatura médica de la NASA y el *Human Research Program* (HRP).
- **Relevancia (Relevance):** Cumple con todos los lineamientos del desafío oficial de salud de astronautas 2026.
- **Presentación (Presentation):** Código modular y documentado, arquitectura reproducible y video pitch de 30 segundos estructurado en inglés.