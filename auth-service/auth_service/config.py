"""Configuration for auth service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Auth service settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://auth_user:auth_pass@localhost:5432/auth_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Cache settings
    token_cache_ttl: int = 1800  # 30 minutes

    # Security
    admin_token: str | None = None  # Optional admin token for management endpoints

    # Service
    service_name: str = "amplify-auth"
    service_version: str = "1.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
