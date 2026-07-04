# CRM WhatsApp Business ↔ n8n

Plataforma self-hosted que actúa como **intermediario entre la WhatsApp Business Cloud API (Meta) y n8n**, y funciona a la vez como **CRM completo**: almacena todos los mensajes, adjuntos y conversaciones en PostgreSQL, permite leer y responder chats sin pasar por n8n, gestiona leads en un embudo configurable con notas internas, y se administra desde un panel técnico protegido por contraseña.

## Qué hace

1. **Recibe todos los mensajes de WhatsApp** (texto, imágenes, audios, documentos, ubicaciones, reacciones…) vía webhook de Meta, los persiste íntegros (payload crudo incluido) y descarga los adjuntos.
2. **Reenvía cada mensaje entrante a n8n** (webhook saliente firmado con HMAC, configurable por cuenta, con reintentos y trazabilidad de cada entrega).
3. **Expone dos webhooks para n8n**:
   - `POST /api/v1/hooks/n8n/messages` — n8n responde y la plataforma envía a WhatsApp.
   - `POST /api/v1/hooks/n8n/leads` — n8n crea/actualiza leads y **crea o edita notas internas** (upsert por `externalKey`).
4. **CRM en el navegador**: bandeja de conversaciones con filtros, envío directo (respetando la ventana de 24 h de WhatsApp), notas internas por chat asociadas al lead, kanban de leads con etapas 100 % editables.
5. **Login con roles** (agente / supervisor / admin) y permisos finos.
6. **Panel técnico** (protegido por la contraseña del `.env`): ahí se configura *todo lo demás* — credenciales de Meta, cuentas de WhatsApp, webhooks a n8n, API keys, usuarios, y se ven la auditoría, las entregas a n8n (re-entregables) y los mensajes fallidos (re-encolables).

## Arquitectura

```
                       ┌──────────────────────── docker compose ────────────────────────┐
 Meta (WhatsApp        │                                                                 │
 Cloud API)            │   :8001  ┌────────────────┐        ┌──────────────┐             │
 ── mensajes ────────────────────▶│    api          │───────▶│ db           │             │
 ◀── envíos ──────────────────────│  FastAPI        │        │ PostgreSQL 16│             │
                       │          │  (Python 3.12)  │        │ (solo red    │             │
 n8n (EXTERNO)         │          │                 │        │  interna)    │             │
 ◀── webhook saliente ────────────│  · webhook Meta │        └──────────────┘             │
 ── hooks msgs/leads ────────────▶│  · hooks n8n    │                                     │
                       │          │  · API CRM      │        ┌──────────────┐             │
                       │          │  · panel /config│        │ volumen      │             │
                       │          └───────▲─────────┘───────▶│ adjuntos     │             │
                       │                  │ proxy /api       └──────────────┘             │
 Navegador             │   :8000  ┌───────┴────────┐                                      │
 (agentes/admin) ────────────────▶│    web          │   migrate (corre 1 vez al up:       │
                       │          │ React + nginx   │   alembic upgrade + seed)           │
                       │          └────────────────┘                                      │
                       └─────────────────────────────────────────────────────────────────┘
```

- **Únicos puertos expuestos**: `8000` (frontend) y `8001` (API: webhook de Meta + hooks de n8n). PostgreSQL no se expone.
- **Stack**: FastAPI + SQLAlchemy 2.0 async + Alembic · PostgreSQL 16 · React + Vite servido por nginx · cola interna con reintentos (Cloud Tasks en la fase GCP).
- **Seguridad**: tokens y secretos cifrados con AES-256-GCM en la DB (clave maestra en el `.env`); firma HMAC verificada en cada webhook de Meta; API keys hasheadas con scopes; sesiones server-side con cookie httpOnly; contraseñas argon2id; auditoría inmutable de cada acción.

### Cómo funciona (flujos principales)

- **Mensaje entrante**: Meta → `POST /api/v1/whatsapp/webhook` → se valida la firma → se responde 200 al instante → async: se persiste (idempotente por `wamid`), se descargan adjuntos, y se encola el reenvío firmado al webhook de n8n de esa cuenta (reintentos con backoff; cada intento queda en `webhook_deliveries`). Si n8n está caído, nada se pierde.
- **Respuesta desde n8n**: `POST /api/v1/hooks/n8n/messages` (API key) → valida ventana de 24 h → encola el envío a la Graph API → los estados (`sent/delivered/read`) llegan por webhook y actualizan el mensaje.
- **Lead desde n8n**: `POST /api/v1/hooks/n8n/leads` (API key) → upsert del lead por `externalKey` o conversación → mueve de etapa si corresponde (con historial) → upsert de notas internas por `externalKey` (crea o **edita**). Todo en una transacción.
- **Envío desde el CRM**: mismo pipeline que n8n (misma cola, misma ventana de 24 h), con el agente como autor.

## Configuración: qué va dónde

| Dónde | Qué |
|---|---|
| **`.env`** (raíz, único archivo) | Contraseña del panel técnico, clave de cifrado, credenciales de Postgres, puertos, drivers. **Nada más.** |
| **Panel técnico** (⚙️ en el front) | Verify token y App Secret de Meta, versión de Graph API, cuentas de WhatsApp con sus tokens, webhooks hacia n8n por cuenta (+ secreto HMAC), API keys para n8n, usuarios y roles, logs/auditoría. Todo cifrado en la DB. |

## Deploy en un servidor (Docker)

Requisitos: Docker + Docker Compose (`curl -fsSL https://get.docker.com | sh`).

```bash
# 1. Clonar
git clone https://github.com/buttiepedro/crm_n8n.git /opt/stacks/crm_n8n
cd /opt/stacks/crm_n8n

# 2. Configurar el .env (solo valores operativos)
cp .env.example .env
sed -i "s|^ADMIN_PANEL_PASSWORD=.*|ADMIN_PANEL_PASSWORD=$(openssl rand -base64 18)|" .env
sed -i "s|^CREDENTIALS_ENCRYPTION_KEY=.*|CREDENTIALS_ENCRYPTION_KEY=$(openssl rand -base64 32)|" .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env   # antes del primer up
grep -E "^(ADMIN_PANEL_PASSWORD|CREDENTIALS_ENCRYPTION_KEY)=" .env   # ⚠ guardar estos dos

# 3. Levantar (migraciones y seed corren solos)
docker compose up -d --build

# 4. Credenciales iniciales — se imprimen UNA sola vez
docker compose logs migrate
#   → admin@crm.local + contraseña aleatoria
#   → API key para n8n (ck_live_…)
```

### Puesta en marcha (5 minutos, desde el navegador)

1. **Login**: `http://tu-servidor:8000` con `admin@crm.local` → cambiar contraseña.
2. **⚙️ Panel técnico** (pide la `ADMIN_PANEL_PASSWORD` del `.env`) → pestaña **WhatsApp / Meta**: botón *Generar* verify token, pegar el **App Secret** de tu app de Meta (App settings → Basic) y la **URL del webhook global de tu n8n** (una sola para todas las cuentas).
3. Pestaña **Cuentas**: crear la cuenta con nombre, WABA ID, **Phone Number ID**, número visible y **token permanente** (System User). Botones *Probar* (valida el token contra la Graph API) y *Test n8n* (manda un evento de prueba al webhook).
4. **En Meta for Developers** → WhatsApp → Configuration → Webhook: URL `https://<tu-https>/api/v1/whatsapp/webhook` (puerto **8001**), el verify token del paso 2, y suscribirse al campo `messages`.
5. Pestaña **API Keys** si necesitás más keys para n8n (se muestran una sola vez).

### HTTPS (Meta exige TLS para el webhook)

Cualquier reverse proxy sirve. Con túnel de Cloudflare (sin abrir puertos):

```bash
docker run -d --name cloudflared --restart unless-stopped --network crm_n8n_default \
  cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <TOKEN>
# En Cloudflare Zero Trust:
#   crm.tudominio.com → http://web:80      (panel)
#   api.tudominio.com → http://api:8080    (webhook Meta + hooks n8n)
```

### n8n (externo)

- **Recibir mensajes**: nodo *Webhook* en n8n; su URL se configura **una sola vez** en el panel (WhatsApp/Meta → *Webhook global hacia n8n*): todos los mensajes de todas las cuentas se guardan y se reenvían ahí. El payload trae cuenta, contacto, conversación, lead, mensaje **y `message.raw` con el payload crudo tal cual llegó de WhatsApp**; viene firmado con `X-Signature-256` si configurás el secreto. (Opcional: una cuenta puede definir su propia URL, que pisa la global solo para esa cuenta.)
- **Responder**: nodo *HTTP Request* → `POST http://tu-servidor:8001/api/v1/hooks/n8n/messages` con header `Authorization: Bearer <api_key>` y body `{"conversationId": "...", "message": {"type": "text", "body": "..."}}`.
- **Crear/actualizar lead + notas**: `POST http://tu-servidor:8001/api/v1/hooks/n8n/leads` con `{"conversationId": "...", "externalKey": "...", "stageName": "Calificado", "notes": [{"externalKey": "resumen-ia", "body": "..."}]}` — repetir el mismo `externalKey` **edita** la nota en lugar de duplicarla.

Contratos completos en [roadmap/archive/next_steps_webhooks_n8n.md](roadmap/archive/next_steps_webhooks_n8n.md) y en el OpenAPI (`/api/docs`, visible con `APP_ENV=development`).

## Referencia de la API

⚠ **Todas las rutas llevan el prefijo `/api/v1`** — ej.: `http://host:8001/api/v1/hooks/n8n/messages` (también accesibles por el proxy del front en el puerto 8000). Tres formas de autenticación según el grupo:

| Grupo | Autenticación |
|---|---|
| `/api/v1/auth/**`, `/api/v1/conversations/**`, `/api/v1/leads/**`, `/api/v1/pipelines/**`, `/api/v1/notes/**` | Cookie de sesión (`POST /api/v1/auth/login`) |
| `/api/v1/config/**` (panel técnico) | Cookie + step-up vigente (`POST /api/v1/auth/config-panel`) |
| `/api/v1/hooks/n8n/**` | Header `Authorization: Bearer <api_key>` |
| `/api/v1/whatsapp/webhook` | Firma `X-Hub-Signature-256` de Meta (App Secret) |

Los campos aceptan `camelCase` (y también `snake_case`). Campos desconocidos → `422`. Errores siempre con el formato:

```json
{ "error": { "code": "WINDOW_EXPIRED", "message": "…", "details": [], "traceId": "…" } }
```

Con `APP_ENV=development` está el OpenAPI interactivo en `/api/docs`.

### Autenticación

```jsonc
POST /api/v1/auth/login          { "email": "a@b.com", "password": "…" }   // → set-cookie crm_session
POST /api/v1/auth/logout         // sin body
GET  /api/v1/auth/me             // → { id, email, name, role, permissions[], configPanelUntil }
POST /api/v1/auth/config-panel   { "password": "…" }                       // ADMIN_PANEL_PASSWORD del .env → 15 min
POST /api/v1/auth/password       { "currentPassword": "…", "newPassword": "mín 10 chars" }
```

### Conversaciones y mensajes (CRM)

```jsonc
GET  /api/v1/conversations?accountId=&status=open|pending|closed&assignedUserId=&unread=true&q=&before=<ISO>&limit=50
GET  /api/v1/conversations/{id}
GET  /api/v1/conversations/{id}/messages?before=<ISO>&limit=50
POST /api/v1/conversations/{id}/read    // sin body: marca leída
PATCH /api/v1/conversations/{id}        { "status": "closed" }           // o { "assignedUserId": "<uuid>" } o { "unassign": true }

POST /api/v1/conversations/{id}/messages   // → 202 { "messageId", "status": "queued" }
// El "message content" (mismo formato acá y en el hook de n8n):
{ "type": "text", "body": "Hola!" }
{ "type": "image", "mediaUrl": "https://…/foto.jpg", "body": "caption opcional" }
{ "type": "document", "mediaUrl": "https://…/f.pdf", "fileName": "factura.pdf" }
{ "type": "audio" | "video", "mediaUrl": "https://…" }
{ "type": "template", "template": { "name": "hola_cliente", "language": "es_AR", "components": [] } }
// Reglas: text→body requerido; media→mediaUrl requerido; template→template requerido.
// Fuera de la ventana de 24h solo se acepta type=template (409 WINDOW_EXPIRED).
```

### Notas internas

```jsonc
GET    /api/v1/conversations/{id}/notes
POST   /api/v1/conversations/{id}/notes  { "body": "texto de la nota" }
PATCH  /api/v1/notes/{id}                { "body": "texto editado" }     // propia, o notes:edit:any
DELETE /api/v1/notes/{id}                // borrado lógico
GET    /api/v1/attachments/{id}/download // binario del adjunto
GET    /api/v1/users                     // usuarios activos (para selects de asignación)
```

### Leads y embudo

```jsonc
GET    /api/v1/pipelines                 // pipelines con etapas ordenadas + conteo y valor por etapa
POST   /api/v1/pipelines                 { "name": "Ventas B2B", "isDefault": false }
POST   /api/v1/pipelines/{id}/stages     { "name": "Demo", "color": "#22c55e", "position": 3,
                                           "isTerminal": false, "outcome": null }   // outcome: "won" | "lost"
PATCH  /api/v1/stages/{id}               // mismo shape (reordena con position)
DELETE /api/v1/stages/{id}?moveLeadsToStageId=<uuid>   // requerido si la etapa tiene leads

GET    /api/v1/leads?pipelineId=&stageId=&q=&limit=100
POST   /api/v1/leads                     { "conversationId": "<uuid>", "title": "opcional",
                                           "value": 150000, "currency": "ARS", "stageId": "opcional" }
GET    /api/v1/leads/{id}                // + history[] (movimientos) + notes[]
PATCH  /api/v1/leads/{id}                { "title": "…", "value": 200000, "currency": "ARS", "ownerUserId": "<uuid>" }
PATCH  /api/v1/leads/{id}/stage          { "stageId": "<uuid>" }
DELETE /api/v1/leads/{id}
```

### Hooks para n8n (`Authorization: Bearer ck_live_…`)

```jsonc
// 1) Responder a WhatsApp — scope hooks:messages → 202 { "messageId", "status" }
POST /api/v1/hooks/n8n/messages
{
  "conversationId": "<uuid>",            // opción A: viene en el webhook saliente
  // "accountId": "<uuid>", "to": "5491122334455",   // opción B: abre conversación
  "message": { "type": "text", "body": "Respuesta del bot" }   // mismo formato que arriba
}

// 2) Crear/actualizar lead + notas — scope hooks:leads → 200/201
POST /api/v1/hooks/n8n/leads
{
  "conversationId": "<uuid>",            // requerido
  "externalKey": "wf-ventas-123",        // idempotencia: mismo key → mismo lead (upsert)
  "title": "Juan — Plan Premium",        // solo se actualizan los campos enviados
  "value": 150000, "currency": "ARS",
  "stageName": "Calificado",             // o "stageId"; "pipelineId" opcional (default si falta)
  "ownerUserEmail": "vendedor@empresa.com",
  "attributes": { "campania": "julio" },
  "notes": [
    { "externalKey": "resumen-ia", "body": "…" }   // mismo externalKey → EDITA la nota
  ]
}
// → { "leadId", "created": true|false, "stage": {id,name}, "notes": [{id, externalKey, created}] }
```

### Webhook saliente hacia n8n (lo que RECIBE tu workflow)

`POST` a la URL global (o de la cuenta) con headers `X-Event-Type: message.received`, `X-Event-Id` y `X-Signature-256` (si hay secreto):

```jsonc
{
  "event": "message.received", "eventId": "…", "occurredAt": "2026-07-04T…Z",
  "account":      { "id", "name", "phoneNumberId", "displayPhoneNumber" },
  "conversation": { "id", "status", "assignedUserId" },       // id → usarlo para responder
  "contact":      { "id", "waId", "profileName" },
  "lead":         { "id", "stageId", "externalKey" },          // null si no hay
  "message": {
    "id", "wamid", "type", "body",
    "raw": { /* mensaje CRUDO tal cual llegó de WhatsApp/Meta */ },
    "waTimestamp", "attachments": [ { "id", "mimeType", "fileName", "storagePath" } ]
  }
}
```

### Panel técnico (`/api/v1/config/**` — cookie + step-up)

```jsonc
GET  /api/v1/config/platform      // → { verifyToken, appSecretSet, graphApiVersion, n8nWebhookUrl, n8nWebhookSecretSet }
PUT  /api/v1/config/platform      { "verifyToken": "…", "appSecret": "…", "graphApiVersion": "v21.0",
                                    "n8nWebhookUrl": "https://…", "n8nWebhookSecret": "…" }   // todos opcionales; "" quita
POST /api/v1/config/platform/generate-verify-token

GET   /api/v1/config/accounts
POST  /api/v1/config/accounts     { "name": "Ventas AR", "wabaId": "…", "phoneNumberId": "…",
                                    "displayPhoneNumber": "+54 9 11 …", "accessToken": "EAAG…",   // write-only
                                    "n8nInboundWebhookUrl": "opcional", "n8nWebhookSecret": "opcional" }
PATCH /api/v1/config/accounts/{id}        // cualquier subset + { "status": "active|paused" } |
                                          // { "accessToken": "nuevo" } | { "clearWebhookUrl": true }
POST  /api/v1/config/accounts/{id}/test          // prueba el token contra la Graph API
POST  /api/v1/config/accounts/{id}/test-webhook  // evento sintético al webhook n8n

GET  /api/v1/config/api-keys
POST /api/v1/config/api-keys      { "name": "n8n-prod", "scopes": ["hooks:messages","hooks:leads"] }
                                  // → { id, apiKey: "ck_live_…" }  ⚠ se muestra UNA sola vez
POST /api/v1/config/api-keys/{id}/revoke

GET   /api/v1/config/users
POST  /api/v1/config/users        { "email": "…", "name": "…", "role": "agent|supervisor|admin", "password": "mín 10" }
PATCH /api/v1/config/users/{id}   { "name": "…", "role": "…", "isActive": false, "password": "reset opcional" }

GET  /api/v1/config/event-logs?action=&entityType=&before=&limit=100        // auditoría
GET  /api/v1/config/webhook-deliveries?accountId=&onlyFailed=true&limit=100 // entregas a n8n
POST /api/v1/config/webhook-deliveries/{id}/redeliver
GET  /api/v1/config/failed-messages
POST /api/v1/config/messages/{id}/requeue
```

### Webhook de Meta (lo llama Meta, no vos)

```
GET  /api/v1/whatsapp/webhook   → handshake de verificación (hub.challenge, verify token del panel)
POST /api/v1/whatsapp/webhook   → eventos de WhatsApp; exige firma X-Hub-Signature-256 válida
```

## Operación

```bash
docker compose ps                          # estado
docker compose logs -f api                 # logs en vivo (JSON estructurado con trace_id)
git pull && docker compose up -d --build   # actualizar (migraciones corren solas)
docker exec crm_n8n_db pg_dump -U crm crm > backup_$(date +%F).sql   # backup (cronear diario)
docker compose down                        # apagar (datos persisten en volúmenes)
docker compose down -v                     # ⚠ borra TODO, incluida la DB
```

Dentro del panel técnico: **Logs → Auditoría** (quién hizo qué), **Entregas n8n** (cada intento, con botón de re-entrega) y **Mensajes fallidos** (con re-encolado).

## Desarrollo local

```bash
docker compose up -d db                    # solo la DB... o levantá todo el stack
cd apps/api && uv sync
uv run alembic upgrade head && uv run python scripts/seed.py
uv run uvicorn app.main:app --reload --port 8080
# tests y validación sin DB:
uv run pytest                              # 36 tests
uv run python scripts/generate_ddl.py      # DDL de las 18 tablas desde los modelos

cd ../web && npm install && npm run dev    # front con hot reload en :8000
```

## Estructura del repo

```
.env.example          → único archivo de configuración (operativo)
docker-compose.yml    → db + migrate + api + web (puertos 8000/8001)
apps/api/             → FastAPI: modules/ (whatsapp, hooks, auth, conversations,
                        leads, config, n8n_dispatch…), db/models/, alembic/
apps/web/             → React SPA: Inbox, Leads (kanban), Panel técnico
roadmap/              → diseño pendiente (seguridad CI, observabilidad, GCP)
roadmap/archive/      → diseño ya implementado (arquitectura, DB, WhatsApp,
                        webhooks n8n, auth, CRM, embudo, panel)
```

## Estado del desarrollo

✅ Implementado: mensajería WhatsApp completa, puente n8n (3 webhooks), CRM con roles, embudo configurable, notas internas editables por webhook, panel técnico. Pendiente ([roadmap/](roadmap/README.md)): métricas/alertas, hardening de CI (gitleaks, pip-audit), despliegue GCP (Cloud Run/Tasks/GCS) y mejoras residuales (WebSockets, plantillas desde la UI, búsqueda full-text).
