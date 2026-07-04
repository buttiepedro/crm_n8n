# Next Steps — Autenticación, roles y permisos

## Objetivo

Inicio de sesión propio con roles y permisos finos, sesiones seguras server-side, y el mecanismo de **step-up** que protege el panel de configuración con la contraseña explícita `ADMIN_PANEL_PASSWORD` definida en `.env` (requisito del proyecto: ni siquiera un admin logueado entra al panel sin esa contraseña).

## Modelo de acceso

### Roles (columna `users.role`)

| Rol | Descripción |
|---|---|
| `admin` | Todo, incluida la candidatura al panel de configuración (con step-up) y gestión de usuarios |
| `supervisor` | Todas las conversaciones y leads, reasignación, embudo, reportes; sin panel de configuración |
| `agent` | Conversaciones/leads asignados o sin asignar; enviar mensajes; crear notas; sin configuración |

### Permisos (strings estables, evaluados por un `PermissionsGuard`)

```
conversations:read:any | conversations:read:assigned
conversations:send | conversations:assign | conversations:close
leads:read | leads:write | leads:delete | leads:move_stage
notes:write | notes:edit:own | notes:edit:any
pipelines:manage
users:manage
config:access          ← además exige step-up vigente
logs:read
accounts:manage        ← cuentas WhatsApp (implica config:access)
api_keys:manage
```

Cada rol expande a un set de permisos por defecto (mapa en código, versionado, en `app/modules/auth/permissions.py`); `user_permissions` permite otorgar/revocar permisos puntuales por usuario sin cambiar el rol. Decisión final = permisos del rol ∪ concedidos − revocados. Un `PermissionsGuard` equivale aquí a la dependencia `require_permissions()`.

Uso en FastAPI (dependencia reutilizable):

```python
@router.patch(
    "/leads/{lead_id}/stage",
    dependencies=[require_permissions("leads:move_stage")],
)
async def move_stage(lead_id: UUID, body: MoveStageIn, ...): ...
```

## Sesiones

- Login `POST /api/v1/auth/login` (email + contraseña). Hash **argon2id** con `argon2-cffi` (memoria 64 MB, iteraciones según benchmark del contenedor; objetivo ~100 ms).
- Éxito → crear fila en `sessions` con token aleatorio (256 bits); al navegador viaja en **cookie httpOnly, Secure, SameSite=Lax**, firmada con `SESSION_SECRET`. En DB se guarda solo el **sha256** del token.
- Expiración: 12 h de vida + expiración deslizante por inactividad de 60 min (configurable en `settings`).
- `POST /api/v1/auth/logout` revoca la sesión (delete). "Cerrar sesión en todos los dispositivos" disponible para el propio usuario y para admins sobre terceros.
- `GET /api/v1/auth/me` → usuario, rol, permisos expandidos, y si el step-up de configuración está vigente (para que la SPA arme el menú).
- Anti-brute-force: rate limit por IP+email (5 intentos/min, backoff progresivo), respuesta idéntica para "usuario no existe" y "contraseña incorrecta", registro en `event_logs` de intentos fallidos.
- WebSocket: el handshake valida la misma cookie de sesión; sesión revocada → desconexión inmediata.

## Step-up del panel de configuración (`ADMIN_PANEL_PASSWORD`)

Requisito literal: el panel de configuración solo se accede con una contraseña explícita definida en `.env`.

- `POST /api/v1/auth/config-panel` con `{ "password": "…" }`. Solo usuarios con `config:access` pueden intentarlo.
- Comparación en **tiempo constante** (`hmac.compare_digest`) contra `ADMIN_PANEL_PASSWORD`. En producción, la variable proviene de Secret Manager.
- Éxito → se estampa `sessions.config_panel_until = now() + 15 min` (ventana corta, renovable). Fallos limitados a 3/min y auditados.
- Una dependencia `require_config_panel` protege **todas** las rutas `/api/v1/config/**` (cuentas WhatsApp, API keys, webhooks, settings, logs de configuración): exige sesión válida + permiso + `config_panel_until > now()`. Expirado → `403 CONFIG_STEPUP_REQUIRED` y la SPA vuelve a pedir la contraseña.
- La contraseña **nunca** se persiste ni se loguea; no existe endpoint que la devuelva.

## Flujo de administración de usuarios

- Solo `users:manage` (admins) crea/edita/desactiva usuarios. Sin registro público.
- Alta: el admin define email y rol; el sistema genera un enlace de establecimiento de contraseña de un solo uso (token 30 min). Evita que el admin conozca contraseñas ajenas.
- Desactivación (`is_active=false`) revoca todas las sesiones del usuario en la misma transacción.
- Cambio de contraseña propio requiere la contraseña actual y revoca las demás sesiones.

## Pasos de desarrollo

- [ ] Módulo `auth`: modelos SQLAlchemy (`users`, `sessions`, `user_permissions`), servicio argon2id (`argon2-cffi`), cookie firmada (`itsdangerous`).
- [ ] Dependencia de sesión aplicada por router (rutas públicas explícitas: login, webhooks de Meta, hooks n8n que usan su propia autenticación por API key).
- [ ] Mapa rol→permisos en `app/modules/auth/permissions.py` + dependencia `require_permissions()`.
- [ ] Step-up: endpoint, dependencia `require_config_panel`, TTL configurable.
- [ ] Rate limiting de login y step-up (`slowapi` o middleware propio con storage en DB o Memorystore).
- [ ] CRUD de usuarios + flujo de invitación con token de un solo uso.
- [ ] Auditoría: login OK/fallido, logout, step-up OK/fallido, cambios de rol/permisos → `event_logs`.
- [ ] Frontend: pantalla de login, guard de rutas por permiso, modal de step-up al entrar a Configuración, manejo de `403 CONFIG_STEPUP_REQUIRED` global.
- [ ] Tests: matriz rol×endpoint (tabla de casos que falla si se agrega un endpoint sin anotar permisos), expiración de step-up, timing-safe compare.

## Buenas prácticas

- Denegar por defecto: endpoint sin dependencia de permisos declarada → error en arranque (test estático sobre las rutas registradas), no "abierto".
- Autorización **siempre en el backend**; el frontend solo oculta UI.
- No usar el rol para decisiones en código de negocio: usar permisos (los roles son solo agrupaciones editables).
- Sesiones en DB (no JWT stateless) porque la revocación inmediata importa más que evitar un lookup — y el lookup es una PK.
- Preparado para 2FA (TOTP) en v2: columna reservada en `users`, no implementar aún.

## Criterios de aceptación

- Un `agent` no puede: ver conversaciones de otros (si así se configura), acceder a `/api/v1/config/**` (ni con la contraseña del panel, porque le falta `config:access`), gestionar usuarios.
- Un `admin` sin step-up vigente recibe `403 CONFIG_STEPUP_REQUIRED` en todas las rutas de configuración; tras ingresar `ADMIN_PANEL_PASSWORD` accede por 15 min.
- Cambiar `ADMIN_PANEL_PASSWORD` en el entorno y redeplegar invalida el acceso con la contraseña anterior (no hay estado persistido de la contraseña).
- 6 intentos de login fallidos en un minuto → `429` y evento de auditoría visible en el panel.
