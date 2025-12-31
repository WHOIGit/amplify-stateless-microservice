"""
Example processor with token authentication.

This demonstrates how to add authentication to your microservice using
the AMPLIfy auth system.
"""

from pydantic import BaseModel, Field

from stateless_microservice import BaseProcessor, StatelessAction


# Request/Response models
class EchoRequest(BaseModel):
    """Request to echo a message."""
    message: str = Field(..., description="Message to echo")


class EchoResponse(BaseModel):
    """Response with echoed message and user info."""
    message: str
    authenticated_as: str
    scopes: list[str]


class SecretResponse(BaseModel):
    """Response for admin-only endpoint."""
    secret: str
    authenticated_as: str


class Processor(BaseProcessor):
    """Example processor with authentication."""

    @property
    def name(self) -> str:
        return "authenticated-service"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_stateless_actions(self) -> list[StatelessAction]:
        """Define actions with required scopes."""
        return [
            # Public endpoint - no auth required
            StatelessAction(
                name="public",
                path="/public",
                handler=self.public_endpoint,
                methods=("GET",),
                summary="Public endpoint (no auth required)",
                response_model=dict
            ),

            # Protected endpoint - requires 'read' scope
            StatelessAction(
                name="echo",
                path="/echo",
                handler=self.echo_message,
                request_model=EchoRequest,
                response_model=EchoResponse,
                methods=("POST",),
                summary="Echo message (requires 'read' scope)",
                required_scopes=["read"]  # NEW: Require 'read' scope
            ),

            # Admin endpoint - requires 'admin' scope
            StatelessAction(
                name="admin",
                path="/admin/secret",
                handler=self.admin_only,
                methods=("GET",),
                response_model=SecretResponse,
                summary="Admin-only endpoint (requires 'admin' scope)",
                required_scopes=["admin"]  # NEW: Require 'admin' scope
            ),

            # Write endpoint - requires both 'read' and 'write' scopes
            StatelessAction(
                name="update",
                path="/update",
                handler=self.update_data,
                request_model=EchoRequest,
                response_model=dict,
                methods=("POST",),
                summary="Update data (requires 'read' and 'write' scopes)",
                required_scopes=["read", "write"]  # Multiple scopes
            ),
        ]

    def public_endpoint(self) -> dict:
        """Public endpoint - no authentication required."""
        return {
            "message": "This is a public endpoint",
            "auth_required": False
        }

    def echo_message(self, request: EchoRequest, token_info) -> EchoResponse:
        """
        Echo the message back with authentication info.

        Note: token_info is injected by the auth middleware.
        """
        return EchoResponse(
            message=f"Echo: {request.message}",
            authenticated_as=token_info.name,
            scopes=token_info.scopes
        )

    def admin_only(self, token_info) -> SecretResponse:
        """Admin-only endpoint."""
        return SecretResponse(
            secret="This is secret admin data",
            authenticated_as=token_info.name
        )

    def update_data(self, request: EchoRequest, token_info) -> dict:
        """Update endpoint requiring multiple scopes."""
        return {
            "status": "updated",
            "message": request.message,
            "authenticated_as": token_info.name,
            "scopes": token_info.scopes
        }
