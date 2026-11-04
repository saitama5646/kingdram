# Kingdram

Bot de estrategia medieval para Telegram.

## Despliegue en Render

El repositorio incluye `render.yaml` para crear el servicio mediante un Blueprint.

1. En Render, crea un Blueprint nuevo y conecta este repositorio.
2. Selecciona la rama `main`.
3. Render detectará el servicio web definido en `render.yaml`.
4. Cuando solicite variables, configura:
   - `BOT_TOKEN`: token del bot de Telegram.
   - `DATABASE_URL`: URL de conexión de Neon PostgreSQL.
5. Confirma la creación con el plan **Free**.

Configuración incluida:

- Build: `pip install -r requirements.txt`
- Start: `python -m bot.main`
- Health check de Render: `/health`
- Puerto HTTP: el valor de entorno `PORT` (Render lo proporciona).

No subas el archivo `.env` ni escribas los secretos directamente en el repositorio.

## Actualizaciones automáticas

Conecta Render a la rama `main` y deja activado Auto-Deploy. Cada push a esa rama provocará una nueva compilación y despliegue.

## Cron externo

Después del primer despliegue, copia la URL pública de Render y configura en cron-job.org una petición **GET** a:

`https://TU-SERVICIO.onrender.com/cron`

Programa la ejecución cada **10 minutos**. Una respuesta HTTP 200 con JSON y `"status": "ok"` indica que el proceso está inicializado y recibió el ping.

También puedes abrir `/health` en el navegador para comprobar el estado del servicio.

## Importante sobre el plan gratuito

Render suspende los servicios web gratuitos tras 15 minutos sin tráfico entrante. El ping periódico puede mantener el servicio activo, pero si se mantiene encendido todo el mes consumirá aproximadamente 720 de las 750 horas gratuitas mensuales disponibles para el espacio de trabajo. Render también puede reiniciar servicios gratuitos; los datos persistentes del juego deben permanecer en Neon, no en el disco local del servicio.
