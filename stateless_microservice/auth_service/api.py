"""FastAPI application for authentication service."""

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

import asyncpg
import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException, Header, Security
from fastapi.security import HTTPBearer

from .commands import CommandProcessor, CommandType
from .config import settings
from .models import (
    CreateTokenRequest,
    ErrorResponse,
    ExtendTokenRequest,
    HealthResponse,
    RevokeTokenRequest,
    RevokeTokenResponse,
    TokenInfoResponse,
    TokenListResponse,
    TokenResponse,
    ValidateTokenRequest,
    ValidateTokenResponse,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Global state
db_pool: asyncpg.Pool | None = None
redis_client: redis.Redis | None = None
command_processor: CommandProcessor | None = None

security = HTTPBearer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global db_pool, redis_client, command_processor

    # Startup
    logger.info("Starting auth service...")

    # Configure JSONB codec for automatic JSON parsing
    async def init_connection(conn):
        """Configure connection to auto-parse JSONB as Python dicts."""
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )

    # Connect to PostgreSQL
    db_pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=5,
        max_size=20,
        command_timeout=60,
        init=init_connection
    )
    logger.info("Connected to PostgreSQL")

    # Connect to Redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()
    logger.info("Connected to Redis")

    # Start command processor (single writer)
    command_processor = CommandProcessor(
        db_pool=db_pool,
        redis_client=redis_client,
        cache_ttl=settings.token_cache_ttl
    )
    await command_processor.start()

    # Pre-load active tokens into cache
    await _warm_cache()

    logger.info("Auth service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down auth service...")

    if command_processor:
        await command_processor.stop()

    if redis_client:
        await redis_client.close()

    if db_pool:
        await db_pool.close()

    logger.info("Auth service stopped")


async def _warm_cache():
    """Pre-load all active tokens into Redis cache."""
    logger.info("Warming cache with active tokens...")

    async with db_pool.acquire() as conn:
        tokens = await conn.fetch(
            """
            SELECT
                t.token_hash,
                t.token_id,
                t.name,
                t.expires_at,
                t.metadata,
                array_agg(ts.scope) FILTER (WHERE ts.scope IS NOT NULL) as scopes
            FROM tokens t
            LEFT JOIN token_scopes ts ON t.token_id = ts.token_id
            WHERE t.revoked = FALSE
              AND (t.expires_at IS NULL OR t.expires_at > NOW())
            GROUP BY t.token_id
            """
        )

    for token in tokens:
        await redis_client.hset(
            f"token:{token['token_hash']}",
            mapping={
                "token_id": str(token["token_id"]),
                "name": token["name"],
                "scopes": ",".join(token["scopes"]) if token["scopes"] else "",
                "expires_at": token["expires_at"].isoformat() if token["expires_at"] else "",
                "revoked": "0",
                "metadata": json.dumps(token["metadata"]) if token["metadata"] else "{}"
            }
        )
        await redis_client.expire(f"token:{token['token_hash']}", settings.token_cache_ttl)

    logger.info(f"Cache warmed with {len(tokens)} active tokens")


app = FastAPI(
    title="AMPLIfy Auth Service",
    description="Token authentication service for AMPLIfy microservices",
    version=settings.service_version,
    lifespan=lifespan
)


# ============================================
# SECURITY DEPENDENCIES
# ============================================

async def verify_admin(authorization: str = Header(None)):
    """
    Verify admin access via bearer token.

    Required for all management endpoints (create, revoke, list tokens).
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    if token != settings.admin_token:
        raise HTTPException(
            status_code=403,
            detail="Invalid admin token"
        )

    return True


# ============================================
# VALIDATION ENDPOINTS (Read-Only, High Traffic)
# ============================================

@app.post("/auth/validate", response_model=ValidateTokenResponse, response_model_exclude_none=True)
async def validate_token(request: ValidateTokenRequest):
    """
    Validate a token and check scopes.

    This is the hot path - called on every authenticated request to microservices.
    It's read-only and highly concurrent (no race conditions).
    """
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()

    # STEP 1: Check revoked set (authoritative source)
    is_revoked = await redis_client.sismember("revoked_tokens", token_hash)
    if is_revoked:
        return ValidateTokenResponse(
            valid=False,
            error="token_revoked",
            detail="Token has been revoked"
        )

    # STEP 2: Try cache first
    cached = await redis_client.hgetall(f"token:{token_hash}")

    if cached:
        # Cache hit - validate from cached data
        return _validate_from_data(cached, request.required_scopes)

    # STEP 3: Cache miss - query database
    async with db_pool.acquire() as conn:
        token_data = await conn.fetchrow(
            """
            SELECT
                t.token_id,
                t.name,
                t.expires_at,
                t.revoked,
                t.metadata,
                array_agg(ts.scope) FILTER (WHERE ts.scope IS NOT NULL) as scopes
            FROM tokens t
            LEFT JOIN token_scopes ts ON t.token_id = ts.token_id
            WHERE t.token_hash = $1
            GROUP BY t.token_id
            """,
            token_hash
        )

    if not token_data:
        return ValidateTokenResponse(
            valid=False,
            error="token_not_found",
            detail="Invalid token"
        )

    # STEP 4: Populate cache for next time
    await redis_client.hset(
        f"token:{token_hash}",
        mapping={
            "token_id": str(token_data["token_id"]),
            "name": token_data["name"],
            "scopes": ",".join(token_data["scopes"]) if token_data["scopes"] else "",
            "expires_at": token_data["expires_at"].isoformat() if token_data["expires_at"] else "",
            "revoked": "1" if token_data["revoked"] else "0",
            "metadata": json.dumps(token_data["metadata"]) if token_data["metadata"] else "{}"
        }
    )
    await redis_client.expire(f"token:{token_hash}", settings.token_cache_ttl)

    # Validate from fetched data
    return _validate_from_data(
        {
            "token_id": str(token_data["token_id"]),
            "name": token_data["name"],
            "scopes": ",".join(token_data["scopes"]) if token_data["scopes"] else "",
            "expires_at": token_data["expires_at"].isoformat() if token_data["expires_at"] else "",
            "revoked": "1" if token_data["revoked"] else "0"
        },
        request.required_scopes
    )


def _validate_from_data(data: dict, required_scopes: list[str]) -> ValidateTokenResponse:
    """Helper to validate token from cached or fetched data."""
    # Check if revoked
    if data.get("revoked") == "1":
        return ValidateTokenResponse(
            valid=False,
            error="token_revoked",
            detail="Token has been revoked"
        )

    # Check expiration
    expires_at_str = data.get("expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at < datetime.now():
            return ValidateTokenResponse(
                valid=False,
                error="token_expired",
                detail=f"Token expired at {expires_at_str}"
            )

    # Check scopes
    token_scopes = data.get("scopes", "").split(",") if data.get("scopes") else []
    token_scopes = [s for s in token_scopes if s]  # Filter empty strings

    if required_scopes:
        missing_scopes = [s for s in required_scopes if s not in token_scopes]
        if missing_scopes:
            return ValidateTokenResponse(
                valid=False,
                error="insufficient_scopes",
                detail=f"Missing scopes: {missing_scopes}"
            )

    # Valid!
    return ValidateTokenResponse(
        valid=True,
        scopes=token_scopes,
        token_id=data.get("token_id"),
        name=data.get("name")
    )


# ============================================
# TOKEN MANAGEMENT ENDPOINTS (Write Operations via Command Queue)
# ============================================

@app.post("/auth/tokens", response_model=TokenResponse, status_code=201, dependencies=[Depends(verify_admin)])
async def create_token(request: CreateTokenRequest):
    """
    Create a new token.

    Submits a command to the single-writer queue to avoid race conditions.
    """
    try:
        result = await command_processor.submit_command(
            CommandType.CREATE_TOKEN,
            {
                "name": request.name,
                "scopes": request.scopes,
                "ttl_days": request.ttl_days,
                "metadata": request.metadata
            }
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result.get("detail", result["error"]))

        return TokenResponse(**result)

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Command processing timeout")


@app.post("/auth/tokens/{token_id}/revoke", response_model=RevokeTokenResponse, dependencies=[Depends(verify_admin)])
async def revoke_token(token_id: str, request: RevokeTokenRequest = None):
    """
    Revoke a token immediately.

    Submits a command to the single-writer queue.
    """
    # Validate UUID format
    try:
        UUID(token_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token_id format (must be a UUID)")

    try:
        result = await command_processor.submit_command(
            CommandType.REVOKE_TOKEN,
            {"token_id": token_id}
        )

        if "error" in result:
            status_code = 404 if result["error"] == "token_not_found" else 400
            raise HTTPException(status_code=status_code, detail=result.get("detail", result["error"]))

        return RevokeTokenResponse(**result)

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Command processing timeout")


@app.get("/auth/tokens", response_model=TokenListResponse, dependencies=[Depends(verify_admin)])
async def list_tokens(include_revoked: bool = False):
    """List all tokens (without the actual token values)."""
    async with db_pool.acquire() as conn:
        query = """
            SELECT
                t.token_id,
                t.name,
                t.created_at,
                t.expires_at,
                t.revoked,
                t.revoked_at,
                t.metadata,
                array_agg(ts.scope) FILTER (WHERE ts.scope IS NOT NULL) as scopes
            FROM tokens t
            LEFT JOIN token_scopes ts ON t.token_id = ts.token_id
        """

        if not include_revoked:
            query += " WHERE t.revoked = FALSE"

        query += " GROUP BY t.token_id ORDER BY t.created_at DESC"

        tokens = await conn.fetch(query)

    token_list = [
        TokenInfoResponse(
            token_id=str(t["token_id"]),
            name=t["name"],
            scopes=t["scopes"] if t["scopes"] else [],
            created_at=t["created_at"],
            expires_at=t["expires_at"],
            revoked=t["revoked"],
            revoked_at=t["revoked_at"],
            metadata=t["metadata"] if t["metadata"] else {}
        )
        for t in tokens
    ]

    return TokenListResponse(tokens=token_list, total=len(token_list))


@app.get("/auth/tokens/{token_id}", response_model=TokenInfoResponse, dependencies=[Depends(verify_admin)])
async def get_token(token_id: str):
    """Get information about a specific token."""
    # Validate UUID format
    try:
        UUID(token_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token_id format (must be a UUID)")

    async with db_pool.acquire() as conn:
        token = await conn.fetchrow(
            """
            SELECT
                t.token_id,
                t.name,
                t.created_at,
                t.expires_at,
                t.revoked,
                t.revoked_at,
                t.metadata,
                array_agg(ts.scope) FILTER (WHERE ts.scope IS NOT NULL) as scopes
            FROM tokens t
            LEFT JOIN token_scopes ts ON t.token_id = ts.token_id
            WHERE t.token_id = $1
            GROUP BY t.token_id
            """,
            token_id
        )

    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    return TokenInfoResponse(
        token_id=str(token["token_id"]),
        name=token["name"],
        scopes=token["scopes"] if token["scopes"] else [],
        created_at=token["created_at"],
        expires_at=token["expires_at"],
        revoked=token["revoked"],
        revoked_at=token["revoked_at"],
        metadata=token["metadata"] if token["metadata"] else {}
    )


# ============================================
# HEALTH & UTILITY ENDPOINTS
# ============================================

@app.get("/", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    components = {}

    # Check database
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        components["database"] = "healthy"
    except Exception as e:
        components["database"] = f"unhealthy: {str(e)}"

    # Check Redis
    try:
        await redis_client.ping()
        components["redis"] = "healthy"
    except Exception as e:
        components["redis"] = f"unhealthy: {str(e)}"

    # Check command processor
    components["command_processor"] = "running" if command_processor.running else "stopped"

    status = "healthy" if all(v == "healthy" or v == "running" for v in components.values()) else "degraded"

    return HealthResponse(
        status=status,
        version=settings.service_version,
        components=components
    )
