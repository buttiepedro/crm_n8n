# CRM WhatsApp Business ↔ n8n

Plataforma en Google Cloud que actúa como intermediario entre la **WhatsApp Business Cloud API** (Meta) y **n8n**: persiste todos los mensajes, adjuntos y conversaciones en PostgreSQL y funciona como CRM (leads con embudo configurable, notas internas, roles y panel de configuración protegido).

- **Documentación de diseño y plan de desarrollo**: [roadmap/](roadmap/README.md)
- **Backend**: FastAPI (Python 3.12) + SQLAlchemy 2.0 async + PostgreSQL 16 → [apps/api/](apps/api/)
- **Frontend** (fase 3): React + Vite → `apps/web/`

## Quickstart (desarrollo local)

Requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker (para PostgreSQL y n8n).

```bash
# 1. Levantar PostgreSQL (y opcionalmente n8n)
docker compose up -d db
docker compose --profile n8n up -d      # opcional: n8n local en http://localhost:5678

# 2. Instalar dependencias del backend
cd apps/api
uv sync

# 3. Configurar entorno
cp .env.example .env                     # completar valores (ver comentarios)

# 4. Crear el esquema de base de datos
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head

# 5. Datos de desarrollo (pipeline por defecto, cuenta de prueba, API key para n8n)
uv run python scripts/seed.py

# 6. Levantar la API
uv run uvicorn app.main:app --reload --port 8080
```

- API docs (OpenAPI): http://localhost:8080/api/docs
- Health: `GET /api/v1/health` · Readiness: `GET /api/v1/health/ready`
- Webhook de Meta: `GET|POST /api/v1/whatsapp/webhook` (usar túnel `cloudflared`/`ngrok` para pruebas con Meta)
- Hooks para n8n: `POST /api/v1/hooks/n8n/messages` · `POST /api/v1/hooks/n8n/leads` (auth: `Authorization: Bearer <api_key>`)

## Tests y verificación sin base de datos

```bash
cd apps/api
uv run pytest                            # tests unitarios
uv run python scripts/generate_ddl.py    # emite el DDL PostgreSQL desde los modelos
```

## Estado del desarrollo

Ver fases y prioridades en [roadmap/README.md](roadmap/README.md). Implementado hasta ahora: fundaciones (P0), núcleo de mensajería WhatsApp (P1) y puente n8n (P2). Pendiente: autenticación/CRM UI (P3), panel de configuración (P4), despliegue GCP (P5).
