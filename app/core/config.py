import os
import base64
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "MetaTrader 5 & Binary Options Quant Server"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", description="development | production | testing")
    DEBUG: bool = Field(default=False)
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)

    # Security & Encryption
    SECRET_KEY: str = Field(
        default="quant-server-secret-key-change-in-production-32b!",
        description="Application secret key for JWT/signing",
    )
    FERNET_KEY: str = Field(
        default="v9-eJ9K_FmQy6M9P4_5H6l2_jZ2y_8z0_3u5t_X4w1A=",
        description="Fernet 32-byte url-safe base64 key for credential encryption",
    )
    API_KEY: Optional[str] = Field(default=None, description="Optional API key for service-to-service auth")

    # PostgreSQL Database Connection
    POSTGRES_USER: str = Field(default="admin")
    POSTGRES_PASSWORD: str = Field(default="1234")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="quant_trading")
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Direct override for database URL. If omitted, built from components.",
    )

    # MT5 Service & Bridge Connection
    MT5_API_URL: str = Field(
        default="http://localhost:5001",
        description="URL of MT5 Wine Flask REST API container",
    )
    MT5_BRIDGE_HOST: str = Field(default="127.0.0.1")
    MT5_BRIDGE_PORT: int = Field(default=18812)
    MT5_PATH: Optional[str] = Field(default=None)

    # CORS
    CORS_ORIGINS: List[str] = Field(default=["*"])

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            # Ensure dialect is postgresql+asyncpg
            url = self.DATABASE_URL
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql+asyncpg://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if "+asyncpg" in url:
                return url.replace("+asyncpg", "", 1)
            return url
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @field_validator("FERNET_KEY")
    @classmethod
    def validate_fernet_key(cls, v: str) -> str:
        try:
            decoded = base64.urlsafe_b64decode(v)
            if len(decoded) != 32:
                # Generate a valid fallback if length is not 32 bytes
                return base64.urlsafe_b64encode(os.urandom(32)).decode()
        except Exception:
            return base64.urlsafe_b64encode(os.urandom(32)).decode()
        return v


settings = Settings()
