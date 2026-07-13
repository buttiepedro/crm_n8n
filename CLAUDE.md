# Notas del proyecto

## Historial de movimientos en el modal de lead (removido)

Se eliminó la sección "Recorrido" (timeline de cambios de etapa) del modal de detalle de lead
(`apps/web/src/pages/Leads.tsx`, componente `LeadDetailModal`).

Razón: molestaba más de lo que ayudaba (ruido visual en el modal, poco valor para el usuario).

El dato subyacente NO se borró: la tabla `lead_stage_events` (backend, `apps/api/app/db/models/crm.py`)
sigue siendo la base de las métricas de conversión y el endpoint `GET /leads/{id}` sigue devolviendo
`history` en la respuesta. Solo se quitó el render en el frontend.
