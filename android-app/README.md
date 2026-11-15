# BioOrbit para Android (teléfono)

App de teléfono con lo principal del proyecto en pantalla vertical:

| Pestaña | Qué hace |
|---|---|
| **Monitor** | Cámara frontal con **rostro fijado**, pulso por cámara (rPPG experimental), Luma, **reloj por Bluetooth**, telemetría y **alerta de signos vitales** |
| **Luma** | Chat con Luma, respiración guiada, check-in WHO-5 y botón «Pedir apoyo humano» |
| **Alertas** | Alertas **recibidas** de otros teléfonos/laptops y alertas **enviadas** |

## Nadie en cámara y voz de Luma
Con la cámara encendida, si no aparece nadie durante **20 s** (ajustable en *Demostración*):
1. Luma **habla** ("no te veo en la cámara"), el teléfono **vibra** y sale una cuenta regresiva de 15 s con **Estoy aquí**.
2. Si nadie lo toca, se **envía la alerta** a los tripulantes cercanos (tipo `NO_PRESENCE`), y Luma sigue
   anunciando en voz alta y vibrando para que lo note quien esté cerca del teléfono.
3. Cuando la cara vuelve a aparecer, se cancela solo ("Ya te veo").

Luma también habla en las alertas de signos vitales y cuando llega una alerta de otro equipo. La voz usa el
motor de texto a voz del teléfono en español; los avisos urgentes salen por el **canal de alarma** (suenan
aunque el volumen multimedia esté bajo). Se puede apagar con **Voz de Luma**. Si no se oye nada, revisa en
Ajustes del teléfono → *Salida de texto a voz* que esté instalado el idioma español.

La vigilancia solo funciona con la app abierta en pantalla y la cámara encendida.

## Escucha permanente y gráfica del sonido
Desde que se abre la app, el micrófono queda **escuchando todo el tiempo** (botón 🎤 de la barra inferior, debajo de las pestañas,
para apagarlo, o *Escucha permanente* en Demostración). La barra muestra la **gráfica en vivo del nivel de
sonido** que capta el micrófono y el texto de lo que va entendiendo. Mientras Luma habla, la escucha se pausa
(no se escucha a sí misma) y se reanuda sola. Con la app en segundo plano se pausa (Android no deja usar el
micrófono ahí sin un servicio especial).

**Luma contesta todo lo que le digas** (opción *Responder a todo lo que escuche*, encendida por defecto):
cada frase que escucha va a la IA (o a sus respuestas básicas) y responde en voz alta. Para que no se vuelva
un caos: ignora su propio eco (lo que ella acaba de decir) y contesta frases
de una sola palabra también ("hola", "gracias", "¿y tú?"): es una plática normal, de cualquier tema, con
preguntas de seguimiento; solo ignora ruidos ("eh", "mmm"). Si hablas mientras piensa, lo guarda y lo contesta
al terminar. Ojo: también contesta a otras personas cerca o a la tele, y cada frase usa la cuota de la IA.
Si apagas la opción, solo contesta cuando la frase **empieza con "Luma…"** ("Luma, ¿cómo estás?", "oye Luma").

Siempre, con o sin esa opción:
- en una alerta, **"estoy bien" / "estoy aquí" / "cancela"** la detiene;
- **"ayuda", "auxilio" o "socorro"** inicia el **SOS por voz** (10 s para decir "cancela"; si no, se avisa a la
  tripulación cercana con una alerta tipo `SOS`). Se desactiva con *SOS por voz*.

En Android 13+ con el paquete de español instalado se usa el **reconocimiento en el teléfono** (sin pitidos y
sin internet). Si no, se usa el de Google y, para que no pite en cada reinicio, la app silencia el volumen
multimedia mientras escucha y lo devuelve antes de que Luma hable. Al abrir la app pide juntos los permisos de
cámara, micrófono y notificaciones.

### Si Luma no te contesta
En **Monitor → Demostración → Diagnóstico de voz** se ve qué pasa:
- *Permiso de micrófono: NO* → Ajustes del teléfono → Apps → BioOrbit → Permisos → Micrófono → Permitir.
- *Nivel de sonido: no llega* → el micrófono no está grabando (otro app lo usa, o falta permiso).
- *Último evento: error 12/13* → falta el español sin conexión: activa **Usar reconocimiento en línea**.
- *Última frase oída* aparece pero *Qué hice: ignoré…* → dice por qué (muy corta, o parecía su propia voz).
- *Voz de Luma* → toca **Probar voz de Luma**; si no se oye, revisa el volumen y que el motor de texto a voz
  tenga español (Ajustes → Sistema → Idiomas → Salida de texto a voz).

## Tripulación: cuentas, chat y dashboard

Cada astronauta inicia sesión en su teléfono. Los teléfonos se conectan al servidor de la PC
(`crew_server/`, ver su README), que también muestra el dashboard de monitoreo.

- Al abrir la app aparece **Iniciar sesión / Crear cuenta**. En el mismo Wi-Fi el servidor se encuentra solo.
  Con datos móviles se usa la dirección https del túnel (se aprende sola o se escribe a mano).
  «Usar sin cuenta» deja la app como antes (solo este teléfono).
- Pestaña **Equipo**: quién está en línea, su pulso y si está en cámara, sus alertas («Voy en camino»),
  chat general, privado con cada compañero y con Control.
- Mensajes nuevos: aviso, vibración y Luma los lee en voz alta (se puede apagar). Con la app minimizada llega notificación.
- Por voz: «dile a Ana que ya voy», «manda un mensaje a la tripulación: junta a las 5», «¿tengo mensajes?».
- Las alertas también van al servidor, así que llegan a los demás aunque estén con datos móviles.

## Segundo plano

Con **Seguir en segundo plano** (Demostración, encendido por defecto) la app sigue funcionando al minimizarla:
un servicio con notificación fija «BioOrbit · Luma» mantiene vivos el micrófono, la voz de Luma, el SOS por voz,
el reloj, las alertas de la tripulación y la música. El botón **Salir** de esa notificación lo apaga todo.

- El botón «atrás» ya no cierra la app: la manda al fondo.
- La cámara sí se pausa (Android no deja usarla minimizada), así que la alerta «nadie en cámara» solo vigila con la app en pantalla.
- Si deslizas la app para cerrarla desde Recientes, se detiene todo.
- **Samsung / Xiaomi**: toca «Quitar límite de batería» (o en Ajustes → Batería → Límites de uso en segundo plano,
  saca BioOrbit de «Apps en suspensión»). Si no, el sistema puede cerrarla después de un rato.

## Música por voz

Dile a Luma lo que quieres oír (con la escucha permanente o escribiéndolo en el chat):

| Dices | Qué hace |
|---|---|
| «pon música», «pon mi música» | Pone la música guardada en el teléfono en aleatorio (si no hay, radio relajante) |
| «ponme a Bad Bunny», «reproduce Despacito» | La busca en el teléfono; si no está, la abre en Spotify / YouTube Music |
| «pon música relajante / para dormir / espacial / de la NASA / rock / jazz / de los 80 / para bailar» | Radio por internet de ese género (SomaFM, sin anuncios) |
| «pausa», «continúa», «siguiente», «sube / bájale al volumen», «quita la música», «¿qué canción es?» | Controles (funcionan sin decir «Luma») |

- **Spotify**: con «Canciones y artistas en Spotify» (encendido) los artistas y canciones se abren en Spotify
  (o YouTube Music si no hay Spotify). También puedes decir «pon Despacito **en Spotify**».
  Spotify no deja que otras apps le den play directo: a veces solo abre la búsqueda. Luma revisa a los 5 s
  y, si no suena, te dice que toques la canción. Para play automático garantizado haría falta el SDK de
  Spotify (cuenta Premium + registrar la app en developer.spotify.com).
  Con la app minimizada Android no deja abrir otra app: Luma deja una notificación para tocarla.
- Mientras suena música, Luma **solo contesta si empiezas con «Luma…»**, para no responderle a la canción.
  Al decir «Luma» la música baja y te escucha; también baja mientras Luma habla.
- La primera vez pide permiso de **música y audio** para leer las canciones del teléfono.
- En la parte de abajo aparece una barra con ⏯ ⏭ ■ mientras hay música.

## Hablar con Luma (micrófono) e inteligencia artificial
- **Micrófono 🎤** en la pestaña Luma: hablas y Luma te responde en voz alta. Con **Modo conversación**,
  vuelve a escucharte sola después de cada respuesta (se pausa si no oye nada dos veces).
- **En una alerta** (signos vitales o nadie en cámara) Luma pregunta en voz alta y escucha: basta decir
  **"estoy bien"** o **"estoy aquí"** para cancelarla. Se desactiva con *Responder alertas con la voz*.
- Decir o escribir "respiración guiada" abre el ejercicio.
- Usa el reconocimiento de voz de Google del teléfono. Sin internet funciona si descargas el español sin
  conexión: Ajustes → Google → *Reconocimiento de voz* (o *Voz*) → *Idiomas sin conexión* → Español.

**IA (Gemini o Claude):** Luma conversa con un modelo de lenguaje si guardas una clave de API:
- **Gemini (Google):** crea la clave gratis en **aistudio.google.com** → *Get API key*. Las claves nuevas
  empiezan con `AQ.` (formato nuevo de Google) o `AIza`. Modelos: `gemini-3.5-flash-lite`; si no está
  disponible para tu clave, la app usa `gemini-3.5-flash` o `gemini-2.5-flash` sola y lo recuerda.
- **Claude (Anthropic):** clave `sk-ant-…` de **console.anthropic.com** (prepago). Modelo `claude-haiku-5-5`.

En la app: pestaña **Luma → Inteligencia artificial**, pega la clave y toca **Guardar**. La app detecta
sola si es de Gemini o de Claude.

La clave se guarda solo en ese teléfono (almacenamiento privado de la app): **no va escrita en el código
ni dentro del APK**, así que puedes compartir el APK o subir el proyecto a GitHub sin exponerla. Google
recomienda no meter claves en apps móviles porque se pueden extraer, y bloquea automáticamente las
claves que detecta filtradas. Se envían al servicio de IA los últimos mensajes del chat y un resumen de la
telemetría; úsala solo con el consentimiento de quien conversa. Sin clave, sin cuota o sin internet, Luma
usa sus respuestas básicas. Las frases de crisis nunca pasan por la IA. Los modelos se cambian en `LumaAI.kt`.

## Cómo obtener el APK

### Opción A: Android Studio (en tu laptop)
1. Abre Android Studio → **Open** → elige la carpeta `android-app`.
2. Espera a que termine "Gradle sync" (la primera vez descarga cosas, tarda unos minutos).
3. Menú **Build → Build App Bundle(s) / APK(s) → Build APK(s)**.
4. El APK queda en `android-app/app/build/outputs/apk/debug/app-debug.apk`.
5. Pásalo al teléfono (cable, Drive o WhatsApp) y ábrelo. Android pedirá permitir
   "instalar apps de origen desconocido": acéptalo para tu gestor de archivos.

También puedes conectar el teléfono por USB (con *Depuración USB* activada) y darle **Run ▶**.

> Requiere Android Studio Meerkat (2024.3) o más nuevo. El proyecto usa Gradle 8.14.3 y AGP 8.9.2.

### Opción B: GitHub, sin instalar nada
1. Sube todo el proyecto a un repositorio de GitHub.
2. Ve a la pestaña **Actions** → **APK Android** (se ejecuta solo al subir cambios, o con **Run workflow**).
3. Cuando termine, en **Artifacts** descarga `BioOrbit-telefono-apk` (y `BioOrbit-reloj-apk` para el reloj).

## Primer uso
1. Abre **BioOrbit** y acepta la cámara y las notificaciones.
2. En **Demostración**, elige de quién es el teléfono (ASTRO-01 a 04).
3. **Reloj:** abre *BioOrbit Watch Bridge* en el reloj → *Iniciar transmisión*. En el teléfono toca
   **Conectar reloj** (pide permiso de Bluetooth). Si solo hay un reloj con perfil cardíaco, se conecta solo;
   si hay varios, elige de la lista. Sin reloj, toca **Demo**.
4. **Alertas a personas cercanas:** todos los teléfonos y laptops deben estar en la **misma red Wi-Fi**.
   Las laptops reciben con `python src/alert_listener.py`; los teléfonos con la app abierta reciben
   notificación con vibración.

## Cómo funciona por dentro
- La interfaz está en `app/src/main/assets/` (HTML/CSS/JS) y se muestra en un WebView.
  Se puede probar en la laptop sin compilar:
  `cd android-app/app/src/main/assets && python -m http.server 8000` y abrir `http://localhost:8000`
  (en Chrome, el reloj funciona con Web Bluetooth).
- Kotlin (`app/src/main/java/org/bioorbit/mobile/`) hace lo que solo el teléfono puede hacer:
  - `WatchBle.kt`: Bluetooth LE con el perfil cardíaco estándar 0x180D/0x2A37 (igual que `src/ble_watch.py`).
  - `NearbyAlerts.kt`: envía y recibe alertas UDP en el puerto 50505 (mismo formato que `src/alerts.py`).
  - `Notifier.kt`: notificaciones y vibración.
- Rostro: detector *Tiny Face Detector* de face-api (licencia MIT), incluido en la app, funciona sin internet.
- Telemetría: `assets/telemetry.json`, generada con `python tools/export_mobile_data.py`.

## Límites (dilo así en la presentación)
- Prototipo educativo, **no es un dispositivo médico**.
- SpO₂, temperatura, CO₂, radiación, HRV y sueño son **simulados**. El pulso viene del reloj (real) o
  de la cámara (experimental: necesita buena luz y no moverse).
- ASTRO-03 y ASTRO-04 reusan las series del CSV de muestra porque los CSV solo traen dos tripulantes.
- Las alertas solo llegan a equipos en la **misma red Wi-Fi** y con la app abierta (o en segundo plano
  sin que Android la cierre). Para avisos con la app cerrada haría falta un servicio en primer plano o un
  servidor de notificaciones.
- La proximidad es la posición fija de cada tripulante en la app (en un sistema real: balizas BLE/UWB).
- Luma conversa con reglas, sin internet. El APK no incluye ninguna clave de API.
