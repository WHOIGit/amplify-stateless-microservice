"""Pydantic models for auth service API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================
# Request Models
# ============================================

class CreateTokenRequest(BaseModel):
    """Request to create a new token."""
    name: str = Field(..., description="Human-readable token identifier")
    scopes: list[str] = Field(..., description="List of permission scopes")
    ttl_days: int | None = Field(None, description="Days until expiration (null = never)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class ValidateTokenRequest(BaseModel):
    """Request to validate a token."""
    token: str = Field(..., description="The bearer token to validate")
    required_scopes: list[str] = Field(default_factory=list, description="Required scopes")
    service_name: str | None = Field(None, description="Name of requesting service (for audit)")
    action_name: str | None = Field(None, description="Action being performed (for audit)")


class RevokeTokenRequest(BaseModel):
    """Request to revoke a token."""
    reason: str | None = Field(None, description="Reason for revocation")


class ExtendTokenRequest(BaseModel):
    """Request to extend token expiration."""
    extend_days: int = Field(..., description="Number of days to extend")


# ============================================
# Response Models
# ============================================

class TokenResponse(BaseModel):
    """Response when creating a token."""
    token: str = Field(..., description="The bearer token (only shown once!)")
    token_id: str = Field(..., description="Unique token identifier")
    name: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None


class TokenInfoResponse(BaseModel):
    """Response with token information (without the actual token)."""
    token_id: str
    name: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    revoked: bool
    revoked_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidateTokenResponse(BaseModel):
    """Response from token validation."""
    model_config = {"exclude_none": True}

    valid: bool
    scopes: list[str] = Field(default_factory=list)
    token_id: str | None = None
    name: str | None = None
    error: str | None = Field(None, description="Error code if invalid")
    detail: str | None = Field(None, description="Human-readable error message")


class RevokeTokenResponse(BaseModel):
    """Response from token revocation."""
    success: bool
    token_id: str
    revoked_at: datetime


class TokenListResponse(BaseModel):
    """Response with list of tokens."""
    tokens: list[TokenInfoResponse]
    total: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    components: dict[str, str] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: str | None = None
