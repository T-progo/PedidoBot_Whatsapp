# PedidoBot WhatsApp - NegocioListo

Código de la plataforma tal como estaba en el VPS el 21-09-2026, antes de cualquier cambio.
Este commit es la línea base de la auditoría del Hito 1.

## Contenido

- `apps/admin/` - Django (panel, API del bot, pedidos, catálogo). En el servidor corre fuera de Docker, como servicio systemd `negociolisto-django` (gunicorn en 127.0.0.1:8000).
- `apps/admin/requirements.txt` - generado con `pip freeze` del entorno virtual del servidor (no existía en el servidor).
- `infrastructure/stacks/` - docker compose de PostgreSQL, Redis, Evolution API, Typebot, n8n, RustFS y Uptime Kuma.
- `infrastructure/build/` - builds personalizados de Evolution API v2.3.7 (`main.js` parcheado). En producción corre `cards3-full-labels3-iafallback5`.
- `infrastructure/env.example/` - nombres de las variables de cada `.env`, sin valores.
- `server-config/` - sitios de nginx y unidades systemd del servidor.
- `scripts/` - scripts de respaldo del equipo anterior.
- `documentation/` - notas del equipo anterior.

## Excluido a propósito

- Secretos: `infrastructure/secrets/`, `infrastructure/env/`, `configs/`. Los valores reales solo están en el servidor.
- `SECRET_KEY` de Django en `config/settings.py`: reemplazada por un marcador.
- Datos: bases de datos, volúmenes, media, respaldos, exports y logs.
- `.venv/` del servidor.
