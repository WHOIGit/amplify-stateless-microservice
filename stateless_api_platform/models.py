"""Lightweight models shared by stateless APIs."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="healthy")
    version: str = Field(default="1.0.0")


class ErrorResponse(BaseModel):
    """Error response envelope."""

    error: str = Field(..., description="High-level error message")
    detail: str | None = Field(None, description="Additional context for debugging")
