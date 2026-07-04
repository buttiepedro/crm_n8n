# Next Steps — Base de datos (PostgreSQL)

## Objetivo

Diseñar el esquema PostgreSQL que almacena **todos** los mensajes, adjuntos, conversaciones, leads, notas, cuentas WhatsApp, usuarios, configuración y auditoría. Es el contrato central del sistema: los demás documentos referencian estas tablas.

## Principios

- PK: **UUID v7** (`id`) en todas las tablas — ordenable por tiempo, generado en la app.
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` y `updated_at` (manejado por SQLAlchemy con `onupdate=func.now()`) en todas las tablas.
- Payloads crudos de Meta en **JSONB** (`raw_payload`): nunca perder información aunque el modelo no la contemple todavía.
- Borrado lógico (`deleted_at`) solo donde el negocio lo pida (notas, leads); mensajes y auditoría son inmutables.
- Enums de PostgreSQL para estados (mejor validación que texto libre).
- Multi-cuenta desde el día 1: casi todo cuelga de `whatsapp_account_id`.

## Esquema (DDL de referencia)

> La implementación real es con modelos SQLAlchemy 2.0 (`apps/api/app/db/models/`) y migraciones Alembic; este DDL es la especificación.

### Identidad y acceso

```sql
CREATE TYPE user_role AS ENUM ('admin', 'supervisor', 'agent');

CREATE TABLE users (
  id            UUID PRIMARY KEY,
  email         CITEXT UNIQUE NOT NULL,
  name          TEXT NOT NULL,
  password_hash TEXT NOT NULL,           -- argon2id
  role          user_role NOT NULL DEFAULT 'agent',
  is_active     BOOLEAN NOT NULL DEFAULT true,
  last_login_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Permisos finos adicionales al rol (ver doc de autenticación)
CREATE TABLE user_permissions (
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  permission TEXT NOT NULL,              -- p.ej. 'leads:delete', 'config:read'
  PRIMARY KEY (user_id, permission)
);

CREATE TABLE sessions (
  id             UUID PRIMARY KEY,
  user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash     TEXT UNIQUE NOT NULL,   -- sha256 del token de cookie
  config_panel_until TIMESTAMPTZ,        -- step-up: acceso al panel de config vigente hasta
  ip             INET,
  user_agent     TEXT,
  expires_at     TIMESTAMPTZ NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- API keys para los webhooks entrantes de n8n
CREATE TABLE api_keys (
  id          UUID PRIMARY KEY,
  name        TEXT NOT NULL,             -- 'n8n-produccion'
  key_hash    TEXT UNIQUE NOT NULL,      -- sha256; el valor solo se muestra al crearla
  key_prefix  TEXT NOT NULL,             -- 'ck_live_abc…' para identificarla en el panel
  scopes      TEXT[] NOT NULL,           -- {'hooks:messages','hooks:leads'}
  is_active   BOOLEAN NOT NULL DEFAULT true,
  last_used_at TIMESTAMPTZ,
  created_by  UUID REFERENCES users(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at  TIMESTAMPTZ
);
```

### Cuentas WhatsApp

```sql
CREATE TYPE wa_account_status AS ENUM ('active', 'paused', 'error');

CREATE TABLE whatsapp_accounts (
  id                    UUID PRIMARY KEY,
  name                  TEXT NOT NULL,              -- alias interno: 'Ventas AR'
  waba_id               TEXT NOT NULL,              -- WhatsApp Business Account ID
  phone_number_id       TEXT UNIQUE NOT NULL,       -- clave de ruteo de webhooks de Meta
  display_phone_number  TEXT NOT NULL,
  access_token_ciphertext BYTEA NOT NULL,           -- token cifrado AES-256-GCM
  token_key_version     SMALLINT NOT NULL DEFAULT 1,-- para rotación de clave maestra
  status                wa_account_status NOT NULL DEFAULT 'active',
  n8n_inbound_webhook_url TEXT,                     -- URL de n8n a la que se reenvían mensajes
  n8n_webhook_secret_ciphertext BYTEA,              -- secreto HMAC del webhook saliente, cifrado
  settings              JSONB NOT NULL DEFAULT '{}',-- p.ej. { "forwardStatuses": false }
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Contactos, conversaciones y mensajes

```sql
CREATE TABLE contacts (
  id           UUID PRIMARY KEY,
  wa_id        TEXT NOT NULL,            -- número E.164 del cliente en WhatsApp
  profile_name TEXT,
  attributes   JSONB NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (wa_id)
);

CREATE TYPE conversation_status AS ENUM ('open', 'pending', 'closed');

CREATE TABLE conversations (
  id                  UUID PRIMARY KEY,
  whatsapp_account_id UUID NOT NULL REFERENCES whatsapp_accounts(id),
  contact_id          UUID NOT NULL REFERENCES contacts(id),
  status              conversation_status NOT NULL DEFAULT 'open',
  assigned_user_id    UUID REFERENCES users(id),
  last_message_at     TIMESTAMPTZ,
  last_inbound_at     TIMESTAMPTZ,       -- para calcular la ventana de 24h
  unread_count        INT NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (whatsapp_account_id, contact_id)
);

CREATE TYPE message_direction AS ENUM ('inbound', 'outbound');
CREATE TYPE message_status AS ENUM ('queued','sent','delivered','read','failed','received');
CREATE TYPE message_origin AS ENUM ('whatsapp','crm_user','n8n');
CREATE TYPE message_type AS ENUM ('text','image','audio','video','document','sticker','location','contacts','template','interactive','reaction','unknown');

CREATE TABLE messages (
  id                  UUID PRIMARY KEY,
  conversation_id     UUID NOT NULL REFERENCES conversations(id),
  whatsapp_account_id UUID NOT NULL REFERENCES whatsapp_accounts(id),
  wamid               TEXT UNIQUE,       -- id de Meta; NULL hasta que un saliente se envía
  direction           message_direction NOT NULL,
  origin              message_origin NOT NULL,
  sent_by_user_id     UUID REFERENCES users(id),  -- si origin = 'crm_user'
  type                message_type NOT NULL,
  body                TEXT,              -- texto o caption
  status              message_status NOT NULL,
  error_detail        JSONB,             -- respuesta de error de Meta si failed
  raw_payload         JSONB,             -- evento crudo de Meta (inbound) o request (outbound)
  reply_to_message_id UUID REFERENCES messages(id),
  wa_timestamp        TIMESTAMPTZ,       -- timestamp reportado por WhatsApp
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Historial de estados de entrega (Meta manda sent/delivered/read como eventos separados)
CREATE TABLE message_status_events (
  id          UUID PRIMARY KEY,
  message_id  UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  status      message_status NOT NULL,
  raw_payload JSONB,
  occurred_at TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE attachments (
  id           UUID PRIMARY KEY,
  message_id   UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  media_id     TEXT,                     -- id de media en Meta
  gcs_path     TEXT,                     -- NULL hasta completar la descarga
  mime_type    TEXT NOT NULL,
  file_name    TEXT,
  size_bytes   BIGINT,
  sha256       TEXT,
  download_status TEXT NOT NULL DEFAULT 'pending',  -- pending|done|failed
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Leads, embudo y notas

```sql
CREATE TABLE pipelines (
  id         UUID PRIMARY KEY,
  name       TEXT NOT NULL,
  is_default BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE pipeline_stages (
  id          UUID PRIMARY KEY,
  pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  position    INT NOT NULL,              -- orden en el embudo
  color       TEXT,
  is_terminal BOOLEAN NOT NULL DEFAULT false,  -- ganado/perdido
  outcome     TEXT CHECK (outcome IN ('won','lost')),
  UNIQUE (pipeline_id, position)
);

CREATE TABLE leads (
  id              UUID PRIMARY KEY,
  contact_id      UUID NOT NULL REFERENCES contacts(id),
  conversation_id UUID REFERENCES conversations(id),
  pipeline_id     UUID NOT NULL REFERENCES pipelines(id),
  stage_id        UUID NOT NULL REFERENCES pipeline_stages(id),
  external_key    TEXT,                  -- clave idempotente para upsert desde n8n
  title           TEXT NOT NULL,
  value           NUMERIC(14,2),
  currency        CHAR(3) DEFAULT 'ARS',
  source          TEXT NOT NULL DEFAULT 'manual',  -- 'manual' | 'n8n_webhook'
  owner_user_id   UUID REFERENCES users(id),
  attributes      JSONB NOT NULL DEFAULT '{}',     -- campos custom desde n8n
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ,
  UNIQUE (external_key)
);

-- Historial de movimientos en el embudo (para métricas de conversión)
CREATE TABLE lead_stage_events (
  id            UUID PRIMARY KEY,
  lead_id       UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  from_stage_id UUID REFERENCES pipeline_stages(id),
  to_stage_id   UUID NOT NULL REFERENCES pipeline_stages(id),
  moved_by      TEXT NOT NULL,           -- 'user:<uuid>' | 'webhook:<api_key_id>'
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Notas internas: viven en el chat y se asocian al lead de esa conversación.
-- Editables/creables también desde el webhook de leads (vía external_key).
CREATE TABLE notes (
  id              UUID PRIMARY KEY,
  lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES conversations(id),
  external_key    TEXT,                  -- idempotencia/edición desde n8n
  body            TEXT NOT NULL,
  author_user_id  UUID REFERENCES users(id),   -- NULL si vino de n8n
  author_source   TEXT NOT NULL DEFAULT 'user',-- 'user' | 'n8n_webhook'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ,
  UNIQUE (lead_id, external_key),
  CHECK (lead_id IS NOT NULL OR conversation_id IS NOT NULL)
);
```

### Configuración, auditoría y entregas de webhooks

```sql
CREATE TABLE settings (
  key        TEXT PRIMARY KEY,           -- 'general.timezone', 'inbox.autoclose_days'
  value      JSONB NOT NULL,
  updated_by UUID REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auditoría de negocio (quién hizo qué) — inmutable, visible en el panel
CREATE TABLE event_logs (
  id          UUID PRIMARY KEY,
  actor_type  TEXT NOT NULL,             -- 'user' | 'api_key' | 'system' | 'meta'
  actor_id    UUID,
  action      TEXT NOT NULL,             -- 'lead.stage_changed', 'account.token_rotated', …
  entity_type TEXT,
  entity_id   UUID,
  metadata    JSONB NOT NULL DEFAULT '{}',
  trace_id    TEXT,                      -- correlación con Cloud Logging
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trazabilidad de cada intento de entrega hacia n8n
CREATE TABLE webhook_deliveries (
  id                  UUID PRIMARY KEY,
  whatsapp_account_id UUID NOT NULL REFERENCES whatsapp_accounts(id),
  target_url          TEXT NOT NULL,
  event_type          TEXT NOT NULL,     -- 'message.received', …
  payload             JSONB NOT NULL,
  attempt             INT NOT NULL DEFAULT 1,
  response_status     INT,
  response_body       TEXT,              -- truncado a 4KB
  succeeded           BOOLEAN NOT NULL DEFAULT false,
  next_retry_at       TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Índices críticos

```sql
CREATE INDEX idx_messages_conversation ON messages (conversation_id, created_at DESC);
CREATE INDEX idx_messages_account_created ON messages (whatsapp_account_id, created_at DESC);
CREATE INDEX idx_conversations_inbox ON conversations (whatsapp_account_id, status, last_message_at DESC);
CREATE INDEX idx_conversations_assigned ON conversations (assigned_user_id) WHERE status <> 'closed';
CREATE INDEX idx_leads_stage ON leads (pipeline_id, stage_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_notes_lead ON notes (lead_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_event_logs_entity ON event_logs (entity_type, entity_id, created_at DESC);
CREATE INDEX idx_event_logs_created ON event_logs (created_at DESC);
CREATE INDEX idx_webhook_deliveries_pending ON webhook_deliveries (next_retry_at) WHERE succeeded = false;
CREATE INDEX idx_messages_body_search ON messages USING gin (to_tsvector('spanish', coalesce(body,'')));
```

## Pasos de desarrollo

- [ ] Modelar el esquema completo en modelos SQLAlchemy (`app/db/models/`); email único normalizado a minúsculas en la app (evita depender de `citext`).
- [ ] Primera migración (`alembic revision --autogenerate` + `alembic upgrade head`) contra PostgreSQL 16 local en Docker.
- [ ] Seed de desarrollo: usuario admin, pipeline por defecto ("Nuevo → Contactado → Calificado → Propuesta → Ganado/Perdido"), cuenta WhatsApp de prueba.
- [ ] `updated_at` con `onupdate=func.now()` en el mixin de base de los modelos.
- [ ] Función/servicio de generación UUID v7 compartido.
- [ ] Tests de integración de constraints clave: unicidad de `wamid`, `UNIQUE (lead_id, external_key)` en notas, `CHECK` de notas.
- [ ] Documentar en el repo el diagrama ER generado (`eralchemy` o dbdocs) + script `scripts/generate_ddl.py` que emite el DDL PostgreSQL desde los modelos (validación sin DB).
- [ ] Plan de retención: los mensajes no se borran; definir particionado por rango de `created_at` en `messages` y `event_logs` cuando superen ~10M filas (documentar el umbral, no implementarlo aún).

## Buenas prácticas

- **Nunca** guardar tokens/secretos en claro: solo columnas `*_ciphertext` (BYTEA con IV+tag+ciphertext) o hashes.
- Toda escritura que cruce tablas (mensaje + conversación + contacto) va en **una transacción**.
- Acceso a datos solo mediante servicios del módulo dueño de la tabla — otros módulos llaman al servicio, no a la sesión de SQLAlchemy directo.
- Backups automáticos de Cloud SQL + PITR habilitado; probar una restauración antes del go-live.
- Usuario de DB de la app **sin** permisos DDL en producción; las migraciones corren con un usuario separado en el pipeline de deploy.

## Criterios de aceptación

- Reprocesar el mismo webhook de Meta dos veces no duplica mensajes (unicidad `wamid`).
- Enviar dos veces el mismo payload de lead/nota desde n8n con el mismo `external_key` produce una sola fila, actualizada.
- La bandeja de conversaciones (50 conversaciones con último mensaje) responde < 100 ms con 1M de mensajes en la DB (validar con datos sintéticos).
