# Roadmap — Plataforma CRM intermediaria WhatsApp Business ↔ n8n

Plataforma en Google Cloud que actúa como intermediario entre la **API de WhatsApp Business (Cloud API de Meta)** y **n8n**, almacenando todos los mensajes, adjuntos y conversaciones en PostgreSQL, y funcionando como CRM completo: lectura y envío de mensajes (dentro y fuera de n8n), registro de leads con embudo configurable, notas internas, roles y permisos, y un panel de configuración protegido por contraseña definida en `.env`.

## Stack de referencia (decisión transversal)

| Capa | Tecnología | Justificación |
|---|---|---|
| Backend | Python 3.12 + **FastAPI** (async, Uvicorn) | Requisito del proyecto; async nativo para webhooks IO-bound, Pydantic v2 para contratos estrictos, OpenAPI automático, `Depends` para auth/permisos |
| ORM | **SQLAlchemy 2.0 (async) + Alembic** | Migraciones versionadas, modelos tipados (`Mapped[...]`), dialecto PostgreSQL completo (JSONB, enums, arrays) |
| Base de datos | **PostgreSQL 16 en Cloud SQL** | Requisito del proyecto; JSONB para payloads crudos de WhatsApp |
| Frontend | **React 18 + Vite + TypeScript** (SPA) | Panel CRM interactivo; TanStack Query + WebSockets para tiempo real |
| Adjuntos | **Google Cloud Storage** | Los binarios nunca van a PostgreSQL; solo metadatos y ruta GCS |
| Cola/async | **Cloud Tasks** (+ Pub/Sub si crece) | Reintentos de envío a WhatsApp y de webhooks hacia n8n |
| Secretos | **Google Secret Manager** | Credenciales de plataforma; credenciales de cuentas WhatsApp cifradas en DB con clave maestra en Secret Manager |
| Hosting | **Cloud Run** (API y Web como servicios separados) | Escala a cero, autoscaling horizontal, HTTPS gestionado |
| Logs | **structlog** JSON → Cloud Logging + tabla `event_logs` de auditoría | Separación logs técnicos vs. auditoría de negocio |
| CI/CD | GitHub Actions → Artifact Registry → Cloud Run | Deploy reproducible por commit |

Estructura de monorepo sugerida:

```
/apps
  /api        → FastAPI (REST + webhooks + WebSocket)
  /web        → React SPA (panel CRM + panel de configuración)
/infra        → Terraform / scripts gcloud
/roadmap      → esta documentación
```

Los contratos compartidos viven como schemas **Pydantic** en `apps/api/app/schemas/` (única fuente de verdad: validan en runtime y generan el OpenAPI); los tipos TypeScript del frontend se generan desde OpenAPI (`openapi-typescript`).

## Documentos del roadmap

| # | Archivo | Feature |
|---|---|---|
| 1 | [next_steps_arquitectura.md](next_steps_arquitectura.md) | Arquitectura general, servicios GCP, flujos de datos |
| 2 | [next_steps_base_de_datos.md](next_steps_base_de_datos.md) | Esquema PostgreSQL completo, índices, migraciones |
| 3 | [next_steps_integracion_whatsapp.md](next_steps_integracion_whatsapp.md) | Recepción/envío de mensajes, media, multi-cuenta |
| 4 | [next_steps_webhooks_n8n.md](next_steps_webhooks_n8n.md) | Los 2 webhooks expuestos (respuestas y leads/notas) + webhook saliente hacia n8n |
| 5 | [next_steps_autenticacion_roles.md](next_steps_autenticacion_roles.md) | Login, roles, permisos, step-up del panel de configuración |
| 6 | [next_steps_crm_conversaciones.md](next_steps_crm_conversaciones.md) | Panel de conversaciones, filtros, notas internas, tiempo real |
| 7 | [next_steps_leads_embudo.md](next_steps_leads_embudo.md) | Leads y embudo (pipeline) configurable |
| 8 | [next_steps_panel_configuracion.md](next_steps_panel_configuracion.md) | Panel admin: logs, credenciales WhatsApp, webhooks n8n, cuentas |
| 9 | [next_steps_seguridad.md](next_steps_seguridad.md) | Gestión de secretos, cifrado, HMAC, hardening |
| 10 | [next_steps_observabilidad_logs.md](next_steps_observabilidad_logs.md) | Logging estructurado, manejo de errores, métricas, alertas |
| 11 | [next_steps_despliegue_gcp.md](next_steps_despliegue_gcp.md) | Infraestructura, CI/CD, entornos, escalabilidad |

## Orden de desarrollo recomendado (fases)

**Fase 0 — Fundaciones (semana 1)**
Monorepo, FastAPI + SQLAlchemy/Alembic + PostgreSQL local (Docker), CI básico, esqueleto de configuración con validación de `.env`. → Docs 1, 2, 11.

**Fase 1 — Núcleo de mensajería (semanas 2-3)**
Webhook de Meta (verificación + recepción), persistencia de mensajes/conversaciones/adjuntos, descarga de media a GCS, envío de mensajes con Cloud Tasks. → Docs 3, 2.

**Fase 2 — Puente n8n (semana 4)**
Webhook saliente hacia n8n (mensajes entrantes) y los dos webhooks entrantes: respuestas de n8n → WhatsApp y creación/actualización de leads con notas. → Doc 4.

**Fase 3 — Autenticación y CRM (semanas 5-7)**
Login con roles/permisos, panel de conversaciones (leer/enviar/filtrar), leads con embudo configurable, notas internas. → Docs 5, 6, 7.

**Fase 4 — Panel de configuración (semana 8)**
Step-up con `ADMIN_PANEL_PASSWORD`, gestión de cuentas WhatsApp y credenciales cifradas, configuración de webhooks n8n, visor de logs. → Doc 8.

**Fase 5 — Endurecimiento y producción (semanas 9-10)**
Seguridad (doc 9), observabilidad completa (doc 10), despliegue productivo con dominios, alertas y backups (doc 11).

## Convenciones transversales

- **API versionada**: todo bajo `/api/v1/…`. Webhooks bajo `/api/v1/hooks/…` (entrantes de n8n) y `/api/v1/whatsapp/webhook` (Meta).
- **IDs**: UUID v7 (ordenables por tiempo) como PK en todas las tablas.
- **Dinero/valores de lead**: `NUMERIC`, nunca `FLOAT`.
- **Fechas**: `TIMESTAMPTZ`, siempre UTC en DB; el frontend localiza.
- **Errores API**: formato único `{ "error": { "code": "...", "message": "...", "details": [...] } }` con códigos estables.
- **Variables de entorno** (validadas al arranque con pydantic-settings; el proceso no inicia si falta alguna):

```env
APP_ENV=production            # development | staging | production
PORT=8080
DATABASE_URL=postgresql+asyncpg://...
SESSION_SECRET=...            # firma de cookies de sesión
ADMIN_PANEL_PASSWORD=...      # contraseña explícita del panel de configuración (requisito)
CREDENTIALS_ENCRYPTION_KEY=...# clave maestra AES-256-GCM, 32 bytes base64 (Secret Manager en prod)
WHATSAPP_VERIFY_TOKEN=...     # verificación del webhook de Meta
WHATSAPP_APP_SECRET=...       # validación de firma X-Hub-Signature-256
QUEUE_DRIVER=inline           # inline (dev) | cloud_tasks (prod, P5)
STORAGE_DRIVER=local          # local (dev) | gcs (prod, P5)
GCS_BUCKET_ATTACHMENTS=...    # solo con STORAGE_DRIVER=gcs
GCP_PROJECT_ID=...            # solo en GCP
```

(Implementadas y validadas en `apps/api/app/core/config.py`; plantilla en `apps/api/.env.example`.)

Cada documento define objetivo, diseño técnico, pasos de desarrollo con checklist, buenas prácticas y criterios de aceptación. Los contratos (tablas, endpoints, payloads) son la fuente de verdad compartida: si un documento cambia un contrato, actualizar los demás.
