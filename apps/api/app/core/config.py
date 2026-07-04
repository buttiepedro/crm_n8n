"""Configuración de la aplicación validada al arranque (fail-fast).

Todas las variables se leen del entorno (o .env en desarrollo). Si falta
alguna requerida o tiene formato inválido, el proceso no inicia.
"""

import base64
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Único .env en la raíz del repo (compartido con docker compose); un
# apps/api/.env local es opcional y pisa al de la raíz si existe.
# En Docker el código vive en /app (sin repo alrededor): parent.parent nunca
# falla y los .env inexistentes se ignoran (la config llega por env vars).
_API_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _API_DIR.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    port: int = 8080
    log_level: str = "INFO"

    database_url: str

    session_secret: SecretStr
    admin_panel_password: SecretStr
    credentials_encryption_key: SecretStr  # base64 de 32 bytes (AES-256)

    whatsapp_verify_token: SecretStr
    whatsapp_app_secret: SecretStr
    graph_api_version: str = "v21.0"

    queue_driver: Literal["inline", "cloud_tasks"] = "inline"
    storage_driver: Literal["local", "gcs"] = "local"
    storage_local_path: Path = Path("./storage")
    gcs_bucket_attachments: str | None = None
    gcp_project_id: str | None = None

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL debe usar el esquema postgresql+asyncpg://")
        return v

    @field_validator("credentials_encryption_key")
    @classmethod
    def _validate_encryption_key(cls, v: SecretStr) -> SecretStr:
        try:
            raw = base64.b64decode(v.get_secret_value(), validate=True)
        except Exception as exc:
            raise ValueError("CREDENTIALS_ENCRYPTION_KEY debe ser base64 válido") from exc
        if len(raw) != 32:
            raise ValueError("CREDENTIALS_ENCRYPTION_KEY debe decodificar a 32 bytes (AES-256)")
        return v

    @property
    def encryption_key_bytes(self) -> bytes:
        return base64.b64decode(self.credentials_encryption_key.get_secret_value())

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
