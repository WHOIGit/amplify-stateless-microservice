# Stateless API Service

This repo contains a FastAPI toolkit for stateless microservices. It also includes an example image format conversion microservice.

## Building Stateless Services

1. Subclass `stateless_api_platform.BaseProcessor` and implement `get_stateless_actions` to return `StatelessAction` descriptors (path, request model, handler, metadata).
2. Instantiate the API with `stateless_api_platform.create_app(processor, ServiceConfig(...))`.
3. Use the helper utilities from `stateless_api_platform.direct` when you need to read/write objects in the configured S3 bucket without managing boto3 boilerplate.
4. Copy the example Dockerfile/compose setup to deploy dedicated services (each service keeps its own dependencies and scale profile).
