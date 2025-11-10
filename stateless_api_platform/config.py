"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Settings for stateless services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API Settings
    api_title: str = "Stateless API Service"
    api_version: str = "1.0.0"
    api_description: str = "Synchronous FastAPI microservice backed by S3 assets"

    # S3 Settings (for local S3-compatible storage like MinIO)
    s3_endpoint_url: str = "http://localhost:9000"  # Your local S3 endpoint
    s3_bucket: str = "ifcb-features"
    s3_access_key: str = "minioadmin"  # Change via environment variable
    s3_secret_key: str = "minioadmin"  # Change via environment variable
    s3_use_ssl: bool = False  # Set to True if using HTTPS

    # Optional default prefixes for generated URIs
    s3_assets_prefix: str = "assets"


# Global settings instance
settings = Settings()
