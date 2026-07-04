# Next Steps — Despliegue en Google Cloud, CI/CD y escalabilidad

## Objetivo

Infraestructura reproducible (Terraform), pipeline de CI/CD por commit, entornos separados y un camino de escalabilidad claro: empezar simple (2 servicios Cloud Run + Cloud SQL) y saber exactamente qué tocar cuando crezca el volumen.

## Entornos

| Entorno | Proyecto GCP | Uso |
|---|---|---|
| `dev` (local) | — | docker-compose: PostgreSQL 16, fake-gcs-server, n8n local, túnel para webhooks de Meta |
| `staging` | `crm-n8n-staging` | Igual a prod en pequeño (db-f1-micro, min-instances=0), número de WhatsApp de prueba |
| `prod` | `crm-n8n-prod` | Producción |

Proyectos GCP separados (no solo prefijos): aislamiento total de IAM, secretos, cuotas y facturación.

## Infraestructura (Terraform en `/infra`)

- **Cloud Run `api`**: contenedor FastAPI (Uvicorn). Prod: `min-instances=1` (webhooks de Meta sin cold start), `max-instances=10`, concurrency 80, CPU 1 / 512 MB–1 GB, timeout 60 s. Health checks: startup contra `/api/v1/health/ready`, liveness contra `/api/v1/health`.
- **Cloud Run `web`**: nginx con la SPA compilada (o Firebase Hosting como alternativa más barata para estáticos). Escala a cero.
- **Cloud SQL PostgreSQL 16**: prod `db-custom-2-7680` (2 vCPU / 7,5 GB) con HA regional, IP privada, backups diarios + PITR 7 días, ventana de mantenimiento definida. Staging: instancia mínima sin HA.
- **Cloud Tasks**: colas `outbound-whatsapp` (rate limit por debajo del tier de Meta, p.ej. `maxDispatchesPerSecond=10` inicial) y `outbound-n8n` (`maxAttempts=5`, backoff 60 s→6 h). Ambas invocan endpoints `/internal/**` con OIDC.
- **Cloud Storage**: bucket de adjuntos (uniform access, versioning, clase Standard; lifecycle a Nearline > 90 días), bucket de backups/exports.
- **Secret Manager**: los 6 secretos de plataforma (doc de seguridad), con versiones.
- **Serverless VPC Access connector**: para hablar con Cloud SQL por IP privada (y Memorystore cuando llegue).
- **Dominios**: `api.<dominio>` → Cloud Run api; `app.<dominio>` → web. Certificados gestionados.
- **Artifact Registry**: repositorio Docker con escaneo de vulnerabilidades activado.

## CI/CD (GitHub Actions)

```
PR:            lint → typecheck → tests unitarios → tests integración (Postgres service) → build
merge a main:  todo lo anterior → build & push imágenes (tag = SHA) → deploy a STAGING
                → migraciones → smoke tests E2E contra staging
release (tag): deploy a PROD con aprobación manual (environment protection rule)
```

Detalles clave:

- **Workload Identity Federation** para autenticar GitHub Actions en GCP — sin claves de service account exportadas.
- **Migraciones**: paso previo al deploy (`alembic upgrade head`) ejecutado como Cloud Run Job con el usuario de DB de migraciones. Regla: migraciones **compatibles hacia atrás** (expand/contract) — el código viejo debe funcionar durante el rollout.
- **Rollback**: `gcloud run services update-traffic --to-revisions=PREV=100`; como las migraciones son backward-compatible, revertir código no exige revertir DB.
- Deploy con tráfico gradual en prod (`--tag canary` al 10% durante 10 min con verificación de tasa de 5xx, luego 100%) — opcional en v1, documentado desde ya.
- Imágenes: multi-stage build con `uv` (resolver deps → runtime `python:3.12-slim`); imagen final < 300 MB, usuario no root.

## Escalabilidad — plan por etapas

**Etapa 1 (lanzamiento, < ~50k mensajes/mes)** — lo descrito arriba. `min-instances=1` para api. WebSockets funcionan con 1–2 instancias sin adapter (session affinity de Cloud Run activada).

**Etapa 2 (crecimiento, ~50k–500k mensajes/mes)**
- **Memorystore (Redis)**: pub/sub para WebSockets con N instancias, rate limiting distribuido y cache de tokens/settings.
- Separar **worker** en servicio Cloud Run propio (`api-worker`, ingress internal) que recibe las invocaciones de Cloud Tasks — los picos de cola dejan de competir con el tráfico de usuarios.
- Réplica de lectura de Cloud SQL para búsquedas/métricas/exports.
- PgBouncer (o el pooling gestionado de Cloud SQL) si las conexiones se vuelven límite: Cloud Run escala instancias × pool.

**Etapa 3 (alto volumen)**
- Ingesta de webhooks de Meta → **Pub/Sub** (el endpoint solo valida firma y publica): absorbe cualquier pico y desacopla por completo.
- Particionado por rango de fechas de `messages` y `event_logs` (umbral ~10M filas, ya previsto en el doc de base de datos).
- Archivado de conversaciones frías a BigQuery para analítica histórica; la DB operativa mantiene una ventana caliente.

Lo importante: **nada de la etapa 2/3 requiere reescritura** — colas, módulos y contratos ya separan los componentes; solo se mueven a infraestructura dedicada.

## Costes estimados (prod, etapa 1, aprox.)

| Recurso | Estimado/mes |
|---|---|
| Cloud Run api (1 instancia caliente) | ~25–40 USD |
| Cloud SQL (2 vCPU HA + storage) | ~120–150 USD (sin HA: ~60–70) |
| Cloud Storage + Tasks + Secret Manager + Logging | ~10–20 USD |
| **Total orden de magnitud** | **~60–200 USD/mes** según HA y tráfico |

(Meta cobra aparte las conversaciones de WhatsApp Business.)

## Pasos de desarrollo

- [ ] `docker-compose.yml` de desarrollo (PostgreSQL, fake-gcs-server, n8n) + script `make dev`.
- [ ] Dockerfiles multi-stage de api y web; build reproducible con lockfile.
- [ ] Terraform base: proyectos, APIs habilitadas, Cloud SQL, buckets, colas, secretos, service accounts con IAM mínimo, dominios.
- [ ] Workflow de CI (PR) con Postgres como service container para tests de integración.
- [ ] Workflow de CD a staging con migraciones como paso separado + smoke tests.
- [ ] Workflow de release a prod con aprobación manual y rollback documentado.
- [ ] Configurar Workload Identity Federation (sin claves JSON).
- [ ] Session affinity + prueba de WebSockets con 2 instancias; decidir si Memorystore entra en v1.
- [ ] Prueba de carga (k6): 100 webhooks/s de Meta simulados y 20 envíos/s — validar latencias y autoscaling antes del go-live.
- [ ] Runbook de despliegue y rollback en `/docs/runbooks/`.

## Buenas prácticas

- Infra 100% en Terraform: nada creado a mano en la consola (lo manual no sobrevive a un disaster recovery).
- Un artefacto, muchos entornos: la misma imagen (por SHA) va a staging y prod; solo cambia configuración/secretos.
- Migraciones expand/contract siempre: agregar columna nullable → deploy → backfill → hacer NOT NULL en la migración siguiente.
- Presupuestos y alertas de facturación en ambos proyectos GCP desde el día 1.
- Probar el runbook de restauración de backup en staging trimestralmente.

## Criterios de aceptación

- Un `git tag` lleva a producción una versión completa (api+web+migraciones) sin pasos manuales fuera de la aprobación.
- Un rollback de código a la revisión anterior se completa en < 5 min sin tocar la base de datos.
- Con 100 webhooks/s sostenidos durante 10 min, p95 del endpoint de Meta < 2 s y cero mensajes perdidos.
- Recrear staging desde cero con Terraform + seed toma < 1 hora y queda funcional.
