"""Entorno de tests: variables requeridas antes de importar la app.

Los tests unitarios no necesitan base de datos; los de integración (P3+)
usarán una DB efímera y se marcan aparte.
"""

import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://crm:crm@localhost:5432/crm_test")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("ADMIN_PANEL_PASSWORD", "test-panel-password")
# 32 bytes en base64 (clave de test, no usar fuera de tests)
os.environ.setdefault(
    "CREDENTIALS_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
)
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "verify-token-test")
os.environ.setdefault("WHATSAPP_APP_SECRET", "app-secret-test")
os.environ.setdefault("QUEUE_DRIVER", "inline")
os.environ.setdefault("STORAGE_DRIVER", "local")
os.environ.setdefault("STORAGE_LOCAL_PATH", "./.test-storage")
