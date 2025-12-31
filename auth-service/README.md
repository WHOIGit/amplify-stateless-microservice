# AMPLIfy Auth Service

Token-based authentication service for AMPLIfy microservices.

## Architecture

- **PostgreSQL** - Token storage
- **Redis** - Token cache
- **Command Queue** - Single-threaded write operations
- **FastAPI** - HTTP API for validation and management

## Quick Start

### 1. Start the auth infrastructure

```bash
cd auth-service
docker-compose --profile auth up -d
```

### 2. Create tokens

```bash
# Create a read-only token
docker-compose exec auth-service auth-cli \
  create readonly-token --scopes read --ttl 365

# Create a full-access token
docker-compose exec auth-service auth-cli \
  create admin-token --scopes read write delete admin

# List all tokens
docker-compose exec auth-service auth-cli list

# Get token details
docker-compose exec auth-service auth-cli info <token_id>

# Revoke a token
docker-compose exec auth-service auth-cli revoke <token_id>
```

### 3. Use tokens in your services

```python
from stateless_microservice import AuthClient, StatelessAction

# Define action with required scopes
StatelessAction(
    name="my_endpoint",
    path="/my-endpoint",
    handler=self.my_handler,
    required_scopes=["read", "write"]  # Requires both scopes
)
```

## CLI Usage

The CLI can be run from:

**Inside the container:**
```bash
docker-compose exec auth-service auth-cli create mytoken --scopes read write
```

**From your local machine:**
```bash
pip install -e /path/to/auth-service
auth-cli --auth-url http://localhost:8000 create mytoken --scopes read write
```

**Commands:**
- `create NAME --scopes SCOPE1 SCOPE2 [--ttl DAYS]` - Create a new token
- `list [--all]` - List tokens (--all includes revoked)
- `info TOKEN_ID` - Get token details
- `revoke TOKEN_ID` - Revoke a token immediately

## API Endpoints

### Validation (High-frequency, read-only)

**POST /auth/validate**
```json
{
  "token": "amp_live_...",
  "required_scopes": ["read", "write"]
}
```

Response:
```json
{
  "valid": true,
  "scopes": ["read", "write", "delete"],
  "token_id": "...",
  "name": "my-token"
}
```

### Management (Low-frequency, via command queue)

**POST /auth/tokens** - Create token
**GET /auth/tokens** - List tokens
**GET /auth/tokens/{id}** - Get token info
**POST /auth/tokens/{id}/revoke** - Revoke token

See auto-generated docs at http://localhost:8000/docs

## Race Condition Prevention

This auth service uses the **Single-Writer Pattern**:

1. All **write operations** (create, revoke, extend) go through a **single-threaded command queue**
2. All **read operations** (validate) are massively concurrent and read-only
3. **No race conditions** because only one thread modifies state at a time

### How it works:

```
Write Operations:          Read Operations:

API → Command Queue       API → Redis Cache → Response
       ↓                         ↓ (miss)
  Single Writer           PostgreSQL → Response
       ↓
  PostgreSQL
       ↓
  Redis Cache
       ↓
  Response
```

## Token Format

Tokens have the prefix `amp_live_` followed by 43 URL-safe characters:

```
amp_live_k7n2m9p4q8r1s5t3u6v0w7x2y9z4a1b3c5d7e9f2g4h6j8
```

Only the **SHA256 hash** is stored in the database (never the raw token).

## Scopes

Common scopes:
- `read` - Read access
- `write` - Create/update access
- `delete` - Delete access
- `admin` - Administrative access

Define your own scopes as needed - they're just strings!

## Configuration

Environment variables (`.env` or docker-compose):

```bash
DATABASE_URL=postgresql://auth_user:auth_pass@postgres:5432/auth_db
REDIS_URL=redis://redis:6379/0
TOKEN_CACHE_TTL=1800  # 30 minutes (cache duration)
PORT=8000             # Auth service port (default: 8000)
```

To change ports and database credentials in docker-compose:

```bash
cd auth-service

# Set via environment variables
AUTH_SERVICE_PORT=8001 \
POSTGRES_PORT=5433 \
POSTGRES_DB=my_auth_db \
POSTGRES_USER=my_user \
POSTGRES_PASSWORD=my_pass \
docker-compose --profile auth up -d

# Or create a .env file in auth-service/
cat > .env <<EOF
AUTH_SERVICE_PORT=8001
POSTGRES_PORT=5433
POSTGRES_DB=my_auth_db
POSTGRES_USER=my_user
POSTGRES_PASSWORD=my_pass
REDIS_PORT=6379
EOF
docker-compose --profile auth up -d
```

Available docker-compose environment variables:
- `AUTH_SERVICE_PORT` - Auth service port (default: 8000)
- `POSTGRES_PORT` - PostgreSQL host port (default: 5432)
- `POSTGRES_DB` - Database name (default: auth_db)
- `POSTGRES_USER` - Database user (default: auth_user)
- `POSTGRES_PASSWORD` - Database password (default: auth_pass)
- `REDIS_PORT` - Redis host port (default: 6379)

## Security Notes

- Tokens are shown **only once** when created
- Only SHA256 hashes are stored in the database
- Revoked tokens are cached in Redis for fast rejection
- All validation is read-only (no side effects)
- Admin operations should be protected (network-level or admin tokens)

## Monitoring

Health check: `GET /health`

Returns:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "command_processor": "running"
  }
}
```

## Running Example Services

### Example: Authenticated Service

To run the authenticated service example against the auth infrastructure:

```bash
# 1. Make sure auth infrastructure is running
cd auth-service
docker-compose --profile auth up -d

# 2. Build and run the authenticated service
cd ../examples/authenticated_service
docker build -t authenticated-service .
docker run -p 8002:8000 \
  --network auth-service_amplify-net \
  -e AUTH_SERVICE_URL=http://auth-service:8000 \
  authenticated-service
```
