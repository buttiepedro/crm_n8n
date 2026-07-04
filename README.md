# CRM WhatsApp Business ↔ n8n

Plataforma en Google Cloud que actúa como intermediario entre la **WhatsApp Business Cloud API** (Meta) y **n8n**: persiste todos los mensajes, adjuntos y conversaciones en PostgreSQL y funciona como CRM (leads con embudo configurable, notas internas, roles y panel de configuración protegido).

- **Documentación de diseño y plan de desarrollo**: [roadmap/](roadmap/README.md)
- **Backend**: FastAPI (Python 3.12) + SQLAlchemy 2.0 async + PostgreSQL 16 → [apps/api/](apps/api/)
- **Frontend** (fase 3): React + Vite → `apps/web/`

## Quickstart con Docker (recomendado)

Requisitos: Docker Desktop.

```bash
# 1. Configurar entorno — UN solo .env en la raíz, SOLO valores operativos
cp .env.example .env
# completar ADMIN_PANEL_PASSWORD y CREDENTIALS_ENCRYPTION_KEY:
#   openssl rand -base64 18   →  ADMIN_PANEL_PASSWORD
#   openssl rand -base64 32   →  CREDENTIALS_ENCRYPTION_KEY

# 2. Levantar todo: DB → migraciones + seed (automático) → API → frontend
docker compose up -d --build

# Credenciales iniciales (admin y API key de n8n) las imprime el seed UNA vez:
docker compose logs migrate
```

**Únicos puertos expuestos**: `8000` (frontend) y `8001` (API para n8n y el webhook de Meta). PostgreSQL queda solo en la red interna de Docker.

- **Frontend / CRM**: http://localhost:8000 — login con el admin del seed (`admin@crm.local`)
- **API para n8n**: http://localhost:8001 — hooks `POST /api/v1/hooks/n8n/messages` y `/leads` (`Authorization: Bearer <api_key>`)
- Webhook de Meta: `GET|POST /api/v1/whatsapp/webhook` (túnel HTTPS hacia el **8001**)
- Health: `GET /api/v1/health` · Readiness: `GET /api/v1/health/ready`

**Todo lo demás se configura desde el panel técnico** (⚙️ en el frontend, protegido por `ADMIN_PANEL_PASSWORD`): verify token y App Secret de Meta, cuentas de WhatsApp con sus tokens (cifrados en DB), webhooks hacia n8n por cuenta, API keys, usuarios/roles y visores de logs. **Nada de eso va en el `.env`.**

Las migraciones corren solas en el servicio `migrate` (`alembic upgrade head` + seed idempotente); la API arranca recién cuando terminan bien.

### Puesta en marcha (una vez arriba)

1. Entrar a http://host:8000 con `admin@crm.local` (contraseña en `docker compose logs migrate`) y cambiarla.
2. ⚙️ Panel técnico → pestaña **WhatsApp / Meta**: generar el verify token y cargar el App Secret de tu app de Meta.
3. Pestaña **Cuentas**: crear la cuenta con su Phone Number ID + token permanente + URL del webhook de tu n8n. Botones "Probar" y "Test n8n" verifican ambos lados.
4. En Meta for Developers: webhook → `https://<tu-https>/api/v1/whatsapp/webhook` con el verify token del paso 2, suscripto a `messages`.
5. Pestaña **API Keys**: crear la key para n8n (se muestra una sola vez).

## Desarrollo sin Docker (backend local)

Requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL accesible.

El backend lee el mismo `.env` de la raíz (un `apps/api/.env` local es opcional y lo pisa).

```bash
cd apps/api
uv sync
uv run alembic upgrade head
uv run python scripts/seed.py
uv run uvicorn app.main:app --reload --port 8080

# Frontend en modo dev (hot reload, proxy /api → localhost:8080)
cd ../web
npm install
npm run dev                              # http://localhost:8000
```

## Tests y verificación sin base de datos

```bash
cd apps/api
uv run pytest                            # tests unitarios
uv run python scripts/generate_ddl.py    # emite el DDL PostgreSQL desde los modelos
```

## Estado del desarrollo

Implementado: fundaciones (P0), mensajería WhatsApp (P1), puente n8n (P2), autenticación con roles + CRM completo (P3) y panel técnico (P4). Los documentos de diseño de las fases terminadas están en [roadmap/archive/](roadmap/archive/); lo pendiente (observabilidad avanzada, hardening CI, despliegue GCP) sigue en [roadmap/](roadmap/README.md).
