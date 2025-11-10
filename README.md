# AMPLIfy Stateless Microservices

This repo contains a library for quickly generating stateless microservices. It automates much of the boilerplate around REST API generation, S3 integration, and Apache web server configuration, so developers can focus on the logic behind their microservices. It includes an example image format conversion microservice.

## Building Stateless Services

1. Subclass `stateless_microservice.BaseProcessor` and implement `get_stateless_actions` to return `StatelessAction` descriptors (path, request model, handler, metadata).
2. Instantiate the API with `stateless_microservice.create_app(processor, ServiceConfig(...))`.
3. Use the helper utilities from `stateless_microservice.direct` when you need to read/write objects in the configured S3 bucket without managing boto3 boilerplate.
4. Copy the example Dockerfile/compose setup to deploy dedicated services (each service keeps its own dependencies and scale profile).
