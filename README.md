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
5. **Datos NASA:** eventos de partículas solares de NASA DONKI y vista previa de datasets OSDR/LSDA cargados por el usuario.

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

La consola (`src/app.py`) muestra a toda la tripulación, compara señales, ordena los estados que requieren atención e
indica los dispositivos conectados y el historial de alertas. Combina el CSV seleccionado con telemetría de relojes,
HUDs y dispositivos remotos.

- `src/fleet_server.py` recibe reportes HTTP de otras laptops y dispositivos.
- `crew_server/server.py` ofrece cuentas de tripulación, chat y alertas de teléfonos. El dashboard enlaza con este
  servidor para mostrar los teléfonos, enviar mensajes/alertas y resolver alertas desde control.
- Las alertas generadas en control se comparten con los teléfonos; pueden cerrarse desde el teléfono o cuando se
  restablecen las señales vitales.

Ambos servicios son opcionales para la demo local. Puertos, red y configuración: [`docs/fleet_api.md`](docs/fleet_api.md)
y [`crew_server/README.md`](crew_server/README.md).

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

## 🪐 Integración de datos NASA

- **NASA Open APIs / DONKI SEP:** la pestaña **NASA y datasets** consulta eventos de partículas solares de los últimos 7 o 30 días.
  Se puede definir `NASA_API_KEY` antes de iniciar Streamlit; si no, se usa `DEMO_KEY` con sus límites de solicitudes.
- **OSDR y LSDA:** descarga un dataset de acceso abierto en formato CSV/TSV desde
  [NASA OSDR](https://osdr.nasa.gov/bio/repo/data/studies/) o [NASA Life Sciences Portal](https://nlsp.nasa.gov/explore),
  y cárgalo en la misma pestaña para ver sus columnas, una muestra y estadísticas numéricas. Se aceptan archivos de hasta 25 MB.
  El catálogo de estudios `data/osdr_catalog.csv` se conserva en el proyecto y se muestra automáticamente en Streamlit;
  también está disponible con búsqueda en **Catálogo OSDR de referencia** del dashboard de Control de misión.

Los eventos DONKI son contexto de actividad solar, no mediciones de dosis de radiación ni de salud de la tripulación.
Los datasets OSDR/LSDA se cargan localmente, se muestran como referencia y no se mezclan automáticamente con las alertas
o los CSV sintéticos del monitor.

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
│   ├── demo_stress_arc.csv              # Escenario de demostración sintético
│   ├── sample_astronaut_telemetry.csv   # Telemetría sintética de muestra
│   └── osdr_catalog.csv                # Catálogo OSDR guardado como referencia
├── src/
│   ├── app.py, fleet.py                 # Dashboard y registro de dispositivos
│   ├── fleet_server.py, crew_link.py    # Reportes remotos y enlace con teléfonos
│   ├── vision_monitor.py                # HUD de cámara, rostro y rPPG experimental
│   ├── ble_watch.py, watch_connect.py   # Conexión BLE a relojes
│   ├── companion.py, luma.py            # Luma, chat, bienestar y respiración guiada
│   ├── luma_avatar.py                   # Avatar de Luma
│   ├── nasa_data.py                     # API NASA DONKI y carga de datasets tabulares
│   ├── alerts.py, alert_listener.py     # Alertas y receptor UDP
│   ├── data_pipeline.py                 # Ingesta y cálculo de indicadores
│   └── generate_demo_data.py            # Generador de telemetría sintética
├── crew_server/                         # Cuentas, chat, alertas y dashboard de teléfonos
├── tests/                               # Pruebas de NASA, BLE, flota y enlace
├── wear-os-bridge/                      # App Wear OS (Kotlin) para transmitir pulso por BLE
├── docs/
│   ├── fleet_api.md                     # API e integración de dispositivos
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

Espera a que `pip` termine. Si la instalación se cancela, vuelve a ejecutar el último comando antes de iniciar la app.
Si PowerShell bloquea la activación, permite scripts solo para esa sesión y activa de nuevo el entorno:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2. Iniciar la consola principal

```powershell
python -m streamlit run src\app.py
```

Abre la URL que muestra Streamlit, normalmente `http://localhost:8501`. El dashboard funciona con telemetría CSV sin
reloj ni cámara; usa **Demo reloj** en la barra lateral para simular un reloj.

### 3. Iniciar el HUD de cámara (opcional)

En una segunda terminal, desde la carpeta del proyecto, activa `.venv` y ejecuta:

```powershell
.\.venv\Scripts\Activate.ps1
python src\vision_monitor.py
```

Permite el acceso a la cámara si Windows lo solicita. Para elegir cámara, astronauta o CSV:

```powershell
python src\vision_monitor.py 0 ASTRO-01 --csv=data\sample_astronaut_telemetry.csv
```

El pulso rPPG es experimental; SpO₂, temperatura, CO₂, radiación, HRV y sueño provienen del CSV salvo que un dispositivo los proporcione.

### 4. Conectar un reloj BLE (opcional)

En un reloj Wear OS compatible, abre `wear-os-bridge/`, pulsa **Iniciar transmisión** y acepta los permisos. Desde la
barra lateral del dashboard, pulsa **Buscar relojes cercanos** y **Conectar reloj**. También puedes iniciar la conexión
desde el HUD con la tecla **W**. Para probar sin hardware, selecciona **Demo reloj**.

### 5. NASA DONKI y datasets (opcional)

En la pestaña **NASA y datasets**, el dashboard consulta la API DONKI SEP automáticamente y permite cargar CSV/TSV
descargados de OSDR o LSDA. Para usar una clave NASA personal, defínela en PowerShell **antes** de iniciar Streamlit:

```powershell
$env:NASA_API_KEY = "TU_CLAVE_NASA"
python -m streamlit run src\app.py
```

Sin clave personal se usa `DEMO_KEY`. El archivo de referencia debe ser CSV/TSV y no superar 25 MB.

### 6. Habilitar dispositivos y teléfonos remotos (opcional)

Para reportes de otras laptops o dispositivos, inicia `fleet_server.py` en otra terminal:

```powershell
.\.venv\Scripts\Activate.ps1
python src\fleet_server.py
```

Para cuentas de astronautas, chat y alertas entre teléfonos y control, inicia el servidor de tripulación:

```powershell
python crew_server\server.py
```

Consulta [`docs/fleet_api.md`](docs/fleet_api.md) y [`crew_server/README.md`](crew_server/README.md) para puertos,
conexión por Wi-Fi y configuración opcional. No expongas los servidores a Internet sin protegerlos.

### 7. Pipeline y pruebas

```powershell
python src\data_pipeline.py data\sample_astronaut_telemetry.csv
python -m unittest discover -s tests -v
```

### Teclas del HUD

| Tecla | Acción |
| **S** | Simular pérdida de signos vitales |
| **C** | "Estoy bien" (cancela el aviso) |
| **B** | Respiración guiada |
| **P** | Pausar / reanudar la telemetría |
| **A / D** | Retroceder / avanzar en la misión |
| **W** | Conectar / desconectar el reloj |
| **N** | Siguiente astronauta |
| **Q / Esc** | Salir |

### Solución de problemas

- **`No module named streamlit`**: activa `.venv` y ejecuta `python -m pip install -r requirements.txt`; instala y ejecuta con el mismo Python.
- **Falta `bleak`**: con `.venv` activo, ejecuta `python -m pip install bleak`. El dashboard sigue funcionando con datos CSV sin Bluetooth.
- **La cámara no abre**: cierra otras aplicaciones que la estén usando y revisa los permisos de cámara de Windows.
- **El teléfono no encuentra el servidor**: ambos dispositivos deben estar en la misma red Wi-Fi; revisa el firewall y sigue [`crew_server/README.md`](crew_server/README.md).

## ⚠️ Alcance y limitaciones

Prototipo educativo, no dispositivo médico ni servicio de salud mental. Los CSV incluidos son sintéticos; los umbrales no
son orientación médica y el pulso por cámara es experimental. No usar para diagnóstico, tratamiento ni decisiones clínicas.
No envíes datos biométricos reales a servicios externos sin consentimiento informado.