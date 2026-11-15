# Centro de control: cómo se conectan los dispositivos

La pestaña **Centro de control** de `streamlit run src/app.py` muestra a toda la tripulación (ASTRO-01…04)
y todos los dispositivos que reportan, en una sola pantalla.

## De dónde sale cada dato

| Dispositivo | Cómo llega | ¿Reemplaza los signos simulados? |
|---|---|---|
| Sensores simulados (CSV) | `data/demo_stress_arc.csv` | Es la base de todo |
| Reloj Bluetooth (en la laptop del centro) | archivo puente, ya existente | Sí: FC (y HRV/SpO₂ si el reloj los manda) |
| HUD de cámara en la misma laptop | archivo puente, ya existente | No: se muestra, pero el pulso por cámara es experimental |
| HUD de cámara en **otra** laptop | `BIOORBIT_FLEET_URL` → `fleet_server.py` | No |
| Teléfono u otro aparato | `POST /report` → `fleet_server.py` | Sí: FC (y HRV/SpO₂ si los manda) |

Un dispositivo que reemplaza signos y **deja de mandar pulso** (entre 10 s y 2 min) cuenta como pérdida de signos
vitales: sale la cuenta regresiva «estoy bien» y, si no se cancela, el aviso a los tripulantes cercanos.

## Puesta en marcha (PowerShell, en la laptop del centro de control)

```powershell
.\venv\Scripts\Activate.ps1
python src/fleet_server.py          # terminal 1: receptor de dispositivos (puerto 8766)
streamlit run src/app.py            # terminal 2: consola
```

Token opcional (recomendado si hay más gente en la red): define `$env:BIOORBIT_FLEET_TOKEN="<algo-largo-y-secreto>"`
**antes** de arrancar el servidor, y el mismo valor en quien reporta. No lo escribas en el código ni lo subas a GitHub.

## Otra laptop con el HUD de cámara

```powershell
$env:BIOORBIT_FLEET_URL="http://<ip-del-centro-de-control>:8766"
python src/vision_monitor.py --crew=ASTRO-03
```

No pongas `BIOORBIT_FLEET_URL` en la laptop del centro de control: ahí el HUD ya se lee por archivo.

## Reporte de un dispositivo (JSON)

`POST http://<ip>:8766/report`, cuerpo máximo 4 KB, encabezado `X-BioOrbit-Token` solo si usas token.

| Campo | Obligatorio | Notas |
|---|---|---|
| `device_id` | sí | letras, números, `.` `_` `-`; máx. 48 |
| `crew` | sí | uno de `ASTRO-01`…`ASTRO-04` |
| `kind` | no | `watch`, `phone`, `camera` u `other` (por defecto `other`) |
| `name` | no | nombre que se muestra |
| `heart_rate_bpm`, `hrv_rmssd_ms`, `spo2_pct`, `body_temp_c`, `battery_pct` | no | números |
| `hrv_real` | no | `true` solo si la HRV sale de intervalos RR medidos |

Prueba rápida sin teléfono:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8766/report -ContentType "application/json" `
  -Body '{"device_id":"movil-prueba","crew":"ASTRO-03","kind":"phone","name":"Telefono de prueba","heart_rate_bpm":72,"battery_pct":80}'
```

Si repites el comando cada 2–5 s, la tarjeta de ASTRO-03 pasa a usar ese pulso. Si dejas de mandarlo, a los ~10 s
aparece «retrasado» y arranca la cuenta regresiva de pérdida de signos.

## Teléfonos: servidor de tripulación (`crew_server/`)

Los teléfonos hablan con `crew_server/server.py` (cuentas, chat, alertas; solo usa la librería estándar de Python).
El centro de control entra a él solo, como la cuenta `control`, cada 2 s, y muestra cada teléfono que ya sincronizó.

```powershell
.\venv\Scripts\Activate.ps1
python crew_server/server.py        # terminal 1: puerto 8765 (la primera vez crea la contraseña de «control»)
streamlit run src/app.py            # terminal 2
```

- **¿Qué puesto tiene cada teléfono?** El que el astronauta eligió al crear su cuenta (ASTRO-01 a 04). Una cuenta con
  otro puesto aparece en la tabla de dispositivos, pero sin tarjeta.
- **Contraseña de `control`:** se lee de `crew_server/data/control_password.txt`. Si el servidor está en otra PC, define
  `$env:BIOORBIT_CONTROL_PASSWORD` y `$env:BIOORBIT_CREW_URL="http://<ip>:8765"` antes de abrir la consola.
- **Qué cuenta como pulso real:** solo si el teléfono dice que tiene un reloj conectado. El pulso por cámara se muestra,
  pero no reemplaza los signos ni dispara alertas.
- **Alertas de los teléfonos** (sin signos vitales, SOS, apoyo humano) salen arriba en el centro de control, con quién va en
  camino, y se pueden marcar como resueltas.
- Si no aparecen teléfonos, el renglón verde/naranja arriba de las tarjetas dice el motivo (servidor apagado,
  contraseña, etc.).

## Puertos

| Puerto | Qué es |
|---|---|
| 8501 | consola Streamlit |
| 8765 | `crew_server` (teléfonos, dashboard web de tu compañero) |
| 8766 | `fleet_server.py` (solo para el HUD de otras laptops) |
