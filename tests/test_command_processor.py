"""Tests for command processor."""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
import asyncio

from stateless_microservice.auth_service.commands import CommandProcessor, CommandType


@pytest.fixture
def mock_db_pool():
    """Mock database pool."""
    pool = Mock()
    conn = AsyncMock()

    # Create proper async context manager for pool.acquire()
    class MockAcquireContext:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    # Make acquire() return the context manager (not async)
    pool.acquire = Mock(return_value=MockAcquireContext())

    # Create proper async context manager for conn.transaction()
    class MockTransactionContext:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    # Make transaction() return the context manager (not async)
    conn.transaction = Mock(return_value=MockTransactionContext())

    return pool, conn


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return AsyncMock()


# ============================================
# Command Creation Tests
# ============================================

@pytest.mark.asyncio
async def test_create_token_command(mock_db_pool, mock_redis):
    """Test token creation through command processor."""
    pool, conn = mock_db_pool

    # Mock database responses
    token_id = "abc-123-def-456"
    created_at = datetime.now()
    conn.fetchval.side_effect = [token_id, created_at]

    processor = CommandProcessor(pool, mock_redis, cache_ttl=1800)

    result = await processor._create_token({
        "name": "test-token",
        "scopes": ["read", "write"],
        "ttl_days": 30,
        "metadata": {"env": "prod"}
    })

    # Verify token was generated correctly
    assert "token" in result
    assert result["token"].startswith("amp_live_")
    assert len(result["token"]) > 20  # Should be reasonably long

    # Verify response contains expected fields
    assert result["name"] == "test-token"
    assert result["scopes"] == ["read", "write"]
    assert result["token_id"] == token_id

    # Verify DB insert was called
    assert conn.fetchval.called
    assert conn.executemany.called  # For scopes

    # Verify cache write
    assert mock_redis.hset.called
    assert mock_redis.expire.called


@pytest.mark.asyncio
async def test_create_token_no_expiration(mock_db_pool, mock_redis):
    """Test creating a permanent token (no TTL)."""
    pool, conn = mock_db_pool

    token_id = "permanent-123"
    created_at = datetime.now()
    conn.fetchval.side_effect = [token_id, created_at]

    processor = CommandProcessor(pool, mock_redis)

    result = await processor._create_token({
        "name": "permanent-token",
        "scopes": ["admin"],
        "ttl_days": None,
        "metadata": {}
    })

    assert result["expires_at"] is None
    assert result["name"] == "permanent-token"

    # Check that DB was called with None for expires_at
    # Parameters: (query, token_hash, name, expires_at, metadata)
    call_args = conn.fetchval.call_args_list[0]
    assert call_args[0][3] is None  # expires_at parameter (index 3)


@pytest.mark.asyncio
async def test_create_token_empty_scopes(mock_db_pool, mock_redis):
    """Test creating a token with no scopes."""
    pool, conn = mock_db_pool

    token_id = "no-scopes-123"
    created_at = datetime.now()
    conn.fetchval.side_effect = [token_id, created_at]

    processor = CommandProcessor(pool, mock_redis)

    result = await processor._create_token({
        "name": "no-scopes-token",
        "scopes": [],
        "ttl_days": None,
        "metadata": {}
    })

    assert result["scopes"] == []

    # executemany should not be called for empty scopes
    assert not conn.executemany.called


@pytest.mark.asyncio
async def test_create_token_cache_ttl(mock_db_pool, mock_redis):
    """Test that cache TTL is set correctly."""
    pool, conn = mock_db_pool

    token_id = "cache-test-123"
    created_at = datetime.now()
    conn.fetchval.side_effect = [token_id, created_at]

    custom_ttl = 3600
    processor = CommandProcessor(pool, mock_redis, cache_ttl=custom_ttl)

    await processor._create_token({
        "name": "test-token",
        "scopes": ["read"],
        "ttl_days": None,
        "metadata": {}
    })

    # Verify expire was called with custom TTL
    mock_redis.expire.assert_called()
    expire_call = mock_redis.expire.call_args
    assert expire_call[0][1] == custom_ttl


# ============================================
# Command Revocation Tests
# ============================================

@pytest.mark.asyncio
async def test_revoke_token_command(mock_db_pool, mock_redis):
    """Test token revocation."""
    pool, conn = mock_db_pool

    revoked_at = datetime.now()
    conn.fetchrow.return_value = {
        "token_hash": "abc123hash",
        "revoked_at": revoked_at
    }

    processor = CommandProcessor(pool, mock_redis)

    result = await processor._revoke_token({"token_id": "token-123"})

    assert result["success"] is True
    assert result["token_id"] == "token-123"
    assert "revoked_at" in result

    # Verify DB update was called
    assert conn.fetchrow.called

    # Verify cache invalidation
    mock_redis.delete.assert_called_once()
    delete_call = mock_redis.delete.call_args
    assert "abc123hash" in delete_call[0][0]

    # Verify token added to revoked set
    mock_redis.sadd.assert_called_once_with("revoked_tokens", "abc123hash")


@pytest.mark.asyncio
async def test_revoke_token_not_found(mock_db_pool, mock_redis):
    """Test revoking non-existent token."""
    pool, conn = mock_db_pool

    # Database returns None (token not found)
    conn.fetchrow.return_value = None

    processor = CommandProcessor(pool, mock_redis)

    result = await processor._revoke_token({"token_id": "nonexistent-123"})

    assert "error" in result
    assert result["error"] == "token_not_found"
    assert "nonexistent-123" in result["detail"]

    # Cache should not be modified
    assert not mock_redis.delete.called
    assert not mock_redis.sadd.called


# ============================================
# Command Extension Tests
# ============================================

@pytest.mark.asyncio
async def test_extend_token_command(mock_db_pool, mock_redis):
    """Test token expiration extension."""
    pool, conn = mock_db_pool

    new_expiry = datetime.now() + timedelta(days=60)
    conn.fetchrow.return_value = {
        "token_hash": "def456hash",
        "expires_at": new_expiry
    }

    processor = CommandProcessor(pool, mock_redis)

    result = await processor._extend_token({
        "token_id": "token-123",
        "extend_days": 30
    })

    assert result["success"] is True
    assert "expires_at" in result

    # Verify DB update was called with correct parameters
    assert conn.fetchrow.called
    call_args = conn.fetchrow.call_args
    assert call_args[0][1] == "token-123"
    assert call_args[0][2] == 30  # extend_days

    # Verify cache invalidation
    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_extend_token_not_found(mock_db_pool, mock_redis):
    """Test extending non-existent token."""
    pool, conn = mock_db_pool

    conn.fetchrow.return_value = None

    processor = CommandProcessor(pool, mock_redis)

    result = await processor._extend_token({
        "token_id": "nonexistent-123",
        "extend_days": 30
    })

    assert "error" in result
    assert result["error"] == "token_not_found"

    # Cache should not be modified
    assert not mock_redis.delete.called


# ============================================
# Command Queue Processing Tests
# ============================================

@pytest.mark.asyncio
async def test_submit_command_create_token(mock_db_pool, mock_redis):
    """Test submitting a create token command."""
    pool, conn = mock_db_pool

    # Mock the command queue
    response_data = {
        "token": "amp_live_test123",
        "token_id": "id-123",
        "name": "test-token",
        "scopes": ["read"],
        "created_at": datetime.now().isoformat(),
        "expires_at": None
    }

    # Mock redis.get to return the response after first call
    mock_redis.get.side_effect = [None, json.dumps(response_data)]

    processor = CommandProcessor(pool, mock_redis)

    result = await processor.submit_command(
        CommandType.CREATE_TOKEN,
        {"name": "test-token", "scopes": ["read"]}
    )

    # Verify command was pushed to queue
    mock_redis.rpush.assert_called_once()
    call_args = mock_redis.rpush.call_args
    assert call_args[0][0] == "auth:commands"

    # Verify result was retrieved
    assert result["token"] == "amp_live_test123"


@pytest.mark.asyncio
async def test_submit_command_timeout(mock_db_pool, mock_redis):
    """Test command submission timeout."""
    pool, _ = mock_db_pool

    # Redis never returns a result
    mock_redis.get.return_value = None

    processor = CommandProcessor(pool, mock_redis)

    with pytest.raises(TimeoutError):
        await processor.submit_command(
            CommandType.CREATE_TOKEN,
            {"name": "test-token", "scopes": ["read"]}
        )


@pytest.mark.asyncio
async def test_process_command_unknown_type(mock_db_pool, mock_redis):
    """Test processing unknown command type."""
    pool, _ = mock_db_pool

    processor = CommandProcessor(pool, mock_redis)

    command = {
        "type": "unknown_command",
        "data": {},
        "response_key": "test:response:123"
    }

    await processor._process_command(command)

    # Should set error response
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args
    response = json.loads(call_args[0][2])
    assert response["error"] == "unknown_command"


@pytest.mark.asyncio
async def test_process_command_exception_handling(mock_db_pool, mock_redis):
    """Test that exceptions in command processing are handled."""
    pool, conn = mock_db_pool

    # Make the DB call raise an exception
    conn.fetchval.side_effect = Exception("Database error")

    processor = CommandProcessor(pool, mock_redis)

    command = {
        "type": CommandType.CREATE_TOKEN.value,
        "data": {"name": "test", "scopes": ["read"]},
        "response_key": "test:response:123"
    }

    await processor._process_command(command)

    # Should publish error response
    mock_redis.setex.assert_called()
    call_args = mock_redis.setex.call_args
    response = json.loads(call_args[0][2])
    assert response["error"] == "command_failed"
    assert "Database error" in response["detail"]


# ============================================
# Processor Lifecycle Tests
# ============================================

@pytest.mark.asyncio
async def test_processor_start_stop(mock_db_pool, mock_redis):
    """Test starting and stopping the processor."""
    pool, _ = mock_db_pool

    # Mock BLPOP to return None (no commands)
    mock_redis.blpop.return_value = None

    processor = CommandProcessor(pool, mock_redis)

    assert processor.running is False

    await processor.start()
    assert processor.running is True
    assert processor._task is not None

    await processor.stop()
    assert processor.running is False


@pytest.mark.asyncio
async def test_processor_start_already_running(mock_db_pool, mock_redis):
    """Test starting processor when already running."""
    pool, _ = mock_db_pool

    mock_redis.blpop.return_value = None

    processor = CommandProcessor(pool, mock_redis)

    await processor.start()
    first_task = processor._task

    # Try starting again
    await processor.start()

    # Should still be the same task
    assert processor._task == first_task

    await processor.stop()


@pytest.mark.asyncio
async def test_process_loop_handles_commands(mock_db_pool, mock_redis):
    """Test that the process loop handles commands from the queue."""
    pool, conn = mock_db_pool

    token_id = "test-123"
    created_at = datetime.now()
    conn.fetchval.side_effect = [token_id, created_at]

    command = {
        "type": CommandType.CREATE_TOKEN.value,
        "data": {"name": "test", "scopes": ["read"], "ttl_days": None, "metadata": {}},
        "response_key": "test:response:123"
    }

    # BLPOP returns command once, then None (to allow loop to exit)
    mock_redis.blpop.side_effect = [
        ("auth:commands", json.dumps(command)),
        None
    ]

    processor = CommandProcessor(pool, mock_redis)

    await processor.start()

    # Wait briefly for command to be processed
    await asyncio.sleep(0.1)

    await processor.stop()

    # Verify command was processed
    assert mock_redis.setex.called  # Response was published


@pytest.mark.asyncio
async def test_process_loop_handles_errors(mock_db_pool, mock_redis):
    """Test that the process loop continues after errors."""
    pool, _ = mock_db_pool

    # First BLPOP raises exception, second returns None
    mock_redis.blpop.side_effect = [
        Exception("Redis error"),
        None
    ]

    processor = CommandProcessor(pool, mock_redis)

    await processor.start()

    # Wait briefly
    await asyncio.sleep(0.1)

    await processor.stop()

    # Should not crash - loop should continue


# ============================================
# Token Hash Generation Tests
# ============================================

@pytest.mark.asyncio
async def test_create_token_hash_consistency(mock_db_pool, mock_redis):
    """Test that token hash is generated correctly."""
    pool, conn = mock_db_pool

    token_id = "test-123"
    created_at = datetime.now()
    conn.fetchval.side_effect = [token_id, created_at]

    processor = CommandProcessor(pool, mock_redis)

    result = await processor._create_token({
        "name": "test-token",
        "scopes": ["read"],
        "ttl_days": None,
        "metadata": {}
    })

    # Get the token
    token = result["token"]

    # Verify hash was used in cache key
    hset_call = mock_redis.hset.call_args
    cache_key = hset_call[0][0]
    assert cache_key.startswith("token:")

    # The hash should be deterministic for the same token
    import hashlib
    expected_hash = hashlib.sha256(token.encode()).hexdigest()
    assert cache_key == f"token:{expected_hash}"


# ============================================
# Cache Writing Tests
# ============================================

@pytest.mark.asyncio
async def test_create_token_cache_format(mock_db_pool, mock_redis):
    """Test that token is cached with correct format."""
    pool, conn = mock_db_pool

    token_id = "test-123"
    created_at = datetime.now()
    expires_at = datetime.now() + timedelta(days=30)

    conn.fetchval.side_effect = [token_id, created_at]

    processor = CommandProcessor(pool, mock_redis)

    await processor._create_token({
        "name": "test-token",
        "scopes": ["read", "write"],
        "ttl_days": 30,
        "metadata": {"key": "value"}
    })

    # Check cache write
    hset_call = mock_redis.hset.call_args
    cache_data = hset_call[1]["mapping"]

    assert cache_data["token_id"] == str(token_id)
    assert cache_data["name"] == "test-token"
    assert cache_data["scopes"] == "read,write"
    assert cache_data["revoked"] == "0"
    assert '"key": "value"' in cache_data["metadata"]
