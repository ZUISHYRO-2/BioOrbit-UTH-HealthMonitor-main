# BioOrbit-UTH / Astronaut Health Monitor
**NASA Space Apps Challenge 2026 — Sede Hermosillo, Sonora, México**  
**Desafío Oficial:** *Create Health Monitoring Software for Astronauts on Space Missions*  
**Equipo:** BioOrbit UTH (`yovani28`, líder mecatrónico)

---

## 🛰️ Resumen del Proyecto

**BioOrbit-UTH** es un prototipo educativo de monitoreo de salud para tripulaciones. Integra:
1. **Telemetría fisiológica:** reproducción de CSV y conexión opcional a reloj BLE para frecuencia cardíaca.
2. **Indicadores de riesgo:** cálculo de índices cardiovasculares, recuperación autonómica y riesgo ambiental a partir de las señales disponibles.
3. **HUD de cámara:** detección de rostro y estimación experimental del pulso por rPPG con OpenCV.
4. **Centro de control:** dashboard Streamlit para visualizar varios astronautas, dispositivos, gráficas e historial de alertas.

La mayor parte de la telemetría incluida es sintética. El proyecto no está validado clínicamente y no debe usarse para diagnóstico ni decisiones médicas.

---

## 🤖 Luma, el compañero a bordo

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

## 🛰️ Centro de control multi-astronauta

La consola (`src/app.py`) muestra una tarjeta por astronauta, compara sus señales y presenta dispositivos y alertas. Los datos
locales proceden del CSV seleccionado y de los puentes de reloj/cámara. Para recibir reportes de otras laptops se puede
iniciar `src/fleet_server.py`; para el servidor opcional de teléfonos, chat y alertas, se puede iniciar
`crew_server/server.py`. Consulta [`docs/fleet_api.md`](docs/fleet_api.md) para configuración y puertos.

## ⌚ Reloj inteligente por Bluetooth

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

Pruebas: `python -m unittest discover -s tests -v`

## 🚨 Alerta a tripulantes cercanos

Si faltan frecuencia cardíaca y SpO₂ varias lecturas seguidas, aparece una cuenta regresiva de 10 s ("Estoy bien").
Si nadie la cancela, avisa a los tripulantes dentro del radio configurado por registro local, difusión UDP en la red
(`python src/alert_listener.py` en los equipos receptores) y, opcionalmente, push con `BIOORBIT_NTFY_TOPIC`.

> ⚠️ **Alcance:** prototipo educativo, no un dispositivo médico ni un servicio de salud mental. La proximidad entre
> tripulantes está configurada en `src/alerts.py` (en un sistema real vendría de balizas BLE/UWB) y la telemetría es
> **simulada**: `data/demo_stress_arc.csv` (generado con `src/generate_demo_data.py`, ASTRO-02 se desgasta poco a poco)
> y `data/sample_astronaut_telemetry.csv`. No son datos reales de la NASA.

---

## 📊 Fuentes de referencia

- **[NASA Open Science Data Repository (OSDR)](https://science.nasa.gov/biological-physical/data/osdr/)**
- **[NASA Life Sciences Portal (NLSP / LSDA)](https://www.nasa.gov/hrp/nlsp/)**
- **[NASA Open APIs](https://api.nasa.gov/)**

Estas fuentes sirven como referencia; el proyecto no descarga ni integra sus datasets o APIs durante la ejecución. Los CSV incluidos son sintéticos.

---

## 🛠️ Tecnologías

- Python 3.10 o superior; probado como aplicación local en Windows.
- `pandas` y `numpy` para telemetría y cálculos; `OpenCV` y Pillow para el HUD.
- Streamlit y Plotly para la consola; `bleak` para Bluetooth Low Energy.
- El servidor de tripulación (`crew_server/`) usa la biblioteca estándar de Python y SQLite.

---

## 📁 Estructura del Repositorio

```text
BioOrbit-UTH-HealthMonitor/
├── .streamlit/config.toml               # Tema de Streamlit
├── data/
│   ├── demo_stress_arc.csv              # Escenario sintético de demostración
│   └── sample_astronaut_telemetry.csv   # Telemetría sintética de muestra
├── src/
│   ├── app.py, fleet.py                 # Dashboard y registro local de dispositivos
│   ├── fleet_server.py                  # Receptor HTTP de otras laptops/dispositivos
│   ├── crew_link.py                     # Enlace del dashboard con el servidor de tripulación
│   ├── vision_monitor.py                # HUD de cámara y estimación experimental rPPG
│   ├── ble_watch.py, watch_connect.py   # Reloj BLE y cliente de terminal
│   ├── companion.py, luma.py            # Compañero Luma, consejos y bienestar
│   ├── luma_avatar.py                   # Avatar de Luma
│   ├── alerts.py, alert_listener.py     # Alertas locales y receptor UDP
│   ├── data_pipeline.py                 # Ingesta y cálculo de indicadores
│   └── generate_demo_data.py            # Generador de telemetría sintética
├── crew_server/                         # Servidor local para teléfonos, chat y alertas
├── tests/                               # Pruebas unitarias de BLE, flota y enlace
├── wear-os-bridge/                      # App Wear OS (Kotlin) que anuncia pulso por BLE
├── docs/
│   ├── fleet_api.md                     # Conexión de dispositivos y servidores
│   ├── pitch_script_30s.md              # Guion de pitch
│   └── vista_previa_hud.png             # Vista previa del HUD
├── requirements.txt
└── README.md
```

---

## 🚀 Guía de Instalación y Ejecución Rápida

### 1. Preparar el entorno en Windows

Abre PowerShell en la carpeta del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Deja que `pip` termine; si la instalación se cancela, vuelve a ejecutar el último comando antes de iniciar la app.

Si PowerShell bloquea la activación del entorno, permite scripts solo para esa sesión y actívalo de nuevo:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2. Iniciar la consola principal

Con `.venv` activo:

```powershell
python -m streamlit run src\app.py
```

Abre la URL que muestra Streamlit, normalmente `http://localhost:8501`. La consola reproduce telemetría de los CSV;
no requiere reloj ni cámara. En la barra lateral puedes usar **Demo reloj** para simular una conexión.

### 3. Iniciar el HUD de cámara (opcional)

Abre una segunda terminal en la carpeta del proyecto y activa `.venv` en ella:

```powershell
.\.venv\Scripts\Activate.ps1
python src\vision_monitor.py
```

Permite el acceso a la cámara si Windows lo solicita. Para elegir cámara, astronauta o CSV:

```powershell
python src\vision_monitor.py 0 ASTRO-01 --csv=data\sample_astronaut_telemetry.csv
```

El pulso rPPG es experimental. SpO₂, temperatura, CO₂, radiación, HRV y sueño provienen del CSV si un dispositivo real no los proporciona.

### 4. Conectar un reloj BLE (opcional)

En un reloj Wear OS compatible, instala y abre `wear-os-bridge/`, pulsa **Iniciar transmisión** y acepta los permisos.
Después, desde la barra lateral del dashboard pulsa **Buscar relojes cercanos** y **Conectar reloj**. También puedes
conectar desde el HUD o usar el cliente de terminal:

```powershell
python src\watch_connect.py
```

El cliente de terminal es una alternativa de conexión; para usar el reloj en el dashboard, conéctalo desde el dashboard.

### 5. Servicios adicionales (opcionales)

Para recibir reportes de otras laptops en la misma red, abre otra terminal, activa `.venv` y ejecuta:

```powershell
python src\fleet_server.py
```

Para el servidor de tripulación (cuentas, chat y alertas de teléfonos), abre otra terminal y ejecuta:

```powershell
python crew_server\server.py
```

Sus puertos y configuración están descritos en [`docs/fleet_api.md`](docs/fleet_api.md) y [`crew_server/README.md`](crew_server/README.md).
No expongas estos servicios a Internet sin una configuración de seguridad adecuada.

### 6. Pipeline y pruebas

Procesar una muestra desde la terminal:

```powershell
python src\data_pipeline.py data\sample_astronaut_telemetry.csv
```

Ejecutar las pruebas:

```powershell
python -m unittest discover -s tests -v
```

### Teclas del HUD

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

### Solución de problemas

- **`No module named streamlit`**: activa `.venv` y ejecuta `python -m pip install -r requirements.txt`. Asegúrate de
  instalar y correr la app con el mismo intérprete de Python.
- **Falta `bleak`**: con `.venv` activo ejecuta `python -m pip install bleak` o vuelve a instalar `requirements.txt`.
  La consola sigue funcionando con datos simulados sin Bluetooth.
- **La cámara no abre**: cierra otras aplicaciones que la estén usando y verifica los permisos de cámara de Windows.
- **No aparece el reloj**: activa Bluetooth, abre BioOrbit Watch Bridge en el reloj e inicia la transmisión; algunos
  dispositivos no anuncian el servicio cardíaco mientras la pantalla está apagada.

## ⚠️ Alcance y limitaciones

Es un prototipo para demostración, no un dispositivo médico ni un servicio de salud mental. Los CSV incluidos son sintéticos,
los umbrales no constituyen orientación médica y el pulso por cámara es experimental. No se debe usar para diagnosticar,
tratar ni tomar decisiones clínicas. Evita enviar datos biométricos reales a servicios externos sin consentimiento informado.
