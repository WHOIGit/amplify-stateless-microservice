"""Command processor for serialized write operations.

This module implements the single-writer pattern to eliminate race conditions.
All write operations (create, revoke, extend) go through a single command queue
that is processed serially by one async task.
"""

import asyncio
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import asyncpg
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class CommandType(str, Enum):
    """Types of commands that can be queued."""
    CREATE_TOKEN = "create_token"
    REVOKE_TOKEN = "revoke_token"
    EXTEND_TOKEN = "extend_token"


class CommandProcessor:
    """
    Single-threaded command processor for all write operations.

    This ensures all database and cache modifications happen serially,
    eliminating race conditions between concurrent operations.
    """

    def __init__(self, db_pool: asyncpg.Pool, redis_client: redis.Redis, cache_ttl: int = 1800):
        self.db = db_pool
        self.redis = redis_client
        self.cache_ttl = cache_ttl
        self.running = False
        self._task = None

    async def start(self):
        """Start the command processor background task."""
        if self.running:
            logger.warning("Command processor already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Command processor started")

    async def stop(self):
        """Stop the command processor."""
        self.running = False
        if self._task:
            await self._task
        logger.info("Command processor stopped")

    async def _process_loop(self):
        """Main processing loop - runs continuously."""
        logger.info("Command processor loop started")

        while self.running:
            try:
                # BLPOP blocks until a command is available (or timeout)
                result = await self.redis.blpop("auth:commands", timeout=1)

                if result:
                    _, command_json = result
                    command = json.loads(command_json)

                    # Process the command serially
                    await self._process_command(command)

            except Exception as e:
                logger.error(f"Error in command processor loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # Brief pause on error

    async def _process_command(self, command: dict[str, Any]):
        """
        Process a single command.

        Since this is the only place that writes to the database and cache,
        there are no race conditions.
        """
        cmd_type = command.get("type")
        data = command.get("data", {})
        response_key = command.get("response_key")

        logger.info(f"Processing command: {cmd_type}")

        try:
            if cmd_type == CommandType.CREATE_TOKEN:
                result = await self._create_token(data)
            elif cmd_type == CommandType.REVOKE_TOKEN:
                result = await self._revoke_token(data)
            elif cmd_type == CommandType.EXTEND_TOKEN:
                result = await self._extend_token(data)
            else:
                result = {"error": "unknown_command", "detail": f"Unknown command type: {cmd_type}"}

            # Publish result to response key
            await self.redis.setex(
                response_key,
                30,  # Response available for 30 seconds
                json.dumps(result, default=str)  # default=str handles datetime serialization
            )

            logger.info(f"Command {cmd_type} completed successfully")

        except Exception as e:
            logger.error(f"Error processing command {cmd_type}: {e}", exc_info=True)

            # Publish error
            await self.redis.setex(
                response_key,
                30,
                json.dumps({"error": "command_failed", "detail": str(e)})
            )

    async def _create_token(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new token.

        No race conditions because:
        1. We're the only writer
        2. Database constraints prevent duplicates
        3. Cache write happens after DB write
        """
        name = data["name"]
        scopes = data["scopes"]
        ttl_days = data.get("ttl_days")
        metadata = data.get("metadata", {})

        # Generate token
        token = f"amp_live_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Calculate expiration
        expires_at = None
        if ttl_days is not None:
            expires_at = datetime.now() + timedelta(days=ttl_days)

        # Insert into database
        async with self.db.acquire() as conn:
            async with conn.transaction():
                # Insert token
                token_id = await conn.fetchval(
                    """
                    INSERT INTO tokens (token_hash, name, expires_at, metadata)
                    VALUES ($1, $2, $3, $4)
                    RETURNING token_id
                    """,
                    token_hash, name, expires_at, metadata
                )

                # Insert scopes
                if scopes:
                    await conn.executemany(
                        "INSERT INTO token_scopes (token_id, scope) VALUES ($1, $2)",
                        [(token_id, scope) for scope in scopes]
                    )

                # Get created_at timestamp
                created_at = await conn.fetchval(
                    "SELECT created_at FROM tokens WHERE token_id = $1",
                    token_id
                )

        # Write to cache (write-through caching)
        await self.redis.hset(
            f"token:{token_hash}",
            mapping={
                "token_id": str(token_id),
                "name": name,
                "scopes": ",".join(scopes) if scopes else "",
                "expires_at": expires_at.isoformat() if expires_at else "",
                "revoked": "0",
                "metadata": json.dumps(metadata)
            }
        )
        await self.redis.expire(f"token:{token_hash}", self.cache_ttl)

        logger.info(f"Created token: {name} (id={token_id})")

        return {
            "token": token,
            "token_id": str(token_id),
            "name": name,
            "scopes": scopes,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None
        }

    async def _revoke_token(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Revoke a token.

        No race conditions because:
        1. We're the only writer
        2. DB update happens first
        3. Cache invalidation happens after
        4. Revoked set is append-only
        """
        token_id = data["token_id"]

        # Update database
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                """
                UPDATE tokens
                SET revoked = TRUE, revoked_at = NOW()
                WHERE token_id = $1
                RETURNING token_hash, revoked_at
                """,
                token_id
            )

        if not result:
            return {"error": "token_not_found", "detail": f"Token {token_id} not found"}

        token_hash = result["token_hash"]
        revoked_at = result["revoked_at"]

        # Invalidate cache
        await self.redis.delete(f"token:{token_hash}")

        # Add to revoked set (authoritative source for revocations)
        await self.redis.sadd("revoked_tokens", token_hash)

        logger.info(f"Revoked token: {token_id}")

        return {
            "success": True,
            "token_id": token_id,
            "revoked_at": revoked_at.isoformat()
        }

    async def _extend_token(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Extend token expiration.

        No race conditions because:
        1. We're the only writer
        2. Database does atomic calculation
        3. Cache invalidation forces refresh
        """
        token_id = data["token_id"]
        extend_days = data["extend_days"]

        # Atomic update in database
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                """
                UPDATE tokens
                SET expires_at = COALESCE(expires_at, NOW()) + INTERVAL '1 day' * $2
                WHERE token_id = $1
                RETURNING token_hash, expires_at
                """,
                token_id, extend_days
            )

        if not result:
            return {"error": "token_not_found", "detail": f"Token {token_id} not found"}

        token_hash = result["token_hash"]
        expires_at = result["expires_at"]

        # Invalidate cache to force refresh with new expiration
        await self.redis.delete(f"token:{token_hash}")

        logger.info(f"Extended token: {token_id} to {expires_at}")

        return {
            "success": True,
            "token_id": token_id,
            "expires_at": expires_at.isoformat()
        }

    async def submit_command(self, cmd_type: CommandType, data: dict[str, Any]) -> dict[str, Any]:
        """
        Submit a command and wait for the result.

        This is called by API endpoints to queue write operations.
        """
        # Generate unique response key
        response_key = f"response:{secrets.token_urlsafe(16)}"

        # Create command
        command = {
            "type": cmd_type.value,
            "data": data,
            "response_key": response_key
        }

        # Push to queue
        await self.redis.rpush("auth:commands", json.dumps(command))

        # Wait for response (with timeout)
        max_wait = 50  # 5 seconds
        for _ in range(max_wait):
            result = await self.redis.get(response_key)
            if result:
                return json.loads(result)
            await asyncio.sleep(0.1)

        # Timeout
        raise TimeoutError("Command processing timeout")
