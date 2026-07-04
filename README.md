# CRM WhatsApp Business ↔ n8n

Plataforma en Google Cloud que actúa como intermediario entre la **WhatsApp Business Cloud API** (Meta) y **n8n**: persiste todos los mensajes, adjuntos y conversaciones en PostgreSQL y funciona como CRM (leads con embudo configurable, notas internas, roles y panel de configuración protegido).

- **Documentación de diseño y plan de desarrollo**: [roadmap/](roadmap/README.md)
- **Backend**: FastAPI (Python 3.12) + SQLAlchemy 2.0 async + PostgreSQL 16 → [apps/api/](apps/api/)
- **Frontend** (fase 3): React + Vite → `apps/web/`

## Quickstart con Docker (recomendado)

Requisitos: Docker Desktop.

```bash
# 1. Configurar entorno — UN solo .env en la raíz (solo la primera vez)
cp .env.example .env
# completar los valores (cada variable tiene instrucciones en el archivo);
# la clave de cifrado se genera con:
#   python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"

# 2. Levantar todo: DB → migraciones + seed (automático) → API → frontend
docker compose up -d --build

# La API key para n8n la imprime el seed (una sola vez):
docker compose logs migrate
```

> **n8n es externo al stack**: la URL del webhook hacia tu n8n se define en
> `N8N_WEBHOOK_BASE` del `.env` (y por cuenta, desde el panel en P4).

- **Frontend**: http://localhost:8000 (nginx proxea `/api` al backend por la red interna)
- **API directa**: http://localhost:8080 · docs OpenAPI en http://localhost:8080/api/docs
- Health: `GET /api/v1/health` · Readiness: `GET /api/v1/health/ready`
- Webhook de Meta: `GET|POST /api/v1/whatsapp/webhook` (usar túnel `cloudflared`/`ngrok` hacia el 8080)
- Hooks para n8n: `POST /api/v1/hooks/n8n/messages` · `POST /api/v1/hooks/n8n/leads` (auth: `Authorization: Bearer <api_key>`)

Las migraciones corren solas en el servicio `migrate` (`alembic upgrade head` + seed idempotente); la API arranca recién cuando terminan bien.

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

Ver fases y prioridades en [roadmap/README.md](roadmap/README.md). Implementado hasta ahora: fundaciones (P0), núcleo de mensajería WhatsApp (P1) y puente n8n (P2). Pendiente: autenticación/CRM UI (P3), panel de configuración (P4), despliegue GCP (P5).
