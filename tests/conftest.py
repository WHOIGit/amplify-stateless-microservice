"""pytest configuration and fixtures for tests."""
import os

# Set environment variables BEFORE any imports
# This ensures Settings() can be instantiated when modules are imported
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("SERVICE_VERSION", "test-1.0.0")
os.environ.setdefault("TOKEN_CACHE_TTL", "1800")

import pytest
from unittest.mock import patch


@pytest.fixture
def mock_settings():
    """Mock settings for auth service tests."""
    from stateless_microservice.auth_service.config import Settings

    mock_settings_obj = Settings(
        database_url="postgresql://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/0",
        admin_token="test-admin-token",
        service_version="test-1.0.0",
        token_cache_ttl=1800
    )

    with patch('stateless_microservice.auth_service.config.settings', mock_settings_obj):
        yield mock_settings_obj
