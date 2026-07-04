# Next Steps — Arquitectura

## Objetivo

Definir la arquitectura de una plataforma en Google Cloud que:

1. Recibe todos los eventos de la **WhatsApp Business Cloud API** (Meta) y los persiste íntegramente (mensajes, adjuntos, estados, conversaciones) en PostgreSQL.
2. Reenvía los mensajes entrantes a **n8n** mediante webhooks salientes configurables por cuenta.
3. Expone **dos webhooks entrantes** para n8n: envío de respuestas a WhatsApp y creación/actualización de leads (incluyendo notas internas).
4. Funciona como **CRM autónomo**: leer/enviar mensajes sin pasar por n8n, gestionar leads en un embudo configurable, notas internas, usuarios con roles.
5. Ofrece un **panel de configuración** protegido por contraseña de `.env` para logs, credenciales, cuentas WhatsApp y webhooks n8n.

## Diagrama de alto nivel

```
                            ┌─────────────────────────── Google Cloud ───────────────────────────┐
                            │                                                                     │
 Meta (WhatsApp Cloud API)  │   ┌──────────────┐        ┌──────────────┐      ┌───────────────┐  │
 ── webhook mensajes ──────────▶│              │───────▶│  Cloud SQL   │      │ Cloud Storage │  │
 ◀── envío mensajes/media ──────│   apps/api   │        │ (PostgreSQL) │      │  (adjuntos)   │  │
                            │   │   FastAPI    │───────────────────────────── ▶│               │  │
                            │   │  Cloud Run   │        └──────────────┘      └───────────────┘  │
 n8n                        │   │              │                                                  │
 ◀── webhook saliente ──────────│              │◀──────┐ ┌─────────────┐     ┌────────────────┐  │
 ── hook respuestas ───────────▶│              │       └─│ Cloud Tasks │     │ Secret Manager │  │
 ── hook leads/notas ──────────▶│              │─ encola ▶│ (reintentos)│     │ (secretos)     │  │
                            │   └──────┬───────┘         └─────────────┘     └────────────────┘  │
                            │          │ REST + WebSocket                                        │
                            │   ┌──────┴───────┐         ┌──────────────┐                        │
 Usuarios (agentes/admin) ─────▶│   apps/web   │         │Cloud Logging │                        │
                            │   │ React SPA    │         │+ Monitoring  │                        │
                            │   │ Cloud Run    │         └──────────────┘                        │
                            │   └──────────────┘                                                 │
                            └─────────────────────────────────────────────────────────────────────┘
```

## Servicios GCP y su rol

| Servicio | Rol | Notas |
|---|---|---|
| **Cloud Run (api)** | Backend FastAPI (Uvicorn): REST, webhooks, WebSocket | min-instances=1 en prod (los webhooks de Meta no toleran cold starts largos) |
| **Cloud Run (web)** | Sirve la SPA (nginx o Caddy con el build de Vite) | Puede escalar a cero |
| **Cloud SQL (PostgreSQL 16)** | Única fuente de verdad de datos | IP privada + Cloud SQL Auth Proxy/conector; sin IP pública |
| **Cloud Storage** | Binarios de adjuntos (imágenes, audio, docs, video) | Bucket privado; acceso vía URLs firmadas de corta duración |
| **Cloud Tasks** | Cola de envíos salientes (a WhatsApp y a n8n) con reintentos exponenciales | Dos colas: `outbound-whatsapp`, `outbound-n8n` |
| **Secret Manager** | `SESSION_SECRET`, `CREDENTIALS_ENCRYPTION_KEY`, `WHATSAPP_APP_SECRET`, `ADMIN_PANEL_PASSWORD`, `DATABASE_URL` | Montados como env vars en Cloud Run mediante referencias a secretos |
| **Cloud Logging / Monitoring** | Logs técnicos estructurados, métricas, alertas | Ver doc de observabilidad |
| **Artifact Registry** | Imágenes Docker de api y web | Publicadas por CI |

## Módulos del backend (FastAPI)

```
apps/api/app/
  modules/
    auth/            # login, sesiones, roles, permisos, step-up panel config
    whatsapp/        # webhook Meta, cliente Graph API, descarga de media, multi-cuenta
    conversations/   # conversaciones, mensajes, asignación, lectura
    leads/           # leads, pipelines, etapas, notas internas
    hooks/           # los 2 webhooks entrantes de n8n (messages, leads)
    n8n_dispatch/    # webhook saliente hacia n8n + reintentos
    accounts/        # cuentas WhatsApp: credenciales cifradas, estado, configuración
    settings/        # configuración general de plataforma
    audit/           # event_logs de auditoría de negocio
    attachments/     # metadatos + URLs firmadas de GCS
  core/
    config.py        # settings validadas con pydantic-settings (fail-fast)
    logging.py       # structlog JSON + trace_id
    errors.py        # DomainError + exception handlers
    crypto.py        # AES-256-GCM para credenciales
    security.py      # firmas HMAC, hashing de API keys
  db/
    models/          # modelos SQLAlchemy 2.0 (fuente del esquema)
    session.py       # engine async + sessionmaker
  schemas/           # contratos Pydantic (webhooks, hooks, enums, códigos de error)
  infra/
    queue.py storage.py                     # adaptadores: Cloud Tasks/inline, GCS/local
```

Reglas de dependencia: `modules` pueden depender de `core`, `db`, `schemas` e `infra`, nunca al revés (verificado con `import-linter`). `hooks` y `whatsapp` no contienen lógica de negocio de CRM: delegan en `conversations` y `leads` (servicios de dominio compartidos), de modo que crear un lead desde el panel o desde el webhook pasa por el mismo código.

## Flujos principales

### 1. Mensaje entrante (WhatsApp → plataforma → n8n)

1. Meta hace `POST /api/v1/whatsapp/webhook` con el evento.
2. Se valida la firma `X-Hub-Signature-256` con `WHATSAPP_APP_SECRET` sobre el **body crudo**.
3. Se responde `200` inmediatamente (Meta exige < 20s; procesar async).
4. Procesamiento: idempotencia por `wamid`, upsert de `contacts` y `conversations`, insert de `messages` con payload crudo en JSONB, si hay media → tarea de descarga a GCS → `attachments`.
5. Se encola en Cloud Tasks un POST al webhook n8n configurado para esa cuenta (con HMAC propio). Reintentos exponenciales; fallos definitivos quedan en `event_logs` y visibles en el panel.
6. El WebSocket gateway emite el mensaje a los agentes conectados que ven esa conversación.

### 2. Respuesta desde n8n (n8n → plataforma → WhatsApp)

1. n8n hace `POST /api/v1/hooks/n8n/messages` autenticado con API key + HMAC.
2. Validación del payload (Pydantic), resolución de conversación/cuenta.
3. El mensaje se persiste con estado `queued` y se encola el envío a la Graph API vía Cloud Tasks.
4. El worker envía, guarda el `wamid` devuelto, y los webhooks de estado de Meta (`sent`, `delivered`, `read`, `failed`) actualizan `message_status_events`.

### 3. Lead desde n8n (n8n → plataforma)

1. n8n hace `POST /api/v1/hooks/n8n/leads`.
2. Upsert del lead (por `external_key` o `conversation_id`), asignación a etapa del embudo, y upsert de notas internas por `external_key` de nota (crear si no existe, editar si existe).

### 4. Envío manual desde el CRM

Igual que el flujo 2 pero originado por un agente autenticado; misma cola, mismo pipeline de estados. Se respeta la ventana de 24h de WhatsApp: fuera de ventana solo se permiten plantillas aprobadas (la UI lo indica).

## Decisiones de arquitectura (ADR resumidas)

| Decisión | Alternativa descartada | Razón |
|---|---|---|
| FastAPI sobre Flask/Django | Framework sync o full-stack | Requisito del proyecto; async nativo (webhooks IO-bound), Pydantic para contratos estrictos, `Depends` para auth/permisos, OpenAPI automático |
| Cloud Tasks para salidas | Enviar en línea en el request | Reintentos con backoff sin bloquear webhooks; los webhooks siempre responden rápido |
| Adjuntos en GCS, no en DB | `bytea` en PostgreSQL | Coste, backups y rendimiento; DB guarda solo metadatos + ruta |
| Credenciales WhatsApp cifradas en DB (AES-256-GCM, clave en Secret Manager) | Un secreto por cuenta en Secret Manager | Las cuentas se gestionan dinámicamente desde el panel; evita otorgar permisos de escritura de secretos al runtime |
| Sesiones con cookie httpOnly | JWT en localStorage | Revocación server-side inmediata, inmune a XSS para robo de token |
| WebSockets nativos de FastAPI para tiempo real | Polling | UX de chat; con más de 1 instancia difundir eventos vía pub/sub Redis (Memorystore) |
| Monolito modular | Microservicios | Un solo equipo/dominio; los módulos (routers + servicios) permiten extraer servicios más adelante si hace falta |

## Pasos de desarrollo

- [ ] Inicializar monorepo con `apps/api` (Python 3.12 + uv) y `apps/web` (React + Vite).
- [ ] Bootstrap FastAPI con `core/config.py` que valida todas las env vars con pydantic-settings al arranque (fail-fast).
- [ ] `docker-compose.yml` local: PostgreSQL 16 + n8n local para pruebas (adjuntos con driver de storage local en dev).
- [ ] Esqueleto de módulos vacíos con sus límites de dependencia (`import-linter` con contrato de capas).
- [ ] Healthchecks: `GET /api/v1/health` (liveness) y `GET /api/v1/health/ready` (readiness: DB + GCS accesibles).
- [ ] Definir en `app/schemas/` los contratos Pydantic: payloads de webhooks, enums de estados de mensaje/lead, códigos de error (los tipos TS del frontend se generan luego desde OpenAPI).
- [ ] Pipeline CI mínimo: lint, typecheck, tests, build de imágenes.

## Buenas prácticas desde el inicio

- **12-factor**: configuración solo por entorno; ninguna credencial en el código ni en el repo.
- **Idempotencia en todos los bordes**: `wamid` para mensajes de Meta, `Idempotency-Key`/`external_key` en los hooks de n8n. Los reintentos (de Meta, de Cloud Tasks, de n8n) no deben duplicar datos.
- **Responder webhooks rápido**: persistir lo mínimo + encolar; nunca llamar APIs externas dentro del handler del webhook.
- **Contratos tipados compartidos**: schemas Pydantic como única fuente; el OpenAPI generado documenta los hooks para quien arma los workflows de n8n.
- **Migraciones siempre hacia adelante** (Alembic), nunca editar migraciones aplicadas.

## Criterios de aceptación

- Un mensaje de WhatsApp llega, queda persistido con su payload crudo, su media en GCS, y n8n lo recibe — todo trazable por un `trace_id` común en logs.
- Caída de n8n: los mensajes se siguen almacenando y los reenvíos se reintentan automáticamente al volver.
- Caída de la Graph API: las respuestas quedan en cola con backoff, ninguna se pierde.
- El sistema arranca solo si todas las variables de entorno requeridas están presentes y bien formadas.
