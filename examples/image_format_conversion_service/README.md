# Image Format Conversion Stateless Service

Stateless FastAPI service that exposes one helper endpoint:

- `POST /media/image/convert` — Fetch an image from S3, optionally convert mode, and re-encode to a new format.

The service demonstrates how to use `StatelessAction` descriptors with the `stateless_microservice` factory to expose immediate responses.

## Request Example

```bash
# Convert an image from TIFF to PNG
curl -X POST http://localhost:8010/media/image/convert \
  -H "Content-Type: application/json" \
  --output frame.png \
  -d '{
        "source_uri": "s3://media-tools/examples/sample.tiff",
        "target_format": "png"
      }'
```

## Run with Docker Compose

```bash
cd examples/image_format_conversion_service
cp .env.example .env    # edit with your S3 credentials
docker compose up --build
```
