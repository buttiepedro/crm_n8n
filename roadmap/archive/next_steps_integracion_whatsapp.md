# Next Steps — Integración WhatsApp Business Cloud API

## Objetivo

Recibir todos los eventos de la Cloud API de Meta (mensajes, estados, errores) para todas las cuentas configuradas, persistirlos íntegramente, descargar la media a Cloud Storage y poder enviar mensajes (texto, media, plantillas) desde el CRM, desde n8n o desde cualquier consumidor interno — con reintentos, idempotencia y trazabilidad.

## Prerrequisitos externos (Meta)

- App de Meta tipo Business con producto **WhatsApp** habilitado.
- **WABA** (WhatsApp Business Account) con al menos un número verificado.
- **System User token permanente** (no el token temporal de 24h del panel de pruebas), con permisos `whatsapp_business_messaging` y `whatsapp_business_management`. Uno por cuenta gestionada.
- Webhook de la app apuntando a `https://<dominio>/api/v1/whatsapp/webhook`, suscrito a los campos `messages` (mínimo). La URL es **una sola para todas las cuentas**: el ruteo interno se hace por `phone_number_id` del payload.

## Recepción de webhooks de Meta

### Endpoints

```
GET  /api/v1/whatsapp/webhook   → verificación (hub.challenge) con WHATSAPP_VERIFY_TOKEN
POST /api/v1/whatsapp/webhook   → eventos
```

### Reglas del handler POST (orden estricto)

1. **Firma**: validar `X-Hub-Signature-256` (HMAC-SHA256 con `WHATSAPP_APP_SECRET`) sobre el **body crudo**. En FastAPI, calcular el HMAC sobre `await request.body()` (bytes crudos) antes de parsear el JSON; si el body se re-serializa, la firma falla. Firma inválida → `401` + log de seguridad.
2. **Responder `200` de inmediato** tras persistir el evento crudo en una tabla/cola de ingesta. Meta reintenta con backoff y desactiva webhooks que fallan sostenidamente; nunca hacer trabajo pesado en línea.
3. **Procesar async** (en el mismo proceso vía job inmediato, o Cloud Tasks si el volumen crece):
   - Rutear por `entry[].changes[].value.metadata.phone_number_id` → `whatsapp_accounts`. Cuenta desconocida → log warn + descartar (no 500).
   - **Idempotencia**: `INSERT … ON CONFLICT (wamid) DO NOTHING`. Meta reenvía eventos.
   - Upsert `contacts` (por `wa_id`), upsert `conversations` (por cuenta+contacto), insert `messages` con `raw_payload` completo.
   - Actualizar `last_message_at`, `last_inbound_at`, `unread_count`.
   - Eventos `statuses` (sent/delivered/read/failed) → `message_status_events` + actualizar `messages.status` (solo hacia adelante: nunca pisar `read` con `delivered`).
   - Encolar reenvío a n8n (ver doc de webhooks) y emitir por WebSocket al panel.

### Media entrante

Los payloads traen `media_id`, no el binario. La URL de descarga de Meta **expira en ~5 minutos**, así que la descarga es inmediata y con reintentos:

1. Crear fila en `attachments` con `download_status='pending'`.
2. Job: `GET https://graph.facebook.com/v21.0/{media_id}` (con el token de la cuenta) → devuelve URL temporal → descargar con el mismo token → subir stream a GCS (`accounts/{account_id}/{yyyy}/{mm}/{message_id}/{filename}`) → guardar `gcs_path`, `sha256`, `size_bytes`, `download_status='done'`.
3. Fallo definitivo → `download_status='failed'` + `event_logs`; reintentable manualmente desde el panel.
4. El CRM sirve adjuntos solo mediante **URLs firmadas de GCS de corta duración** (15 min), nunca bucket público.

## Envío de mensajes

### Servicio único de salida

Todos los orígenes (agente del CRM, hook de n8n, futuro API pública) convergen en `OutboundMessageService.send()`:

1. Validar la **ventana de 24h**: si `now() - conversations.last_inbound_at > 24h`, solo se aceptan mensajes `type='template'`. Rechazo con código `WINDOW_EXPIRED` para que la UI/n8n lo manejen.
2. Persistir el mensaje con `status='queued'`, `origin` (`crm_user` | `n8n`) y `sent_by_user_id` si aplica.
3. Encolar en Cloud Tasks (`outbound-whatsapp`) el job de envío con `message_id`.
4. Worker (`POST /internal/tasks/send-message`, autenticado por OIDC de Cloud Tasks):
   - Llamar `POST /v21.0/{phone_number_id}/messages` con el token descifrado de la cuenta.
   - Éxito → guardar `wamid`, `status='sent'` (los estados posteriores llegan por webhook).
   - Error 4xx de negocio (ventana, número inválido, plantilla no aprobada) → `status='failed'` + `error_detail`, **sin reintento**.
   - Error 5xx / red / 429 → lanzar excepción para que Cloud Tasks reintente con backoff exponencial (max 5 intentos), luego `failed`.
5. Media saliente: subir primero a Meta (`POST /{phone_number_id}/media`) o usar link público firmado; guardar `media_id` resultante.

### Tipos soportados en v1

Texto, imagen, documento, audio, video, plantillas (`template` con variables), respuesta a mensaje (`context.message_id`). Interactivos (botones/listas) quedan para v2 pero el enum de DB ya los contempla.

## Multi-cuenta y credenciales

- El módulo `accounts` expone `getDecryptedToken(accountId)` que descifra `access_token_ciphertext` con `CREDENTIALS_ENCRYPTION_KEY` (AES-256-GCM). El token descifrado vive solo en memoria por request; **jamás** se loguea ni se devuelve por API.
- Cache en memoria del token descifrado con TTL corto (60 s) para no descifrar por mensaje.
- Health check por cuenta: botón "probar conexión" en el panel que llama `GET /v21.0/{phone_number_id}` y actualiza `status` de la cuenta (`error` si el token venció).
- Versionado del cliente Graph API centralizado (`GRAPH_API_VERSION = 'v21.0'`) en un solo lugar.

## Pasos de desarrollo

- [ ] Cliente HTTP tipado de Graph API (`WhatsAppApiClient`) con inyección del token por cuenta, timeouts (10 s) y mapeo de errores de Meta a errores de dominio.
- [ ] Endpoint GET de verificación del webhook con `WHATSAPP_VERIFY_TOKEN`.
- [ ] Endpoint POST con validación de firma sobre raw body + tests con firmas válidas/inválidas.
- [ ] Parser de payloads de Meta → DTOs internos (cubrir con fixtures reales todos los `message_type`).
- [ ] Pipeline de persistencia transaccional (contacto + conversación + mensaje) idempotente por `wamid`.
- [ ] Descarga de media a GCS con reintentos y verificación de tamaño/mime (límite configurable, p.ej. 100 MB).
- [ ] `OutboundMessageService` + worker de Cloud Tasks + manejo de ventana de 24h.
- [ ] Soporte de plantillas: sincronizar la lista de plantillas aprobadas de la WABA (`GET /{waba_id}/message_templates`) para que el CRM/n8n las usen por nombre.
- [ ] Suite de fixtures: guardar payloads reales anonimizados en `apps/api/test/fixtures/meta/` y testear el parser contra todos.
- [ ] Entorno de pruebas: túnel (cloudflared/ngrok) documentado para desarrollo local contra el sandbox de Meta.

## Buenas prácticas

- Tratar el payload de Meta como **no confiable** hasta validar firma; y como **evolutivo**: campos desconocidos se conservan en `raw_payload`, el parser nunca explota por campos extra (`unknown` como fallback de tipo).
- Respetar rate limits de Meta (por número: ~80 msg/s en tiers altos, mucho menos al inicio): la cola con `maxDispatchesPerSecond` configurado por cuenta protege de bans.
- No reenviar a n8n los eventos de estado por defecto (ruido); hacerlo opt-in por cuenta (`settings.forwardStatuses`).
- Logs de cada interacción con Meta con `trace_id`, `account_id`, `wamid` — sin tokens ni cuerpos de mensaje en logs técnicos (privacidad).
- Monitorear la expiración/invalidez de tokens: un `401` de Meta marca la cuenta en `error` y dispara alerta (ver observabilidad).

## Criterios de aceptación

- Los 10+ tipos de mensaje de Meta se persisten sin pérdida (verificado con fixtures) y los no reconocidos quedan como `unknown` con su `raw_payload`.
- Un webhook duplicado de Meta no genera filas duplicadas.
- Media entrante disponible en GCS aunque el primer intento de descarga falle (reintento antes de que expire la URL).
- Un mensaje enviado desde el CRM pasa por `queued → sent → delivered → read` reflejado en tiempo real en la UI.
- Con el token de una cuenta revocado, la cuenta queda en `error`, el resto de cuentas sigue operando y hay alerta visible en el panel.
