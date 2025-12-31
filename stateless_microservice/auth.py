"""
Auth client library for microservices.

This module provides integration with the AMPLIfy auth service for token validation.
Microservices use this to validate bearer tokens and check scopes.
"""

import logging
from typing import Callable

import httpx
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

logger = logging.getLogger(__name__)

security = HTTPBearer()


class TokenInfo(BaseModel):
    """Information about a validated token."""
    valid: bool
    scopes: list[str] = []
    token_id: str | None = None
    name: str | None = None
    error: str | None = None
    detail: str | None = None


class AuthClient:
    """
    Client for communicating with the auth service.

    Usage in your microservice:
        from fastapi import Depends

        auth_client = AuthClient(auth_service_url="http://auth-service:8000")

        # In your endpoint:
        @app.get("/protected")
        async def protected_endpoint(token_info = Depends(auth_client.require_scopes(["read"]))):
            return {"message": "Access granted", "user": token_info.name}
    """

    def __init__(self, auth_service_url: str, timeout: float = 5.0):
        """
        Initialize auth client.

        Args:
            auth_service_url: Base URL of auth service (e.g., "http://auth-service:8000")
            timeout: Timeout for auth validation requests in seconds
        """
        self.auth_service_url = auth_service_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def validate_token(
        self,
        token: str,
        required_scopes: list[str] | None = None,
        service_name: str | None = None,
        action_name: str | None = None
    ) -> TokenInfo:
        """
        Validate a token with the auth service.

        Args:
            token: The bearer token to validate
            required_scopes: List of required scopes
            service_name: Name of the service making the request (for audit)
            action_name: Name of the action being performed (for audit)

        Returns:
            TokenInfo object with validation results

        Raises:
            HTTPException: If auth service is unreachable or returns an error
        """
        try:
            response = await self._client.post(
                f"{self.auth_service_url}/auth/validate",
                json={
                    "token": token,
                    "required_scopes": required_scopes or [],
                    "service_name": service_name,
                    "action_name": action_name
                }
            )

            if response.status_code == 200:
                data = response.json()
                return TokenInfo(**data)
            else:
                logger.error(f"Auth service returned {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Auth service error: {response.text}"
                )

        except httpx.TimeoutException:
            logger.error("Auth service timeout")
            raise HTTPException(status_code=504, detail="Auth service timeout")
        except httpx.RequestError as e:
            logger.error(f"Auth service connection error: {e}")
            raise HTTPException(status_code=503, detail="Auth service unavailable")

    def require_scopes(self, required_scopes: list[str] | None = None) -> Callable:
        """
        Create a FastAPI dependency that validates tokens and checks scopes.

        Usage:
            from fastapi import Depends

            @app.get("/protected")
            async def protected(token_info = Depends(auth_client.require_scopes(["read"]))):
                # token_info is TokenInfo object
                return {"user": token_info.name}

        Args:
            required_scopes: List of scopes required to access the endpoint

        Returns:
            FastAPI dependency function
        """
        async def dependency(
            request: Request,
            credentials: HTTPAuthorizationCredentials = Security(security)
        ) -> TokenInfo:
            """Dependency that validates the token."""
            # Get service and action name from request for audit logging
            service_name = getattr(request.app.state, "service_name", None)
            action_name = request.url.path

            token_info = await self.validate_token(
                token=credentials.credentials,
                required_scopes=required_scopes,
                service_name=service_name,
                action_name=action_name
            )

            if not token_info.valid:
                if token_info.error == "token_expired":
                    raise HTTPException(status_code=401, detail="Token expired")
                elif token_info.error == "token_revoked":
                    raise HTTPException(status_code=401, detail="Token has been revoked")
                elif token_info.error == "insufficient_scopes":
                    raise HTTPException(
                        status_code=403,
                        detail=f"Insufficient permissions. Required: {required_scopes}"
                    )
                elif token_info.error == "token_not_found":
                    raise HTTPException(status_code=401, detail="Invalid token")
                else:
                    raise HTTPException(status_code=401, detail="Authentication failed")

            return token_info

        return dependency

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()


def create_auth_dependency(required_scopes: list[str] | None = None):
    """
    Helper to create auth dependency without instantiating AuthClient directly.

    This is useful when you want to use environment-based configuration.

    Usage:
        from fastapi import Depends

        # In your config
        AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")

        # In your app
        require_auth = create_auth_dependency(["read", "write"])

        @app.get("/protected")
        async def protected(token_info = Depends(require_auth)):
            return {"user": token_info.name}
    """
    import os
    auth_url = os.getenv("AUTH_SERVICE_URL", "http://localhost:8000")
    auth_client = AuthClient(auth_url)
    return auth_client.require_scopes(required_scopes)
