# Next Steps — Observabilidad: logging, errores, métricas y alertas

## Objetivo

Que cualquier evento del sistema sea trazable de punta a punta (Meta → plataforma → n8n → WhatsApp), que los errores se manejen de forma uniforme y visible, y que los problemas se detecten por alertas antes que por usuarios. Dos planos separados: **logs técnicos** (Cloud Logging, para desarrolladores) y **auditoría de negocio** (`event_logs`, visible en el panel).

## Logging técnico estructurado

- **structlog** como logger único, salida JSON a stdout → Cloud Logging la ingiere automáticamente en Cloud Run.
- Formato compatible con Cloud Logging: `severity`, `message`, `time`, y `logging.googleapis.com/trace` para correlación con Cloud Trace.
- **`trace_id` por request** (del header `X-Cloud-Trace-Context` o generado) propagado a: logs, tareas de Cloud Tasks (header custom), `event_logs.trace_id` y `webhook_deliveries`. Un mensaje de WhatsApp se sigue por un único id desde el webhook de Meta hasta la entrega a n8n.
- Middleware de request-logging en FastAPI: método, ruta, status, duración, `user_id`/`api_key_id`, `trace_id`. **Nunca**: cuerpos de mensajes, tokens, contraseñas, payloads completos (solo en nivel `debug`, deshabilitado en prod).
- Niveles: `error` (requiere acción), `warn` (anómalo tolerado: cuenta desconocida, reintento), `info` (hitos de negocio: mensaje persistido, lead creado), `debug` (solo dev).
- Child loggers con contexto (`module`, `account_id`, `conversation_id`) en vez de concatenar en el mensaje.

## Manejo de errores

- **Jerarquía de errores de dominio** (`DomainError` con `code` estable: `WINDOW_EXPIRED`, `ACCOUNT_PAUSED`, `STAGE_NOT_FOUND`, `CONFIG_STEPUP_REQUIRED`…) separada de errores de infraestructura.
- **Exception handlers globales** de FastAPI: mapean `DomainError` → HTTP con el formato único `{ "error": { "code", "message", "details", "traceId" } }`; errores no controlados → `500` genérico (sin stack al cliente) + log `error` con stack completo.
- Regla transversal: **capturar solo lo que se puede manejar**; lo demás sube al handler. Prohibido `except Exception: pass` (regla de lint).
- En workers (Cloud Tasks): distinguir errores **reintentables** (5xx, red, 429 → throw para que la cola reintente) de **permanentes** (4xx de negocio → persistir como `failed`, no reintentar). Cola con dead-letter: tras agotar reintentos → `event_logs` + alerta.
- En el frontend: error boundary global + toast con `traceId` visible para reportar; los formularios muestran `details` por campo de los `422`.
- Crash-safety: excepciones no capturadas del event loop se loguean y terminan el proceso (Cloud Run lo reinicia); shutdown graceful vía `lifespan` de FastAPI (SIGTERM: dejar de aceptar, drenar tareas en curso, cerrar pool de DB).

## Auditoría de negocio (`event_logs`)

Qué se registra (mínimo): login OK/fallido, step-up OK/fallido, mensajes enviados (quién), cambios de asignación/estado de conversaciones, creación/movimiento/borrado de leads (actor humano o webhook), notas creadas/editadas (origen), todas las escrituras del panel de configuración, rotaciones de token, fallos definitivos de entrega a n8n o a Meta. Inmutable (sin UPDATE/DELETE), consultable en el panel con filtros. Es la respuesta a "¿quién movió este lead y cuándo?".

## Métricas y alertas

Métricas custom (Cloud Monitoring, vía log-based metrics o OpenTelemetry):

| Métrica | Alerta sugerida |
|---|---|
| `webhook_meta_received` / `webhook_meta_signature_failed` | Firmas fallidas > 10/min (ataque o secreto mal rotado) |
| `message_send_failed_total` (por cuenta y código de error) | > 5% de fallos en 10 min |
| `n8n_delivery_failed_total` (por cuenta) | Fallos definitivos > 0 en 15 min |
| `media_download_failed_total` | > 3 en 10 min (las URLs de Meta expiran) |
| `account_token_invalid` | Inmediata — la cuenta quedó inoperativa |
| Latencia p95 del webhook de Meta | > 2 s (riesgo de que Meta desactive el webhook) |
| Profundidad/edad de las colas de Cloud Tasks | Backlog > 100 o tarea más vieja > 10 min |
| Errores 5xx de la api | > 1% en 5 min |
| Conexiones del pool de PostgreSQL | > 80% del máximo |

Canales: email + webhook (puede ser un workflow de n8n que notifique a WhatsApp/Slack — dogfooding). Uptime checks de Cloud Monitoring sobre `/api/v1/health` y `/health/ready`.

## Dashboards

1. **Operación de mensajería**: mensajes in/out por cuenta, fallos de envío, latencia webhook→persistencia, backlog de colas.
2. **Puente n8n**: entregas OK/fallidas, reintentos, latencia de round-trip (mensaje entrante → respuesta de n8n).
3. **Plataforma**: 5xx, latencias p50/p95/p99 por ruta, CPU/memoria/instancias de Cloud Run, conexiones DB.

## Pasos de desarrollo

- [ ] Configurar structlog + formato Cloud Logging + middleware de request-logging con redacción de campos sensibles (processor de redacción).
- [ ] Middleware de `trace_id` + propagación a Cloud Tasks y a `event_logs`/`webhook_deliveries`.
- [ ] Jerarquía `DomainError` + exception handlers globales + catálogo de códigos en `app/schemas/errors.py`.
- [ ] Clasificación reintentable/permanente en los dos workers (WhatsApp, n8n) + dead-letter con alerta.
- [ ] `AuditService.log()` y llamadas en todos los puntos listados (test que verifica cobertura de acciones críticas).
- [ ] Log-based metrics + políticas de alerta (Terraform) + uptime checks.
- [ ] Dashboards de Monitoring (JSON versionado en `/infra`).
- [ ] Shutdown graceful + handlers de crash + prueba de kill durante carga.
- [ ] Documentar runbook mínimo por alerta: qué mirar, cómo re-entregar, cómo pausar una cuenta.

## Buenas prácticas

- Loguear **hechos con contexto**, no prosa: `{"msg":"message_persisted","conversation_id":…,"wamid":…}` es filtrable; "se guardó el mensaje" no.
- El `traceId` viaja hasta el usuario final (en errores de UI) — soporte lo pega y desarrollo encuentra el log exacto.
- Alertas accionables o no existen: cada alerta tiene runbook; si una alerta suena y se ignora dos veces, se recalibra o se elimina.
- Presupuesto de logs: muestreo de `info` de alto volumen si el coste de Cloud Logging crece; `error`/`warn` nunca se muestrean.
- La auditoría de negocio no es un log técnico: no se rota, no se muestrea, vive en la DB con el resto de los datos.

## Criterios de aceptación

- Dado un mensaje cualquiera, con su `trace_id` se reconstruye en < 2 min todo su recorrido (webhook Meta → persistencia → entrega n8n → respuesta → envío → estados).
- Apagar n8n dispara la alerta de entregas fallidas en ≤ 15 min con el runbook enlazado.
- Un error 500 en producción muestra al usuario un `traceId` que localiza el stack completo en Cloud Logging.
- El panel responde "¿quién movió este lead a Ganado?" sin consultar a un desarrollador.
