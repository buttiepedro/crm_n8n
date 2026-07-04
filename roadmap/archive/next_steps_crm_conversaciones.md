# Next Steps — CRM: panel de conversaciones y notas internas

## Objetivo

Panel tipo inbox para **ver, filtrar y gestionar conversaciones** de todas las cuentas WhatsApp, leer y **enviar mensajes directamente desde la plataforma (sin pasar por n8n)**, y crear **notas internas en cada chat** que quedan asociadas al lead de esa conversación — las mismas notas que el webhook de leads puede crear o editar.

## API

```
GET   /api/v1/conversations
      ?accountId=&status=&assignedUserId=&hasLead=&q=&stageId=&unread=true
      &cursor=&limit=50
      → lista paginada por cursor (last_message_at DESC): contacto, último mensaje,
        unread_count, lead asociado (etapa), agente asignado, ventana 24h restante

GET   /api/v1/conversations/:id                  → detalle + contacto + lead + asignación
GET   /api/v1/conversations/:id/messages?cursor= → mensajes descendentes, paginados,
                                                    adjuntos con URLs firmadas
POST  /api/v1/conversations/:id/messages         → enviar (texto/media/plantilla) como agente
POST  /api/v1/conversations/:id/read             → marcar leída (unread_count = 0)
PATCH /api/v1/conversations/:id                  → { status } | { assignedUserId }
GET   /api/v1/conversations/:id/notes            → notas del chat (las del lead asociado)
POST  /api/v1/conversations/:id/notes            → crear nota interna
PATCH /api/v1/notes/:id                          → editar nota (permiso: propia o notes:edit:any)
DELETE /api/v1/notes/:id                         → borrado lógico
GET   /api/v1/templates?accountId=               → plantillas aprobadas (para fuera de ventana)
```

Búsqueda `q`: full-text en español sobre `messages.body` + nombre/teléfono del contacto (índice GIN ya definido en el doc de base de datos).

## Tiempo real (WebSocket)

WebSockets nativos de FastAPI autenticados con la cookie de sesión en el handshake. Canales (rooms):

- `inbox:{accountId}` → nuevos mensajes/conversaciones para las listas.
- `conversation:{id}` → mensajes nuevos, cambios de estado de entrega, notas nuevas/editadas (incluidas las que llegan por webhook de n8n), typing de otros agentes.

Eventos emitidos: `message.new`, `message.status`, `conversation.updated`, `note.upserted`, `lead.updated`. La SPA usa TanStack Query + invalidación por evento (los eventos traen ids, no payloads completos, para evitar problemas de autorización por socket).

Con más de una instancia de Cloud Run: difundir eventos entre instancias vía pub/sub sobre **Memorystore (Redis)** — documentado en el doc de despliegue; hasta entonces `max-instances=1` para el servicio api o polling de respaldo cada 30 s.

## UI (apps/web)

Layout de 3 columnas, responsive:

1. **Lista de conversaciones**: filtros persistentes en URL (cuenta, estado, asignado a mí/nadie/otros, con/sin lead, etapa del embudo, no leídas), búsqueda, badge de no leídos, indicador de ventana 24h (verde >12h, amarillo <12h, rojo cerrada).
2. **Hilo del chat**: burbujas por dirección con origen visible (WhatsApp / agente X / n8n), estados ✓✓, media con preview (imagen/audio/video/documento vía URL firmada), respuestas citadas, scroll infinito hacia atrás. Compositor: texto, adjuntos, selector de plantillas cuando la ventana está cerrada (deshabilita texto libre y explica por qué).
3. **Panel lateral de contexto**: datos del contacto, lead asociado (etapa editable inline, link a la vista de lead, botón "crear lead" si no existe), y **notas internas**: lista cronológica con autor (usuario o "n8n"), edición inline, visualmente distintas del chat (fondo amarillo suave) — jamás se envían al cliente.

## Reglas de negocio

- **Notas ↔ lead**: al crear una nota en un chat con lead, se asocia `lead_id` (y `conversation_id`). Si el chat no tiene lead, la nota queda solo con `conversation_id`; cuando se cree el lead (manual o por webhook), las notas huérfanas de la conversación se re-asocian automáticamente al lead. Así se cumple "las notas se asocian al lead generado" sin bloquear notas tempranas.
- Enviar mensaje marca la conversación `open` si estaba `closed` y la asigna al emisor si no tenía asignado (configurable en `settings`).
- Visibilidad por permiso: `conversations:read:any` (supervisor/admin) ve todo; `conversations:read:assigned` (agente, según configuración) ve las suyas y las no asignadas.
- Toda acción de gestión (asignar, cerrar, editar nota ajena) → `event_logs`.

## Pasos de desarrollo

- [ ] Endpoints de listado con paginación por cursor + tests de rendimiento con seed de 1M mensajes.
- [ ] Envío como agente reutilizando `OutboundMessageService` (`origin='crm_user'`, `sent_by_user_id`).
- [ ] CRUD de notas con reglas de asociación lead/conversación + re-asociación al crear lead.
- [ ] Endpoint WebSocket (FastAPI) + gestor de canales con autorización por room (verificar permiso antes de join).
- [ ] SPA: layout 3 columnas, lista virtualizada (miles de conversaciones), hilo con scroll infinito, compositor con adjuntos y plantillas.
- [ ] Visor de media: lightbox de imágenes, player de audio (mensajes de voz), descarga de documentos.
- [ ] Filtros/búsqueda con estado en URL (compartible entre agentes).
- [ ] Indicador de ventana 24h calculado en el backend (`last_inbound_at`), mostrado en lista y compositor.
- [ ] Tests E2E (Playwright): recibir mensaje (simulado) → aparece en vivo → responder → nota interna → verla reflejada tras edición por webhook.

## Buenas prácticas

- Paginación **por cursor** (no offset) en mensajes y conversaciones: estable ante inserciones concurrentes.
- URLs firmadas de adjuntos generadas on-demand con TTL 15 min; nunca cachear la URL en el cliente más allá de la sesión de vista.
- Optimistic UI al enviar (estado `queued` local) con reconciliación por WebSocket; si falla, el mensaje muestra reintentar.
- Sanitizar todo texto renderizado (los mensajes son input hostil): render como texto plano, links auto-detectados con `rel="noopener"`.
- Accesibilidad mínima: navegación por teclado en la lista, contraste AA, `aria-live` para mensajes entrantes.

## Criterios de aceptación

- Un agente responde un mensaje entrante en < 3 clics desde la bandeja, sin tocar n8n.
- Dos agentes viendo el mismo chat ven mensajes y notas aparecer en vivo (< 1 s tras el evento).
- Una nota creada desde el webhook de leads aparece en el chat en tiempo real, marcada como origen "n8n", y editarla desde la UI la actualiza (mismo `id`).
- Con la ventana de 24h vencida, el compositor solo ofrece plantillas y el backend rechaza texto libre con `WINDOW_EXPIRED`.
- Los filtros combinados (cuenta + etapa + no asignadas + búsqueda) responden < 300 ms con dataset grande.
