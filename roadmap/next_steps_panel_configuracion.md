# Next Steps — Panel de configuración

## Objetivo

Centro de administración de la plataforma, accesible **solo** con la contraseña explícita `ADMIN_PANEL_PASSWORD` del `.env` (step-up sobre la sesión de un usuario con `config:access`; mecánica en el doc de autenticación). Desde aquí se gestionan: **cuentas de WhatsApp y sus credenciales**, **webhooks hacia n8n**, **API keys**, **logs**, **usuarios** y **configuración general**.

Todas las rutas de backend de esta sección viven bajo `/api/v1/config/**`, protegidas por `ConfigPanelGuard` (sesión + permiso + step-up vigente de 15 min).

## Secciones del panel

### 1. Cuentas de WhatsApp (`accounts:manage`)

- Lista de cuentas con estado (`active` / `paused` / `error`), número, WABA, último webhook recibido, salud del token.
- **Alta/edición**: nombre interno, `waba_id`, `phone_number_id`, `display_phone_number`, y el **access token** (System User permanente). El token:
  - se envía una sola vez por HTTPS, se cifra con AES-256-GCM (`CREDENTIALS_ENCRYPTION_KEY`) y se guarda como `access_token_ciphertext`;
  - **nunca vuelve a mostrarse**: la UI muestra `EAAG…○○○○` (prefijo + máscara) y solo permite *reemplazar*;
  - "Probar conexión" valida contra la Graph API antes de guardar y actualiza `status`.
- **Configuración n8n por cuenta**: `n8n_inbound_webhook_url` + secreto HMAC (generable desde la UI, cifrado en DB, visible solo al crearlo), toggle `forwardStatuses`, botón **"enviar evento de prueba"**.
- Pausar cuenta (`paused`): deja de reenviar a n8n y de aceptar envíos salientes; sigue persistiendo lo entrante.
- Rotación de token: reemplazo atómico + `event_logs` (`account.token_rotated`), sin downtime.

```
GET    /api/v1/config/accounts
POST   /api/v1/config/accounts
PATCH  /api/v1/config/accounts/:id            → campos generales / token (write-only) / webhook n8n
POST   /api/v1/config/accounts/:id/test        → prueba de conexión Graph API
POST   /api/v1/config/accounts/:id/test-webhook→ evento sintético al webhook n8n
DELETE /api/v1/config/accounts/:id             → solo si no tiene mensajes; si tiene, solo 'paused'
```

### 2. API keys para n8n (`api_keys:manage`)

- Crear key con nombre y scopes (`hooks:messages`, `hooks:leads`); el valor completo (`ck_live_…`) se muestra **una única vez**; en DB queda hash + prefijo.
- Lista con `last_used_at`, scopes, estado; revocación inmediata (deja de autenticar en el próximo request).

### 3. Visor de logs (`logs:read`)

- **Auditoría** (`event_logs`): tabla filtrable por actor, acción, entidad, rango de fechas; detalle JSON expandible. Aquí se ven logins, cambios de configuración, movimientos de leads por webhook, rotaciones de token.
- **Entregas de webhooks** (`webhook_deliveries`): por cuenta, con status HTTP, intentos, próximo reintento; botón **re-entregar** y **re-entregar todos los fallidos**.
- **Mensajes fallidos**: mensajes con `status='failed'` + `error_detail` de Meta; botón re-encolar.
- Enlace directo a Cloud Logging (filtro pre-armado por `trace_id`) para el detalle técnico.

### 4. Usuarios y roles (`users:manage`)

Alta con invitación, cambio de rol, permisos individuales (checkboxes sobre el set del doc de autenticación), desactivación, cierre remoto de sesiones.

### 5. Configuración general (`config:access`)

Tabla `settings` editable con validación por clave: zona horaria de la UI, TTL del step-up, días para autocierre de conversaciones inactivas, política de asignación automática, límites de tamaño de adjuntos.

## UI

Sección `/settings` de la SPA con navegación lateral (Cuentas, API Keys, Logs, Usuarios, General). Al entrar sin step-up vigente → modal de contraseña del panel (una sola contraseña, sin usuario — es la del `.env`). Cuenta atrás visible del step-up con botón "extender". Toda acción destructiva (revocar key, pausar cuenta, desactivar usuario) pide confirmación tipeando el nombre del recurso.

## Pasos de desarrollo

- [ ] Dependencia `require_config_panel` aplicada a todo el árbol `/api/v1/config/**` (test que falla si una ruta config no la tiene).
- [ ] Servicio de cifrado AES-256-GCM (`app/core/crypto.py`) con `key_version` para rotación futura de la clave maestra.
- [ ] CRUD de cuentas con token write-only + máscara + prueba de conexión.
- [ ] Generador/gestor de API keys (mostrar-una-vez, hash en DB, scopes).
- [ ] Visores: auditoría, entregas de webhooks (con re-entrega), mensajes fallidos (con re-encolado).
- [ ] CRUD de usuarios + invitaciones (definido en doc de autenticación, la UI vive aquí).
- [ ] Editor de `settings` con schema de validación por clave.
- [ ] Modal de step-up + interceptor global de `403 CONFIG_STEPUP_REQUIRED` en la SPA.
- [ ] Auditar **todas** las escrituras del panel en `event_logs` con diff de campos no sensibles (nunca loguear tokens/secretos, ni siquiera cifrados).

## Buenas prácticas

- Credenciales **write-only**: no existe ningún endpoint que devuelva un token o secreto guardado; solo reemplazo. Elimina exfiltración vía panel comprometido.
- Confirmaciones destructivas explícitas + auditoría con actor y `trace_id`.
- El panel es el único camino de escritura de configuración: nada de editar `settings` o cuentas por SQL manual en producción (los cambios quedarían sin auditar).
- Cambios de configuración toman efecto sin redeploy (lectura de `settings`/cuentas con cache TTL 60 s), salvo las env vars por diseño (`ADMIN_PANEL_PASSWORD`, claves de cifrado).

## Criterios de aceptación

- Sin step-up vigente, ningún dato de `/api/v1/config/**` es accesible ni siquiera para un admin logueado; con step-up expira a los 15 min y la UI lo re-solicita sin perder el trabajo en formularios.
- Un token de WhatsApp guardado no puede recuperarse por ninguna vía (API, UI, logs); solo reemplazarse.
- Alta completa de una cuenta nueva (credenciales + webhook n8n + prueba) en menos de 5 minutos sin tocar código ni consola de GCP.
- Toda acción del panel aparece en la auditoría con quién, qué y cuándo.
