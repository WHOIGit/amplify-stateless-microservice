# String Appender Service

Example stateless microservice that demonstrates path parameter usage. This service takes two strings from the URL path and returns them concatenated together.

## API

### GET /append/{first}/{second}

Appends two path parameters together.

**Example:**
```bash
curl http://localhost:8030/append/hello/world
```

Response:
```json
{
  "result": "helloworld"
}
```

## Running

```bash
docker-compose up --build
```

The service will be available at `http://localhost:8030`.
