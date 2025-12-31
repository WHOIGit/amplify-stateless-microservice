# AMPLIfy Auth Service

Token-based authentication service for AMPLIfy microservices.

## Architecture

- **PostgreSQL** - Token storage
- **Redis** - Token cache
- **Command Queue** - Single-threaded write operations
- **FastAPI** - HTTP API for validation and management

## Usage

### 1. Start the auth infrastructure

```bash
cd infrastructure/auth-server
docker-compose --profile auth up -d
```

### 2. Token management via CLI

```bash
# Create a read-only token
docker-compose exec auth-service amplify-auth-cli \
  create readonly-token --scopes read --ttl 365

# Create a full-access token
docker-compose exec auth-service amplify-auth-cli \
  create admin-token --scopes read write delete admin

# List all tokens
docker-compose exec auth-service amplify-auth-cli list

# Get token details
docker-compose exec auth-service amplify-auth-cli info <token_id>

# Revoke a token
docker-compose exec auth-service amplify-auth-cli revoke <token_id>
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

Run the CLI via docker compose exec:

```bash
docker-compose exec auth-service amplify-auth-cli create mytoken --scopes read write
```

**Commands:**
- `create NAME --scopes SCOPE1 SCOPE2 [--ttl DAYS]` - Create a new token
- `list [--all]` - List tokens (--all includes revoked)
- `info TOKEN_ID` - Get token details
- `revoke TOKEN_ID` - Revoke a token immediately

## API Endpoints

### Validation (read-only for token-state)

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

### Management (via command queue)

**POST /auth/tokens** - Create token

**GET /auth/tokens** - List tokens

**GET /auth/tokens/{id}** - Get token info

**POST /auth/tokens/{id}/revoke** - Revoke token

See auto-generated docs at http://localhost:8000/docs

## Token Format

Tokens have the prefix `amp_live_` followed by 43 URL-safe characters:

```
amp_live_k7n2m9p4q8r1s5t3u6v0w7x2y9z4a1b3c5d7e9f2g4h6j8
```

Only the **SHA256 hash** is stored in the database -- never the raw token.

## Scopes

Common scopes:
- `read` - Read access
- `write` - Create/update access
- `delete` - Delete access
- `admin` - Administrative access

You may define your own scopes as needed. Each scope is represented by a string.

## Configuration

Available environment variables for docker-compose (`.env` file):

```bash
AUTH_SERVICE_PORT=8001  # Port that the auth API will be available on (default: 8000)
POSTGRES_PORT=5433      # PostgreSQL host port (default: 5432)
POSTGRES_DB=my_auth_db  # Database name (default: auth_db)
POSTGRES_USER=my_user   # Database user (default: auth_user)
POSTGRES_PASSWORD=my_pass  # Database password (default: auth_pass)
REDIS_PORT=6379         # Redis host port (default: 6379)
```

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
