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

## 🖥️ Consola de cabina (nueva)

```bash
streamlit run src/app.py
```

- **Monitor de salud futurista:** FC, HRV, SpO₂, temperatura, CO₂ y radiación en vivo (reproduce el CSV como flujo de telemetría).
- **ORBI, compañero virtual:** conversa con cada tripulante (`ASTRO-01…04`), responde con empatía, ofrece respiración guiada y registro de ánimo, y detecta señales de crisis para pedir apoyo humano. Funciona sin internet; si defines `ANTHROPIC_API_KEY` conversa con un modelo de lenguaje (se envía el chat y un resumen biométrico: úsalo solo con consentimiento).
- **Alerta por pérdida de signos vitales:** si faltan FC y SpO₂ varios segundos, la consola abre una cuenta regresiva de 10 s ("Estoy bien, cancelar aviso"). Si nadie la cancela, avisa a los tripulantes dentro del radio configurado por registro local, difusión UDP en la red (`python src/alert_listener.py` en los equipos receptores) y, opcionalmente, notificación push con `BIOORBIT_NTFY_TOPIC`.
- En la barra lateral, **"Simular pérdida de signos vitales"** sirve para demostrar el flujo completo en el video.

> ⚠️ **Alcance:** prototipo educativo, no un dispositivo médico ni un servicio de salud mental. La proximidad entre tripulantes está configurada en `src/alerts.py` (en un sistema real vendría de balizas BLE/UWB) y los datos de telemetría son sintéticos.

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
├── data/
│   └── sample_astronaut_telemetry.csv   # Dataset de bioseñales calibrado con rangos NASA
├── src/
│   ├── app.py                           # Consola de cabina (Streamlit)
│   ├── alerts.py                        # Detección de pérdida de signos vitales y avisos
│   ├── alert_listener.py                # Receptor de alertas para equipos cercanos
│   ├── companion.py                     # ORBI, compañero virtual
│   ├── data_pipeline.py                 # Pipeline de ingesta, cálculo de HRV y alertas
│   └── vision_monitor.py                # Módulo OpenCV de análisis de fatiga y postura
├── docs/
│   └── pitch_script_30s.md              # Guion oficial de pitch de 30 segundos en inglés
├── requirements.txt                     # Dependencias de Python
└── README.md                            # Documentación técnica del proyecto
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

### 3. Ejecutar el HUD de cámara (rediseñado)
```bash
python src/vision_monitor.py            # o: python src/vision_monitor.py 0 ASTRO-02
```
Teclas: **S** simular pérdida de signos vitales · **C** "estoy bien" · **B** respiración guiada · **Q** salir.
Pulso por rPPG experimental (real, con la cámara); SpO₂, temperatura, CO₂ y radiación son telemetría simulada del CSV y el HUD lo indica.

### 4. Consola web con ORBI
```bash
streamlit run src/app.py
```

---

## 🏆 Alineación con los Criterios de Evaluación de la NASA

- **Impacto (Impact):** Reduce la dependencia de telemedicina terrestre y mitiga riesgos de arritmias, pérdida ósea y fatiga crónica en misiones interplanetarias.
- **Creatividad (Creativity):** Fusión única de datos biomédicos tradicionales con visión artificial embebida en cabina para evaluación ergonómica y cognitiva sin contacto.
- **Validez (Validity):** Rangos normales y umbrales de alerta calibrados con literatura médica de la NASA y el *Human Research Program* (HRP).
- **Relevancia (Relevance):** Cumple con todos los lineamientos del desafío oficial de salud de astronautas 2026.
- **Presentación (Presentation):** Código modular y documentado, arquitectura reproducible y video pitch de 30 segundos estructurado en inglés.