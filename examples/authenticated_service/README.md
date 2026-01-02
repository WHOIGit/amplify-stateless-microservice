# Authenticated Service Example

This example demonstrates an AMPLIfy microservice with token authentication.

## Running the Example

### 1. Start the auth infrastructure

```bash
# From repo root
cd infrastructure/auth-server
docker-compose up -d
```

This starts:
- PostgreSQL (token storage)
- Redis (token cache)
- Auth service (token validation API)

### 2. Create a token

```bash
# From infrastructure/auth-server directory
cd infrastructure/auth-server

# Create a token with 'read' scope
docker-compose exec auth-service amplify-auth-cli \
  create my-token --scopes read --ttl 365

# Create an admin token
docker-compose exec auth-service amplify-auth-cli \
  create admin-token --scopes read write admin --ttl 365
```

### 3. Start the authenticated service

```bash
# Build from repo root (required for accessing library code)
cd ../..
docker build -t authenticated-service -f examples/authenticated_service/Dockerfile .

# Run connected to the auth network
docker run -p 8002:8000 \
  --network auth-server_amplify-net \
  -e AUTH_SERVICE_URL=http://auth-service:8000 \
  authenticated-service
```

### 4. Test the endpoints

```bash
# Public endpoint (no auth)
curl http://localhost:8002/public

# Protected endpoint (requires token)
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}' \
  http://localhost:8002/echo

# Admin endpoint (requires 'admin' scope)
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN_HERE" \
  http://localhost:8002/admin/secret
```

## Code Overview

### Define Scopes on Actions

```python
StatelessAction(
    name="echo",
    path="/echo",
    handler=self.echo_message,
    required_scopes=["read"]  # Requires 'read' scope
)
```

### Access Token Info in Handler

```python
def echo_message(self, request: EchoRequest, token_info) -> EchoResponse:
    # token_info contains: name, scopes, token_id
    return EchoResponse(
        message=f"Echo: {request.message}",
        authenticated_as=token_info.name,
        scopes=token_info.scopes
    )
```

### Integration in main.py

```python
from stateless_microservice import create_app, AuthClient

auth_client = AuthClient(auth_service_url="http://auth-service:8000")

# Pass auth_client to create_app to enable authentication
app = create_app(
    processor=processor,
    config=config,
    auth_client=auth_client
)
```

Auth is automatically applied to routes based on `required_scopes`.

## Available Scopes

- `read` - Read access to resources
- `write` - Create/update resources
- `delete` - Delete resources
- `admin` - Administrative operations

You may define your own scopes as needed.
