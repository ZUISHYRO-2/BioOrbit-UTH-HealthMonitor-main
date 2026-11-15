# BioOrbit · Servidor de tripulación

Guarda las cuentas de los astronautas, reparte el chat interno y las alertas entre teléfonos,
y muestra el **dashboard de monitoreo** en la PC del control de misión.
Solo usa Python (3.9 o más nuevo): no hay que instalar nada.

## 1. Arrancar el servidor (en la PC del dashboard)

Doble clic en `iniciar_servidor.bat` (o en una terminal, desde la carpeta del proyecto):

```
py crew_server/server.py
```

La ventana muestra:
- **Dashboard**: abre `http://localhost:8765` en el navegador de la PC.
- **Cuenta del dashboard**: usuario `control` y una contraseña que se genera la primera vez
  (queda guardada en `crew_server/data/control_password.txt`).
- La dirección para los teléfonos en el Wi-Fi, por ejemplo `http://192.168.1.10:8765`.

**Windows Firewall:** la primera vez Windows pregunta si deja que Python use la red.
Marca **Redes privadas** y acepta. Si no, los teléfonos no podrán conectarse.
El Wi-Fi de la PC debe estar como red **privada**, no pública.

## 2. Teléfonos en el mismo Wi-Fi

Abre la app BioOrbit. El servidor se encuentra solo («✓ Servidor encontrado en el Wi-Fi»).
Cada astronauta toca **Crear cuenta**, escribe su nombre, elige su puesto (ASTRO-01 a 04),
usuario y contraseña. Después solo **Entrar**.

Si no aparece solo (algunas redes de escuela bloquean los anuncios), escribe a mano la dirección
que muestra la ventana del servidor, por ejemplo `192.168.1.10:8765`.

## 3. Teléfonos con datos móviles

La PC necesita una dirección pública. Gratis y sin cuenta, con Cloudflare:

1. Instala cloudflared una vez: `winget install --id Cloudflare.cloudflared`
2. Con el servidor abierto, doble clic en `iniciar_tunel.bat` (o `py crew_server/tunel.py`).
3. Aparece una dirección `https://algo.trycloudflare.com`.

Los teléfonos que ya iniciaron sesión por Wi-Fi **la aprenden solos** y la usan cuando salen
del Wi-Fi. También se puede escribir en la app: **Equipo → Cambiar servidor**.
La dirección cambia cada vez que abres el túnel.

## Qué hace

| Teléfono (pestaña **Equipo**) | Dashboard (PC) |
|---|---|
| Lista de la tripulación: en línea, pulso, si está en cámara, alertas | Tarjeta por astronauta con pulso, SpO₂, temperatura y gráfica de 5 min |
| Chat general, privado con cada compañero y con Control | Chat con todos o privado; ve todos los mensajes |
| Alertas de los demás con «Voy en camino» / «No puedo ir» | Alertas con sonido, quién va en camino, «Marcar resuelta» |
| Por voz: «dile a Beto que ya voy», «manda un mensaje a la tripulación: …», «¿tengo mensajes?» | Quitar cuentas |

- Las alertas (sin signos vitales, nadie en cámara, SOS por voz, apoyo humano) también se siguen
  mandando por el Wi-Fi como antes, así que funcionan aunque el servidor esté apagado.
- Cuando la persona toca «Estoy bien», su alerta se cierra sola en todos lados.
- Contraseñas guardadas con PBKDF2 (nunca en texto plano). En el Wi-Fi la conexión es http;
  por datos móviles va cifrada (https del túnel).

## Opciones

```
py crew_server/server.py --port 9000            # otro puerto
py crew_server/server.py --reset-admin          # nueva contraseña para «control»
py crew_server/server.py --public https://...   # si ya tienes una dirección pública fija
```

Para empezar de cero (borrar cuentas y chat): cierra el servidor y borra `crew_server/data/`.
