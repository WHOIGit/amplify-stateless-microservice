"""FastAPI entrypoint for the image format conversion stateless service."""

from stateless_microservice import ServiceConfig, create_app

from .processor import ImageConvertProcessor

config = ServiceConfig(
    description="Instant image format conversions over S3 assets.",
)

app = create_app(ImageConvertProcessor(), config)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)
