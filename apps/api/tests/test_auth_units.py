"""Tests unitarios de auth: argon2, expansión de permisos, rate limit."""

from app.db.models.enums import UserRole
from app.modules.auth.passwords import hash_password, verify_password
from app.modules.auth.permissions import (
    ALL_PERMISSIONS,
    CONFIG_ACCESS,
    LEADS_DELETE,
    ROLE_PERMISSIONS,
    expand_permissions,
)
from app.modules.auth.service import rate_limit_ok


def test_password_roundtrip():
    h = hash_password("secreta-123456")
    assert verify_password(h, "secreta-123456")
    assert not verify_password(h, "otra")
    assert not verify_password("basura-no-hash", "secreta-123456")


def test_role_permission_hierarchy():
    agent = ROLE_PERMISSIONS[UserRole.agent]
    supervisor = ROLE_PERMISSIONS[UserRole.supervisor]
    admin = ROLE_PERMISSIONS[UserRole.admin]
    assert agent < supervisor < ALL_PERMISSIONS
    assert admin == ALL_PERMISSIONS
    # Solo admin accede al panel técnico por defecto
    assert CONFIG_ACCESS not in supervisor
    assert CONFIG_ACCESS in admin


def test_individual_grants_expand():
    perms = expand_permissions(UserRole.agent, {LEADS_DELETE, "permiso-invalido"})
    assert LEADS_DELETE in perms
    assert "permiso-invalido" not in perms  # solo permisos del catálogo


def test_rate_limit_window():
    key = "test:rate:limit"
    for _ in range(5):
        assert rate_limit_ok(key)
    assert not rate_limit_ok(key)
