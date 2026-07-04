# Next Steps — Leads y embudo configurable

## Objetivo

Registrar leads desde tres orígenes (manual en el CRM, webhook de n8n, botón "crear lead" en un chat), gestionarlos en un **embudo configurable** (pipelines con etapas ordenadas, editables desde la UI), con vista kanban y lista, historial de movimientos y métricas de conversión.

## Modelo

Definido en el doc de base de datos: `pipelines`, `pipeline_stages` (ordenadas por `position`, con etapas terminales `won`/`lost`), `leads` (con `external_key` para upsert desde n8n, `attributes` JSONB para campos custom), `lead_stage_events` (historial), `notes` (compartidas con el chat).

Reglas:
- Debe existir siempre exactamente **un pipeline por defecto** (`is_default`), usado cuando el webhook no especifica pipeline. El seed lo crea: *Nuevo → Contactado → Calificado → Propuesta → Ganado / Perdido*.
- Un lead pertenece a un pipeline y una etapa de ese pipeline (validar coherencia al mover).
- Un contacto puede tener múltiples leads históricos, pero **solo un lead activo por conversación** (activo = etapa no terminal y no borrado). El webhook y la UI reutilizan el activo antes de crear otro.

## Configuración del embudo (desde la UI, permiso `pipelines:manage`)

- Crear/renombrar/archivar pipelines; marcar el default.
- Agregar/renombrar/reordenar (drag & drop)/colorear etapas; marcar terminales con outcome.
- **Reordenar** usa `position` con actualización transaccional.
- **Eliminar etapa con leads** exige elegir etapa destino (la API recibe `moveLeadsToStageId`); nunca se borran leads por borrar una etapa.
- Cambios de estructura → `event_logs` (quién agregó/quitó etapas).

## API

```
# Pipelines y etapas
GET    /api/v1/pipelines                         → con etapas ordenadas y conteo de leads
POST   /api/v1/pipelines
PATCH  /api/v1/pipelines/:id                     → nombre, is_default
POST   /api/v1/pipelines/:id/stages
PATCH  /api/v1/stages/:id                        → nombre, color, position, is_terminal, outcome
DELETE /api/v1/stages/:id?moveLeadsToStageId=…

# Leads
GET    /api/v1/leads?pipelineId=&stageId=&ownerUserId=&q=&source=&createdFrom=&createdTo=
       &cursor=&limit=50                         → lista/kanban
POST   /api/v1/leads                             → creación manual (o desde un chat)
GET    /api/v1/leads/:id                         → detalle + contacto + conversación + notas + historial
PATCH  /api/v1/leads/:id                         → título, valor, dueño, attributes
PATCH  /api/v1/leads/:id/stage                   → { stageId } (registra lead_stage_events)
DELETE /api/v1/leads/:id                         → borrado lógico (permiso leads:delete)
GET    /api/v1/leads/:id/notes  /  POST idem     → mismas notas que el chat
GET    /api/v1/pipelines/:id/metrics?from=&to=   → conversión por etapa, tiempo medio por etapa,
                                                   valor total por etapa, ganados/perdidos
```

El webhook `POST /api/v1/hooks/n8n/leads` (contrato completo en el doc de webhooks) converge en el **mismo** `LeadsService.upsert()` que usa esta API — una sola implementación de reglas de negocio.

## UI

- **Kanban** por pipeline: columnas = etapas (color y suma de valor por columna), tarjetas con contacto, título, valor, dueño, tiempo en etapa, badge de origen (manual/n8n). Drag & drop entre columnas → `PATCH /stage` optimista.
- **Vista lista**: tabla con orden y filtros (etapa, dueño, origen, rango de fechas, búsqueda), export CSV.
- **Detalle de lead**: datos editables, historial de etapas (timeline), notas internas (crear/editar), acceso directo al chat asociado y viceversa.
- **Editor de embudo** dentro de Configuración → Pipelines (o sección propia con permiso `pipelines:manage`).
- **Métricas**: funnel de conversión por etapa y tiempos medios, filtrable por rango de fechas y dueño.

## Pasos de desarrollo

- [ ] `LeadsService.upsert()` transaccional único (usado por API manual y webhook) con re-asociación de notas huérfanas de la conversación.
- [ ] CRUD de pipelines/etapas con reordenamiento transaccional y protección de la etapa con leads.
- [ ] Registro automático en `lead_stage_events` en todo cambio de etapa (servicio, no trigger, para capturar el actor).
- [ ] Endpoints de listado con paginación por cursor y agregados por columna para el kanban (una query `GROUP BY stage_id`, no N+1).
- [ ] Kanban con drag & drop (dnd-kit) + actualización optimista + rollback en error.
- [ ] Detalle de lead con timeline (merge de `lead_stage_events` + notas + creación).
- [ ] Métricas de conversión (CTE sobre `lead_stage_events`) + endpoint + gráfico funnel.
- [ ] Export CSV en streaming (no cargar todo en memoria).
- [ ] Tests: mover lead entre pipelines (prohibido — 422), etapa de otro pipeline (422), doble lead activo por conversación (bloqueado), upsert concurrente con mismo `external_key` (unicidad).

## Buenas prácticas

- Todos los movimientos de etapa pasan por un único método de servicio → historial y auditoría completos garantizados.
- `attributes` JSONB es para datos de n8n/campañas, **no** un cajón para features del core: si un campo se consulta/filtra con frecuencia, promoverlo a columna en una migración.
- Métricas calculadas sobre `lead_stage_events` (hechos inmutables), no sobre el estado actual — permite responder "cuántos pasaron por Calificado en junio".
- Valores monetarios `NUMERIC(14,2)` + `currency`; nunca sumar monedas distintas en la UI sin agrupar.

## Criterios de aceptación

- Un admin agrega la etapa "Demo agendada" entre dos existentes y las tarjetas kanban la reflejan sin recargar; el webhook puede referenciarla por `stageName` inmediatamente.
- Arrastrar un lead a "Ganado" lo saca de los leads activos, permite crear un lead nuevo en esa conversación y queda en las métricas del período.
- Un lead creado por n8n con `external_key` y luego editado manualmente conserva ambos cambios (el próximo upsert de n8n no pisa campos que no envía).
- Las métricas de conversión de un pipeline con 10k leads responden < 1 s.
