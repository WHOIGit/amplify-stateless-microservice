"""Tests for auth client library."""
import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from stateless_microservice.auth import AuthClient, TokenInfo


@pytest.mark.asyncio
async def test_validate_token_success():
    """Test successful token validation."""
    client = AuthClient("http://auth:8000")

    # Mock httpx response
    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "valid": True,
                "scopes": ["read", "write"],
                "token_id": "123",
                "name": "test-token"
            }
        )

        result = await client.validate_token("test_token", ["read"])

        assert result.valid is True
        assert "read" in result.scopes
        assert "write" in result.scopes
        assert result.token_id == "123"
        assert result.name == "test-token"


@pytest.mark.asyncio
async def test_validate_token_with_service_info():
    """Test token validation with service and action names."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "valid": True,
                "scopes": ["read"],
                "token_id": "123",
                "name": "test-token"
            }
        )

        result = await client.validate_token(
            "test_token",
            required_scopes=["read"],
            service_name="my-service",
            action_name="/api/test"
        )

        # Verify the request was made with correct parameters
        call_args = mock_post.call_args
        assert call_args[1]["json"]["service_name"] == "my-service"
        assert call_args[1]["json"]["action_name"] == "/api/test"
        assert result.valid is True


@pytest.mark.asyncio
async def test_validate_token_timeout():
    """Test handling of auth service timeout."""
    client = AuthClient("http://auth:8000", timeout=1.0)

    with patch.object(client._client, 'post', side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(HTTPException) as exc_info:
            await client.validate_token("test_token")

        assert exc_info.value.status_code == 504
        assert "timeout" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_validate_token_connection_error():
    """Test handling of auth service unavailability."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'post', side_effect=httpx.ConnectError("Connection failed")):
        with pytest.raises(HTTPException) as exc_info:
            await client.validate_token("test_token")

        assert exc_info.value.status_code == 503
        assert "unavailable" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_validate_token_auth_service_error():
    """Test handling of auth service returning error status."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(
            status_code=500,
            text="Internal server error"
        )

        with pytest.raises(HTTPException) as exc_info:
            await client.validate_token("test_token")

        assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_require_scopes_success():
    """Test that valid token with sufficient scopes succeeds."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "valid": True,
                "scopes": ["read", "write"],
                "token_id": "123",
                "name": "test-token"
            }
        )

        # Create the dependency
        dependency = client.require_scopes(["read"])

        # Mock request and credentials
        mock_request = Mock(spec=Request)
        mock_request.app.state.service_name = "test-service"
        mock_request.url.path = "/test"

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test_token"
        )

        result = await dependency(mock_request, mock_credentials)

        assert result.valid is True
        assert result.token_id == "123"


@pytest.mark.asyncio
async def test_require_scopes_insufficient():
    """Test that insufficient scopes raises 403."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "valid": False,
                "error": "insufficient_scopes",
                "detail": "Missing required scopes"
            }
        )

        dependency = client.require_scopes(["admin"])

        mock_request = Mock(spec=Request)
        mock_request.app.state.service_name = "test-service"
        mock_request.url.path = "/test"

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test_token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await dependency(mock_request, mock_credentials)

        assert exc_info.value.status_code == 403
        assert "permissions" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_scopes_token_expired():
    """Test that expired token raises 401."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "valid": False,
                "error": "token_expired",
                "detail": "Token expired on 2024-01-01"
            }
        )

        dependency = client.require_scopes(["read"])

        mock_request = Mock(spec=Request)
        mock_request.app.state.service_name = "test-service"
        mock_request.url.path = "/test"

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test_token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await dependency(mock_request, mock_credentials)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_scopes_token_revoked():
    """Test that revoked token raises 401."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "valid": False,
                "error": "token_revoked",
                "detail": "Token has been revoked"
            }
        )

        dependency = client.require_scopes(["read"])

        mock_request = Mock(spec=Request)
        mock_request.app.state.service_name = "test-service"
        mock_request.url.path = "/test"

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test_token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await dependency(mock_request, mock_credentials)

        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_scopes_token_not_found():
    """Test that non-existent token raises 401."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "valid": False,
                "error": "token_not_found",
                "detail": "Token not found in database"
            }
        )

        dependency = client.require_scopes(["read"])

        mock_request = Mock(spec=Request)
        mock_request.app.state.service_name = "test-service"
        mock_request.url.path = "/test"

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid_token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await dependency(mock_request, mock_credentials)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_scopes_unknown_error():
    """Test that unknown error raises 401."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "valid": False,
                "error": "unknown_error",
                "detail": "Something went wrong"
            }
        )

        dependency = client.require_scopes(["read"])

        mock_request = Mock(spec=Request)
        mock_request.app.state.service_name = "test-service"
        mock_request.url.path = "/test"

        mock_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test_token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await dependency(mock_request, mock_credentials)

        assert exc_info.value.status_code == 401
        assert "authentication failed" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_auth_client_close():
    """Test that client can be closed properly."""
    client = AuthClient("http://auth:8000")

    with patch.object(client._client, 'aclose', new_callable=AsyncMock) as mock_close:
        await client.close()
        mock_close.assert_called_once()


def test_token_info_model():
    """Test TokenInfo model creation."""
    token_info = TokenInfo(
        valid=True,
        scopes=["read", "write"],
        token_id="123",
        name="test-token"
    )

    assert token_info.valid is True
    assert len(token_info.scopes) == 2
    assert token_info.error is None


def test_token_info_model_with_error():
    """Test TokenInfo model with error."""
    token_info = TokenInfo(
        valid=False,
        error="token_expired",
        detail="Token expired on 2024-01-01"
    )

    assert token_info.valid is False
    assert token_info.error == "token_expired"
    assert token_info.scopes == []
