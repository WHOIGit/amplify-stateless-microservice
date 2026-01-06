"""Tests for auth service models."""
import pytest
from datetime import datetime
from pydantic import ValidationError

from stateless_microservice.auth_service.models import (
    CreateTokenRequest,
    ValidateTokenRequest,
    RevokeTokenRequest,
    ExtendTokenRequest,
    TokenResponse,
    TokenInfoResponse,
    ValidateTokenResponse,
    RevokeTokenResponse,
    TokenListResponse,
    HealthResponse,
    ErrorResponse,
)


# ============================================
# Request Model Tests
# ============================================

def test_create_token_request_valid():
    """Test valid token creation request."""
    req = CreateTokenRequest(
        name="my-token",
        scopes=["read", "write"],
        ttl_days=30,
        metadata={"env": "production"}
    )
    assert req.name == "my-token"
    assert len(req.scopes) == 2
    assert req.ttl_days == 30
    assert req.metadata["env"] == "production"


def test_create_token_request_no_ttl():
    """Test token creation without expiration (permanent token)."""
    req = CreateTokenRequest(
        name="permanent-token",
        scopes=["admin"]
    )
    assert req.ttl_days is None
    assert req.metadata == {}


def test_create_token_request_empty_scopes():
    """Test token creation with empty scopes list."""
    req = CreateTokenRequest(
        name="no-scopes-token",
        scopes=[]
    )
    assert req.scopes == []


def test_create_token_request_missing_required():
    """Test that missing required fields raises validation error."""
    with pytest.raises(ValidationError):
        CreateTokenRequest(name="test")  # Missing required 'scopes'

    with pytest.raises(ValidationError):
        CreateTokenRequest(scopes=["read"])  # Missing required 'name'


def test_validate_token_request_defaults():
    """Test validation request with default values."""
    req = ValidateTokenRequest(token="amp_live_test123")
    assert req.token == "amp_live_test123"
    assert req.required_scopes == []
    assert req.service_name is None
    assert req.action_name is None


def test_validate_token_request_with_all_fields():
    """Test validation request with all fields populated."""
    req = ValidateTokenRequest(
        token="amp_live_test123",
        required_scopes=["read", "write"],
        service_name="my-service",
        action_name="/api/endpoint"
    )
    assert len(req.required_scopes) == 2
    assert req.service_name == "my-service"
    assert req.action_name == "/api/endpoint"


def test_revoke_token_request_optional_reason():
    """Test revoke request with and without reason."""
    req1 = RevokeTokenRequest()
    assert req1.reason is None

    req2 = RevokeTokenRequest(reason="Compromised token")
    assert req2.reason == "Compromised token"


def test_extend_token_request():
    """Test extend token request."""
    req = ExtendTokenRequest(extend_days=30)
    assert req.extend_days == 30


def test_extend_token_request_requires_days():
    """Test that extend_days is required."""
    with pytest.raises(ValidationError):
        ExtendTokenRequest()


# ============================================
# Response Model Tests
# ============================================

def test_token_response():
    """Test token response model."""
    now = datetime.now()
    resp = TokenResponse(
        token="amp_live_secret123",
        token_id="uuid-123",
        name="test-token",
        scopes=["read", "write"],
        created_at=now,
        expires_at=None
    )
    assert resp.token.startswith("amp_live_")
    assert resp.token_id == "uuid-123"
    assert resp.expires_at is None


def test_token_response_with_expiration():
    """Test token response with expiration date."""
    now = datetime.now()
    future = datetime(2025, 12, 31)
    resp = TokenResponse(
        token="amp_live_secret123",
        token_id="uuid-123",
        name="test-token",
        scopes=["read"],
        created_at=now,
        expires_at=future
    )
    assert resp.expires_at == future


def test_token_info_response():
    """Test token info response (without actual token)."""
    now = datetime.now()
    resp = TokenInfoResponse(
        token_id="uuid-123",
        name="my-token",
        scopes=["read", "write"],
        created_at=now,
        expires_at=None,
        revoked=False,
        metadata={"env": "prod"}
    )
    assert resp.revoked is False
    assert resp.revoked_at is None
    assert resp.metadata["env"] == "prod"


def test_token_info_response_revoked():
    """Test token info response for revoked token."""
    now = datetime.now()
    resp = TokenInfoResponse(
        token_id="uuid-123",
        name="revoked-token",
        scopes=["read"],
        created_at=now,
        expires_at=None,
        revoked=True,
        revoked_at=now
    )
    assert resp.revoked is True
    assert resp.revoked_at is not None


def test_validate_token_response_valid():
    """Test validation response for valid token."""
    resp = ValidateTokenResponse(
        valid=True,
        scopes=["read", "write"],
        token_id="uuid-123",
        name="my-token"
    )
    assert resp.valid is True
    assert len(resp.scopes) == 2
    assert resp.error is None
    assert resp.detail is None


def test_validate_token_response_invalid():
    """Test validation response for invalid token."""
    resp = ValidateTokenResponse(
        valid=False,
        error="token_expired",
        detail="Token expired on 2024-01-01"
    )
    assert resp.valid is False
    assert resp.error == "token_expired"
    assert resp.scopes == []
    assert resp.token_id is None


def test_validate_token_response_insufficient_scopes():
    """Test validation response for insufficient scopes."""
    resp = ValidateTokenResponse(
        valid=False,
        scopes=["read"],
        token_id="uuid-123",
        name="my-token",
        error="insufficient_scopes",
        detail="Required scopes: ['admin']"
    )
    assert resp.valid is False
    assert resp.error == "insufficient_scopes"
    assert "read" in resp.scopes


def test_revoke_token_response():
    """Test revoke token response."""
    now = datetime.now()
    resp = RevokeTokenResponse(
        success=True,
        token_id="uuid-123",
        revoked_at=now
    )
    assert resp.success is True
    assert resp.token_id == "uuid-123"
    assert resp.revoked_at == now


def test_token_list_response():
    """Test token list response."""
    now = datetime.now()
    tokens = [
        TokenInfoResponse(
            token_id="uuid-1",
            name="token-1",
            scopes=["read"],
            created_at=now,
            expires_at=None,
            revoked=False
        ),
        TokenInfoResponse(
            token_id="uuid-2",
            name="token-2",
            scopes=["write"],
            created_at=now,
            expires_at=None,
            revoked=False
        )
    ]
    resp = TokenListResponse(tokens=tokens, total=2)
    assert resp.total == 2
    assert len(resp.tokens) == 2


def test_token_list_response_empty():
    """Test empty token list response."""
    resp = TokenListResponse(tokens=[], total=0)
    assert resp.total == 0
    assert resp.tokens == []


def test_health_response():
    """Test health check response."""
    resp = HealthResponse(
        status="healthy",
        version="1.0.0",
        components={
            "database": "connected",
            "redis": "connected"
        }
    )
    assert resp.status == "healthy"
    assert resp.version == "1.0.0"
    assert resp.components["database"] == "connected"


def test_health_response_minimal():
    """Test health response with minimal fields."""
    resp = HealthResponse(
        status="healthy",
        version="1.0.0"
    )
    assert resp.components == {}


def test_error_response():
    """Test error response model."""
    resp = ErrorResponse(
        error="token_not_found",
        detail="Token does not exist in database"
    )
    assert resp.error == "token_not_found"
    assert resp.detail is not None


def test_error_response_no_detail():
    """Test error response without detail."""
    resp = ErrorResponse(error="internal_error")
    assert resp.error == "internal_error"
    assert resp.detail is None


# ============================================
# Model Serialization Tests
# ============================================

def test_validate_token_response_excludes_none():
    """Test that ValidateTokenResponse excludes None values."""
    resp = ValidateTokenResponse(
        valid=True,
        scopes=["read"]
    )
    data = resp.model_dump(exclude_none=True)
    assert "token_id" not in data
    assert "name" not in data
    assert "error" not in data
    assert "detail" not in data
    assert "valid" in data
    assert "scopes" in data


def test_token_info_response_default_metadata():
    """Test that metadata defaults to empty dict."""
    now = datetime.now()
    resp = TokenInfoResponse(
        token_id="uuid-123",
        name="test-token",
        scopes=["read"],
        created_at=now,
        expires_at=None,
        revoked=False
    )
    assert resp.metadata == {}


def test_create_token_request_default_metadata():
    """Test that metadata defaults to empty dict in create request."""
    req = CreateTokenRequest(
        name="test-token",
        scopes=["read"]
    )
    assert req.metadata == {}


# ============================================
# Field Validation Tests
# ============================================

def test_extend_token_request_positive_days():
    """Test that extend_days can be positive."""
    req = ExtendTokenRequest(extend_days=30)
    assert req.extend_days == 30


def test_extend_token_request_allows_negative_days():
    """Test that extend_days allows negative (shortening expiration)."""
    # Note: The model doesn't prevent negative values
    req = ExtendTokenRequest(extend_days=-10)
    assert req.extend_days == -10


def test_validate_token_request_empty_scopes():
    """Test validation request with empty required scopes."""
    req = ValidateTokenRequest(
        token="amp_live_test",
        required_scopes=[]
    )
    assert req.required_scopes == []
