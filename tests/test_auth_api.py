"""Integration tests for auth service API."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient

from stateless_microservice.auth_service.api import app, _validate_from_data
from stateless_microservice.auth_service.commands import CommandType


# ============================================
# Test Fixtures
# ============================================

@pytest.fixture
def mock_dependencies():
    """Mock database and Redis dependencies."""
    with patch('stateless_microservice.auth_service.api.db_pool') as mock_db, \
         patch('stateless_microservice.auth_service.api.redis_client') as mock_redis, \
         patch('stateless_microservice.auth_service.api.command_processor') as mock_processor:

        # Setup mock database pool
        conn = AsyncMock()

        # Create proper async context manager for pool.acquire()
        class MockAcquireContext:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        # Make acquire() return the context manager (not async)
        mock_db.acquire = Mock(return_value=MockAcquireContext())

        # Setup mock redis client
        mock_redis.sismember = AsyncMock(return_value=False)
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.hset = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_redis.ping = AsyncMock()

        # Setup mock command processor
        mock_processor.running = True
        mock_processor.submit_command = AsyncMock()

        yield {
            'db_pool': mock_db,
            'db_conn': conn,
            'redis': mock_redis,
            'processor': mock_processor
        }


# ============================================
# Health Check Tests
# ============================================

def test_health_check_healthy(mock_dependencies):
    """Test health check when all components are healthy."""
    mocks = mock_dependencies
    mocks['db_conn'].fetchval.return_value = 1

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert data["components"]["database"] == "healthy"
    assert data["components"]["redis"] == "healthy"
    assert data["components"]["command_processor"] == "running"


def test_health_check_root_endpoint(mock_dependencies):
    """Test that root endpoint also returns health."""
    mocks = mock_dependencies
    mocks['db_conn'].fetchval.return_value = 1

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_health_check_database_unhealthy(mock_dependencies):
    """Test health check when database is unhealthy."""
    mocks = mock_dependencies
    mocks['db_conn'].fetchval.side_effect = Exception("Database connection failed")

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert "unhealthy" in data["components"]["database"]


# ============================================
# Token Validation Tests
# ============================================

def test_validate_token_success_from_cache(mock_dependencies):
    """Test successful token validation from cache."""
    mocks = mock_dependencies

    # Mock cached token data
    mocks['redis'].hgetall.return_value = {
        "token_id": "123",
        "name": "test-token",
        "scopes": "read,write",
        "expires_at": "",
        "revoked": "0"
    }

    client = TestClient(app)
    response = client.post(
        "/auth/validate",
        json={
            "token": "amp_live_test123",
            "required_scopes": ["read"]
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert "read" in data["scopes"]
    assert "write" in data["scopes"]
    assert data["token_id"] == "123"
    assert data["name"] == "test-token"


def test_validate_token_success_from_database(mock_dependencies):
    """Test successful token validation from database (cache miss)."""
    mocks = mock_dependencies

    # Cache miss
    mocks['redis'].hgetall.return_value = {}

    # Database returns token
    mocks['db_conn'].fetchrow.return_value = {
        "token_id": "456",
        "name": "db-token",
        "scopes": ["admin"],
        "expires_at": None,
        "revoked": False,
        "metadata": {}
    }

    client = TestClient(app)
    response = client.post(
        "/auth/validate",
        json={
            "token": "amp_live_dbtoken",
            "required_scopes": ["admin"]
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert "admin" in data["scopes"]

    # Verify cache was populated
    assert mocks['redis'].hset.called
    assert mocks['redis'].expire.called


def test_validate_token_revoked_in_set(mock_dependencies):
    """Test that revoked token is rejected."""
    mocks = mock_dependencies

    # Token is in revoked set
    mocks['redis'].sismember.return_value = True

    client = TestClient(app)
    response = client.post(
        "/auth/validate",
        json={"token": "amp_live_revoked"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["error"] == "token_revoked"


def test_validate_token_not_found(mock_dependencies):
    """Test validation of non-existent token."""
    mocks = mock_dependencies

    # Cache miss
    mocks['redis'].hgetall.return_value = {}

    # Database returns None
    mocks['db_conn'].fetchrow.return_value = None

    client = TestClient(app)
    response = client.post(
        "/auth/validate",
        json={"token": "amp_live_nonexistent"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["error"] == "token_not_found"


def test_validate_token_expired(mock_dependencies):
    """Test validation of expired token."""
    mocks = mock_dependencies

    # Token expired yesterday
    expired_date = datetime.now() - timedelta(days=1)

    mocks['redis'].hgetall.return_value = {
        "token_id": "789",
        "name": "expired-token",
        "scopes": "read",
        "expires_at": expired_date.isoformat(),
        "revoked": "0"
    }

    client = TestClient(app)
    response = client.post(
        "/auth/validate",
        json={"token": "amp_live_expired"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["error"] == "token_expired"


def test_validate_token_insufficient_scopes(mock_dependencies):
    """Test validation when token lacks required scopes."""
    mocks = mock_dependencies

    mocks['redis'].hgetall.return_value = {
        "token_id": "999",
        "name": "limited-token",
        "scopes": "read",
        "expires_at": "",
        "revoked": "0"
    }

    client = TestClient(app)
    response = client.post(
        "/auth/validate",
        json={
            "token": "amp_live_limited",
            "required_scopes": ["admin"]
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["error"] == "insufficient_scopes"


# ============================================
# Token Creation Tests
# ============================================

def test_create_token_success(mock_dependencies):
    """Test successful token creation."""
    mocks = mock_dependencies

    # Mock command processor response
    mocks['processor'].submit_command.return_value = {
        "token": "amp_live_new123",
        "token_id": "new-id-123",
        "name": "new-token",
        "scopes": ["read", "write"],
        "created_at": datetime.now().isoformat(),
        "expires_at": None
    }

    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.post(
            "/auth/tokens",
            json={
                "name": "new-token",
                "scopes": ["read", "write"],
                "ttl_days": None
            },
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 201
    data = response.json()
    assert data["token"] == "amp_live_new123"
    assert data["token_id"] == "new-id-123"
    assert data["name"] == "new-token"
    assert data["scopes"] == ["read", "write"]
    assert data["expires_at"] is None


def test_create_token_missing_auth(mock_dependencies):
    """Test token creation without authorization."""
    client = TestClient(app)
    response = client.post(
        "/auth/tokens",
        json={
            "name": "new-token",
            "scopes": ["read"]
        }
    )

    assert response.status_code == 401


def test_create_token_invalid_auth_format(mock_dependencies):
    """Test token creation with invalid auth header format."""
    client = TestClient(app)
    response = client.post(
        "/auth/tokens",
        json={
            "name": "new-token",
            "scopes": ["read"]
        },
        headers={"Authorization": "InvalidFormat token123"}
    )

    assert response.status_code == 401


def test_create_token_timeout(mock_dependencies):
    """Test token creation timeout."""
    mocks = mock_dependencies

    # Simulate timeout
    mocks['processor'].submit_command.side_effect = TimeoutError()

    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.post(
            "/auth/tokens",
            json={
                "name": "new-token",
                "scopes": ["read"]
            },
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 504


# ============================================
# Token Revocation Tests
# ============================================

def test_revoke_token_success(mock_dependencies):
    """Test successful token revocation."""
    mocks = mock_dependencies

    token_id = "00000000-0000-0000-0000-000000000001"

    mocks['processor'].submit_command.return_value = {
        "success": True,
        "token_id": token_id,
        "revoked_at": datetime.now().isoformat()
    }

    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.post(
            f"/auth/tokens/{token_id}/revoke",
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_revoke_token_not_found(mock_dependencies):
    """Test revoking non-existent token."""
    mocks = mock_dependencies

    token_id = "00000000-0000-0000-0000-000000000001"

    mocks['processor'].submit_command.return_value = {
        "error": "token_not_found",
        "detail": "Token not found"
    }

    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.post(
            f"/auth/tokens/{token_id}/revoke",
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 404


def test_revoke_token_invalid_uuid(mock_dependencies):
    """Test revoking with invalid UUID format."""
    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.post(
            "/auth/tokens/not-a-uuid/revoke",
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 400


# ============================================
# Token Listing Tests
# ============================================

def test_list_tokens_success(mock_dependencies):
    """Test listing all tokens."""
    mocks = mock_dependencies

    mocks['db_conn'].fetch.return_value = [
        {
            "token_id": "id-1",
            "name": "token-1",
            "scopes": ["read"],
            "created_at": datetime.now(),
            "expires_at": None,
            "revoked": False,
            "revoked_at": None,
            "metadata": {}
        },
        {
            "token_id": "id-2",
            "name": "token-2",
            "scopes": ["write"],
            "created_at": datetime.now(),
            "expires_at": None,
            "revoked": False,
            "revoked_at": None,
            "metadata": {}
        }
    ]

    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.get(
            "/auth/tokens",
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["tokens"]) == 2


def test_list_tokens_include_revoked(mock_dependencies):
    """Test listing tokens including revoked ones."""
    mocks = mock_dependencies

    mocks['db_conn'].fetch.return_value = []

    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.get(
            "/auth/tokens?include_revoked=true",
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 200
    # Verify query included revoked tokens (check mock call)


def test_list_tokens_empty(mock_dependencies):
    """Test listing when no tokens exist."""
    mocks = mock_dependencies

    mocks['db_conn'].fetch.return_value = []

    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.get(
            "/auth/tokens",
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["tokens"] == []


# ============================================
# Get Single Token Tests
# ============================================

def test_get_token_success(mock_dependencies):
    """Test getting a specific token."""
    mocks = mock_dependencies

    token_id = "00000000-0000-0000-0000-000000000001"

    mocks['db_conn'].fetchrow.return_value = {
        "token_id": token_id,
        "name": "specific-token",
        "scopes": ["read", "write"],
        "created_at": datetime.now(),
        "expires_at": None,
        "revoked": False,
        "revoked_at": None,
        "metadata": {"env": "prod"}
    }

    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.get(
            f"/auth/tokens/{token_id}",
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "specific-token"
    assert len(data["scopes"]) == 2
    assert data["metadata"]["env"] == "prod"


def test_get_token_not_found(mock_dependencies):
    """Test getting non-existent token."""
    mocks = mock_dependencies

    token_id = "00000000-0000-0000-0000-000000000001"

    mocks['db_conn'].fetchrow.return_value = None

    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.get(
            f"/auth/tokens/{token_id}",
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 404


def test_get_token_invalid_uuid(mock_dependencies):
    """Test getting token with invalid UUID."""
    client = TestClient(app)
    with patch('stateless_microservice.auth_service.config.settings.admin_token', 'test-admin'):
        response = client.get(
            "/auth/tokens/not-a-uuid",
            headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 400


# ============================================
# Helper Function Tests
# ============================================

def test_validate_from_data_valid_token():
    """Test _validate_from_data with valid token."""
    data = {
        "token_id": "123",
        "name": "test-token",
        "scopes": "read,write",
        "expires_at": "",
        "revoked": "0"
    }

    result = _validate_from_data(data, ["read"])

    assert result.valid is True
    assert "read" in result.scopes


def test_validate_from_data_revoked():
    """Test _validate_from_data with revoked token."""
    data = {
        "token_id": "123",
        "name": "test-token",
        "scopes": "read",
        "expires_at": "",
        "revoked": "1"
    }

    result = _validate_from_data(data, [])

    assert result.valid is False
    assert result.error == "token_revoked"


def test_validate_from_data_expired():
    """Test _validate_from_data with expired token."""
    expired = datetime.now() - timedelta(days=1)

    data = {
        "token_id": "123",
        "name": "test-token",
        "scopes": "read",
        "expires_at": expired.isoformat(),
        "revoked": "0"
    }

    result = _validate_from_data(data, [])

    assert result.valid is False
    assert result.error == "token_expired"


def test_validate_from_data_not_expired():
    """Test _validate_from_data with token that expires in future."""
    future = datetime.now() + timedelta(days=30)

    data = {
        "token_id": "123",
        "name": "test-token",
        "scopes": "read",
        "expires_at": future.isoformat(),
        "revoked": "0"
    }

    result = _validate_from_data(data, [])

    assert result.valid is True


def test_validate_from_data_insufficient_scopes():
    """Test _validate_from_data with insufficient scopes."""
    data = {
        "token_id": "123",
        "name": "test-token",
        "scopes": "read",
        "expires_at": "",
        "revoked": "0"
    }

    result = _validate_from_data(data, ["admin"])

    assert result.valid is False
    assert result.error == "insufficient_scopes"


def test_validate_from_data_empty_scopes():
    """Test _validate_from_data with no scopes."""
    data = {
        "token_id": "123",
        "name": "test-token",
        "scopes": "",
        "expires_at": "",
        "revoked": "0"
    }

    result = _validate_from_data(data, [])

    assert result.valid is True
    assert result.scopes == []
