"""Permisos finos y su mapeo por rol.

Decisión final de un usuario = permisos del rol ∪ permisos individuales
(tabla user_permissions, solo concesiones extra). La autorización se evalúa
SIEMPRE en el backend; el frontend solo oculta UI.
"""

from app.db.models.enums import UserRole

# Catálogo completo (strings estables)
CONVERSATIONS_READ = "conversations:read:any"
CONVERSATIONS_SEND = "conversations:send"
CONVERSATIONS_ASSIGN = "conversations:assign"
CONVERSATIONS_CLOSE = "conversations:close"
LEADS_READ = "leads:read"
LEADS_WRITE = "leads:write"
LEADS_DELETE = "leads:delete"
LEADS_MOVE_STAGE = "leads:move_stage"
NOTES_WRITE = "notes:write"
NOTES_EDIT_OWN = "notes:edit:own"
NOTES_EDIT_ANY = "notes:edit:any"
PIPELINES_MANAGE = "pipelines:manage"
USERS_MANAGE = "users:manage"
CONFIG_ACCESS = "config:access"
LOGS_READ = "logs:read"
ACCOUNTS_MANAGE = "accounts:manage"
API_KEYS_MANAGE = "api_keys:manage"

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        CONVERSATIONS_READ, CONVERSATIONS_SEND, CONVERSATIONS_ASSIGN, CONVERSATIONS_CLOSE,
        LEADS_READ, LEADS_WRITE, LEADS_DELETE, LEADS_MOVE_STAGE,
        NOTES_WRITE, NOTES_EDIT_OWN, NOTES_EDIT_ANY,
        PIPELINES_MANAGE, USERS_MANAGE, CONFIG_ACCESS, LOGS_READ,
        ACCOUNTS_MANAGE, API_KEYS_MANAGE,
    }
)

_AGENT = frozenset(
    {
        CONVERSATIONS_READ, CONVERSATIONS_SEND,
        LEADS_READ, LEADS_WRITE, LEADS_MOVE_STAGE,
        NOTES_WRITE, NOTES_EDIT_OWN,
    }
)
_SUPERVISOR = _AGENT | frozenset(
    {
        CONVERSATIONS_ASSIGN, CONVERSATIONS_CLOSE,
        LEADS_DELETE, NOTES_EDIT_ANY, PIPELINES_MANAGE, LOGS_READ,
    }
)

ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.agent: _AGENT,
    UserRole.supervisor: _SUPERVISOR,
    UserRole.admin: ALL_PERMISSIONS,
}


def expand_permissions(role: UserRole, granted: set[str] | None = None) -> set[str]:
    return set(ROLE_PERMISSIONS[role]) | ((granted or set()) & ALL_PERMISSIONS)
