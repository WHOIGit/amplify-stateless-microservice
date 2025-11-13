# Base64 Grayscale Example

This minimal service shows how to use the `stateless_microservice` toolkit without any S3 dependencies. It exposes a single FastAPI endpoint:

- `POST /image/grayscale` — Accepts a base64-encoded image payload and returns a base64-encoded grayscale PNG.

The processor decodes the supplied image locally, runs Pillow's grayscale conversion, and re-encodes the result, so it works in offline environments.

## Quickstart (Docker)

```bash
cd examples/base64_grayscale_service
docker compose up --build
```

## Helper Script

With the service running on `localhost:8020`, you can send images using the bundled script:

```bash
python grayscale_client.py path/to/input.jpg --output grayscale.png
# You can point at a different host/port; the script fills in /image/grayscale if missing.
python grayscale_client.py apple.jpg --url http://127.0.0.1:8020
```

## Sample Request

```bash
curl -X POST http://localhost:8020/image/grayscale \
  -H "Content-Type: application/json" \
  -d '{"image_b64": "<base64-bytes-here>"}'
```

The response contains a single `grayscale_b64` field that you can pipe through `base64 --decode > output.png` to inspect the grayscale image.
