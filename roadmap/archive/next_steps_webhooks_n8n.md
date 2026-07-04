# Next Steps — Webhooks con n8n

## Objetivo

Definir el contrato completo entre la plataforma y n8n:

1. **Webhook saliente** (plataforma → n8n): cada mensaje entrante de WhatsApp se reenvía al workflow de n8n configurado por cuenta.
2. **Webhook entrante de mensajes** (n8n → plataforma): n8n devuelve respuestas que la plataforma envía a WhatsApp. `POST /api/v1/hooks/n8n/messages`.
3. **Webhook entrante de leads** (n8n → plataforma): n8n crea/actualiza leads desde las conversaciones, incluyendo **crear y editar notas internas**. `POST /api/v1/hooks/n8n/leads`.

## Autenticación de los webhooks entrantes

- Header `Authorization: Bearer <api_key>` — API keys creadas en el panel de configuración, con scopes (`hooks:messages`, `hooks:leads`), almacenadas hasheadas (ver doc de seguridad).
- Header opcional `X-Signature-256: sha256=<hmac>` (HMAC del body con el secreto asociado a la key) para entornos que lo requieran — recomendado en producción.
- Header `Idempotency-Key` (UUID generado por n8n): la plataforma guarda la respuesta 24 h y ante repetición devuelve la respuesta original sin re-ejecutar.
- Rate limit por API key (p.ej. 50 req/s) con respuesta `429`.

## 1. Webhook saliente: plataforma → n8n

Configurable **por cuenta WhatsApp** en el panel: `n8n_inbound_webhook_url` + secreto HMAC propio.

```jsonc
// POST {n8n_inbound_webhook_url}
// Headers: X-Signature-256: sha256=<hmac-sha256(body, secreto_de_la_cuenta)>
//          X-Event-Id: <uuid>   X-Event-Type: message.received
{
  "event": "message.received",
  "eventId": "0197a1b2-…",
  "occurredAt": "2026-07-03T14:21:09Z",
  "account": { "id": "…", "name": "Ventas AR", "phoneNumberId": "123456", "displayPhoneNumber": "+54911…" },
  "conversation": { "id": "…", "status": "open", "isNew": false, "assignedUserId": null },
  "contact": { "id": "…", "waId": "54911…", "profileName": "Juan Pérez" },
  "lead": { "id": "…", "stageId": "…", "externalKey": "crm-123" },   // null si no hay lead aún
  "message": {
    "id": "…", "wamid": "wamid.HBg…", "type": "text",
    "body": "Hola, quiero info", "replyToWamid": null,
    "attachments": [ { "id": "…", "mimeType": "image/jpeg", "downloadUrl": "https://storage.googleapis.com/…(firmada 15min)" } ],
    "waTimestamp": "2026-07-03T14:21:07Z"
  }
}
```

Entrega vía Cloud Tasks (cola `outbound-n8n`):
- Timeout 15 s. Éxito = HTTP 2xx.
- Reintentos con backoff exponencial: 1 min, 5 min, 15 min, 1 h, 6 h (máx 5). Cada intento queda en `webhook_deliveries`.
- Fallo definitivo → `event_logs` + contador de fallos por cuenta visible en el panel (con botón de re-entrega manual).
- La caída de n8n **nunca** bloquea la persistencia: el mensaje ya está en DB antes de encolar.

## 2. Webhook entrante de mensajes: `POST /api/v1/hooks/n8n/messages`

n8n responde a una conversación. Scope requerido: `hooks:messages`.

```jsonc
// Request
{
  "conversationId": "0197a1b2-…",        // opción A: id interno (viene en el webhook saliente)
  // opción B (alternativa): "accountId" + "to": "54911…" — abre conversación si no existe
  "message": {
    "type": "text",                       // text | image | document | audio | video | template
    "body": "¡Hola Juan! Te paso la info…",
    "mediaUrl": null,                     // URL descargable si type es media
    "fileName": null,
    "template": null                      // { "name": "...", "language": "es_AR", "components": [...] }
  }
}

// Response 202
{ "messageId": "0197a1c3-…", "status": "queued" }
```

Comportamiento:
- Validación estricta (tipos, tamaños, URL de media accesible). Errores → `422` con detalle por campo.
- El mensaje entra al **mismo** `OutboundMessageService` que usa el CRM: misma cola, misma ventana de 24h (`409 WINDOW_EXPIRED` si aplica y no es plantilla), mismos estados.
- `origin='n8n'` en `messages` para poder filtrar/auditar.
- El resultado final del envío se puede consultar con `GET /api/v1/messages/{id}` (n8n puede hacer polling o suscribirse a un workflow de errores).

## 3. Webhook entrante de leads: `POST /api/v1/hooks/n8n/leads`

Crea o actualiza un lead desde una conversación, **y crea o edita sus notas internas** (requisito clave). Scope: `hooks:leads`.

```jsonc
// Request
{
  "externalKey": "wf-ventas-54911-2026-07",  // idempotencia: mismo key → mismo lead (upsert)
  "conversationId": "0197a1b2-…",            // asocia lead ↔ conversación ↔ contacto
  "title": "Juan Pérez — Plan Premium",
  "value": 150000.00,
  "currency": "ARS",
  "pipelineId": null,                        // null → pipeline por defecto
  "stageId": null,                           // null → primera etapa; o id/nombre de etapa
  "stageName": "Calificado",                 // alternativa amigable a stageId
  "ownerUserEmail": "vendedor@laceleste.com.ar",  // opcional: asignar dueño
  "attributes": { "origen_campania": "meta-ads-julio" },
  "notes": [
    {
      "externalKey": "resumen-ia",           // upsert: si existe (lead, externalKey) se EDITA
      "body": "Resumen IA: cliente pregunta por plan premium, presupuesto ~150k."
    },
    {
      "externalKey": "scoring",
      "body": "Score automático: 82/100 (alta intención)."
    }
  ]
}

// Response 200 (o 201 si el lead es nuevo)
{
  "leadId": "0197a1d4-…",
  "created": false,
  "stage": { "id": "…", "name": "Calificado" },
  "notes": [
    { "id": "…", "externalKey": "resumen-ia", "created": false },
    { "id": "…", "externalKey": "scoring", "created": true }
  ]
}
```

Semántica (todo en **una transacción**):
1. **Lead**: upsert por `externalKey`; si no viene, buscar lead activo de la `conversationId`; si tampoco, crear. Solo se actualizan los campos presentes en el payload (merge parcial, no reemplazo).
2. **Etapa**: si `stageId`/`stageName` cambia la etapa, registrar en `lead_stage_events` con `moved_by='webhook:<api_key_id>'`.
3. **Notas**: por cada nota, upsert por `(lead_id, external_key)` — crea si no existe, **actualiza `body` si existe** (con `author_source='n8n_webhook'`). Notas sin `externalKey` siempre crean una nueva.
4. Auditoría en `event_logs` (`lead.upserted_via_webhook`) y emisión por WebSocket para refrescar el panel en vivo.

Errores: `404` si `conversationId` no existe; `422` validación; `409` si `stageName` es ambiguo entre pipelines.

## Pasos de desarrollo

- [ ] Definir los tres contratos como schemas Pydantic en `app/schemas/` (fuente única: validan en runtime y generan la documentación OpenAPI para quien arma los workflows de n8n).
- [ ] Guard de API key: hash-lookup, verificación de scope, `last_used_at`, rate limit.
- [ ] Middleware de `Idempotency-Key` con almacenamiento de respuestas (tabla o Redis) y TTL 24 h.
- [ ] Dispatcher del webhook saliente: constructor de payload, firma HMAC, integración Cloud Tasks, registro en `webhook_deliveries`.
- [ ] Endpoint `hooks/n8n/messages` delegando en `OutboundMessageService`.
- [ ] Endpoint `hooks/n8n/leads` con la transacción de upsert lead + etapa + notas.
- [ ] Botón "enviar evento de prueba" en el panel (dispara un `message.received` sintético a la URL configurada).
- [ ] Colección de ejemplos: workflows n8n de referencia (recibir → procesar → responder → crear lead) exportados en `/docs/n8n-examples/`.
- [ ] Tests E2E: n8n simulado con un servidor HTTP de test; cubrir reintentos, idempotencia, firma inválida, scopes insuficientes.

## Buenas prácticas

- **Contratos versionados**: el evento saliente lleva `"event"` con nombre estable; cambios incompatibles → `message.received.v2`, nunca mutar el v1.
- Payload saliente **autosuficiente** (cuenta, contacto, conversación, lead, URLs de media firmadas) para que los workflows de n8n no necesiten llamadas extra de lookup.
- Las URLs de media firmadas expiran en 15 min: si el workflow de n8n es lento, debe descargar al inicio (documentarlo en los ejemplos).
- Responder `202` en los hooks entrantes cuando el trabajo es asíncrono; el estado real siempre es consultable.
- Nunca confiar en datos de n8n para permisos: la API key define lo que puede hacer, no el payload.

## Criterios de aceptación

- Mensaje entrante → workflow n8n lo recibe firmado y con media descargable; respuesta de n8n llega al cliente de WhatsApp; el círculo completo < 5 s en condiciones normales.
- Repetir el mismo `POST /hooks/n8n/leads` cinco veces deja exactamente un lead y sus notas con el contenido de la última versión.
- Una nota creada por webhook y luego editada por webhook conserva el mismo `id` y muestra su historial en `updated_at`/auditoría.
- Con n8n caído 1 hora, `webhook_deliveries` muestra los reintentos y al volver n8n recibe todos los eventos pendientes.
