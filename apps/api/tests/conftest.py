"""Entorno de tests: variables requeridas antes de importar la app.

El .env mínimo: solo contraseña del panel técnico + operativos. Los tokens
de WhatsApp viven en DB (settings); en tests se inyectan con prime_cache.
Los tests unitarios no necesitan base de datos.
"""

import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://crm:crm@localhost:5432/crm_test")
os.environ.setdefault("ADMIN_PANEL_PASSWORD", "test-panel-password")
# 32 bytes en base64 (clave de test, no usar fuera de tests)
os.environ.setdefault(
    "CREDENTIALS_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
)
os.environ.setdefault("QUEUE_DRIVER", "inline")
os.environ.setdefault("STORAGE_DRIVER", "local")
os.environ.setdefault("STORAGE_LOCAL_PATH", "./.test-storage")
