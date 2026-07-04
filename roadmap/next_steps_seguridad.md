# Next Steps — Seguridad

## Objetivo

Prácticas de seguridad aplicadas **desde el primer commit**: gestión de secretos y credenciales, cifrado, validación de todos los bordes, hardening de la aplicación y de la infraestructura GCP. Este documento es transversal; los demás docs referencian sus mecanismos.

## Gestión de secretos y credenciales

### Secretos de plataforma (estáticos, por entorno)

| Secreto | Uso | Dónde vive |
|---|---|---|
| `DATABASE_URL` | Conexión Cloud SQL | Secret Manager → env var en Cloud Run |
| `SESSION_SECRET` | Firma de cookies | Secret Manager |
| `ADMIN_PANEL_PASSWORD` | Step-up del panel de configuración | Secret Manager (local: `.env`) |
| `CREDENTIALS_ENCRYPTION_KEY` | Clave maestra AES-256-GCM | Secret Manager, **con versiones** |
| `WHATSAPP_APP_SECRET` | Verificación de firma de webhooks de Meta | Secret Manager |
| `WHATSAPP_VERIFY_TOKEN` | Handshake del webhook | Secret Manager |

Reglas: `.env` solo para desarrollo local, **en `.gitignore` desde el commit inicial**, con `.env.example` documentando cada variable sin valores reales. En producción no existe archivo `.env`: Cloud Run monta secretos por referencia. Rotación: todos los secretos deben poder rotarse sin pérdida de datos (sesiones se invalidan — aceptable; clave de cifrado — ver rotación abajo).

### Credenciales dinámicas (creadas desde el panel)

- **Tokens de WhatsApp y secretos HMAC de webhooks**: cifrados con **AES-256-GCM** antes de persistir. Formato almacenado: `key_version (1B) || IV (12B) || authTag (16B) || ciphertext`. AAD = id de la cuenta (liga el ciphertext a su fila: no se puede trasplantar a otra cuenta).
- **Rotación de la clave maestra**: nueva versión en Secret Manager → job que descifra con vN y recifra con vN+1 (por eso `key_version` en cada fila) → deshabilitar vN.
- **API keys de n8n**: aleatorias (256 bits), formato `ck_live_<base62>`; en DB solo `sha256(key)` + prefijo visible. Comparación por hash-lookup (tiempo constante por naturaleza).
- **Contraseñas de usuarios**: argon2id con `argon2-cffi` (ver doc de autenticación). La `ADMIN_PANEL_PASSWORD` se compara con `hmac.compare_digest` (tiempo constante) y jamás se persiste.
- Prohibición absoluta de secretos en: logs, `event_logs`, respuestas de API, mensajes de error, URLs, código y repo. Lint de CI con detector de secretos (gitleaks) bloqueante.

## Validación de bordes (todo input es hostil)

| Borde | Mecanismo |
|---|---|
| Webhook de Meta | Firma `X-Hub-Signature-256` sobre raw body, obligatoria |
| Hooks de n8n | API key con scope + HMAC opcional + rate limit + `Idempotency-Key` |
| API del CRM | Sesión (cookie httpOnly) + `PermissionsGuard` + validación de DTO estricta (whitelist: campos desconocidos → 400) |
| Panel de configuración | Todo lo anterior + step-up `ADMIN_PANEL_PASSWORD` |
| Workers de Cloud Tasks | Endpoints `/internal/**` solo aceptan OIDC de la service account de la cola (no expuestos a Internet vía checkeo de audience) |
| WebSocket | Misma cookie de sesión + autorización por room |
| Media saliente por URL (n8n) | Allowlist de esquemas https, resolución DNS segura (bloquear IPs privadas — SSRF), límite de tamaño y timeout |

## Hardening de aplicación

- **Cabeceras**: middleware de seguridad propio o lib `secure` — CSP estricta para la SPA (sin `unsafe-inline`), HSTS, `X-Content-Type-Options`, `frame-ancestors 'none'`.
- **CORS**: allowlist explícita del dominio de la SPA; los webhooks no necesitan CORS (server-to-server).
- **CSRF**: cookies `SameSite=Lax` + verificación de `Origin` en mutaciones (defensa en profundidad).
- **XSS**: React escapa por defecto; prohibido `dangerouslySetInnerHTML`; el cuerpo de mensajes de WhatsApp se renderiza siempre como texto plano.
- **SQLi**: SQLAlchemy parametriza; prohibido `text()` con interpolación de strings (regla de lint / bandit).
- **Subidas de archivos**: validar mime real (magic bytes, no extensión), límite de tamaño, GCS privado, URLs firmadas de 15 min, nunca servir con `Content-Disposition: inline` tipos peligrosos (html/svg → attachment).
- **Rate limiting global** por IP y por sesión además de los específicos (login, hooks).
- **Dependencias**: lockfile obligatorio (`uv.lock`), `pip-audit` + Renovate/Dependabot en CI, imágenes Docker slim escaneadas (Artifact Registry scanning).
- Contenedor: usuario no-root, filesystem read-only, sin shell en imagen final.

## Hardening de infraestructura GCP

- **Cloud SQL**: solo IP privada, conexión por conector con IAM; usuario de app sin DDL; usuario de migraciones separado.
- **Service accounts dedicadas por servicio** (api, web, CI) con mínimo privilegio: la SA de la api solo `cloudsql.client`, `secretmanager.secretAccessor` (secretos puntuales, no wildcard), `storage.objectAdmin` del bucket de adjuntos, `cloudtasks.enqueuer`.
- **Cloud Run**: ingress "all" solo para la api (recibe webhooks); si se separa un servicio interno de workers → ingress internal. Egress por VPC connector si se fija IP para allowlists de terceros.
- Bucket GCS: uniform access, sin ACLs públicas, retención y versioning activados.
- **Auditoría GCP**: Admin Activity logs habilitados; alertas sobre cambios IAM y accesos a secretos.
- Backups Cloud SQL diarios + PITR; simulacro de restauración documentado antes del go-live.

## Privacidad de datos (mensajes de clientes)

- Los cuerpos de mensajes **no** van a logs técnicos (solo ids y metadatos); Cloud Logging tiene retención limitada (30 días).
- Acceso a conversaciones gobernado por permisos; todo acceso administrativo queda auditado.
- Definir política de retención/borrado de datos de contacto (soporte futuro a solicitudes de borrado) — al menos documentada en v1.
- TLS en todo: Cloud Run lo da gestionado; verificación de certificados activa en llamadas salientes (no deshabilitar nunca `rejectUnauthorized`).

## Pasos de desarrollo

- [ ] `.gitignore` con `.env*` + `.env.example` completo — commit inicial.
- [ ] Módulo `common/crypto` (AES-256-GCM con AAD y versionado de clave) con tests de vectores conocidos.
- [ ] Validación de env vars al arranque (pydantic-settings) — falla rápido y claro.
- [ ] Guards: firma Meta, API key+scope, OIDC de Cloud Tasks, step-up. Tests negativos para cada uno.
- [ ] Middleware de cabeceras de seguridad + CORS + verificación de Origin + rate limit global.
- [ ] Protección SSRF en descargas de `mediaUrl` de n8n.
- [ ] gitleaks + `pip-audit` + escaneo de imagen en CI (bloqueantes).
- [ ] Terraform/scripts de IAM de mínimo privilegio por service account.
- [ ] Checklist OWASP ASVS nivel 2 como revisión previa al go-live; pentest básico o revisión externa si el presupuesto lo permite.

## Criterios de aceptación

- Un dump de la base de datos no expone ningún token de WhatsApp, secreto de webhook ni API key utilizables (todo cifrado o hasheado).
- Webhook de Meta con firma inválida → `401` y evento de seguridad; payload jamás procesado.
- Una API key revocada deja de funcionar en el request siguiente.
- El escaneo de secretos en CI bloquea un commit con un token de prueba real.
- La SA de la api no puede leer secretos que no usa ni escribir en buckets ajenos (verificado con `gcloud policy-troubleshoot`).
