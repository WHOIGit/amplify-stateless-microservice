# AMPLIfy Stateless Microservices

This repo contains a library for quickly generating stateless microservices. It automates much of the boilerplate around REST API generation, S3 integration, and Apache web server configuration, so developers can focus on the logic behind their microservices. It includes:

- `examples/image_format_conversion_service`: converts S3-hosted images between formats.
- `examples/base64_grayscale_service`: converts a base64 image payload to grayscale without using S3

## Building Stateless Services

1. Subclass `stateless_microservice.BaseProcessor` and implement `get_stateless_actions` to return `StatelessAction` descriptors (path, request model, handler, metadata).

    ```python
    from typing import List
    from pydantic import BaseModel
    from stateless_microservice import BaseProcessor, StatelessAction

    class MyRequest(BaseModel):
        payload: str

    class MyProcessor(BaseProcessor):
        @property
        def name(self) -> str:
            # Return a short identifier for logs and metrics.
            return "my-service"

        def get_stateless_actions(self) -> List[StatelessAction]:
            # Describe the FastAPI routes exposed by this processor.
            return [
                StatelessAction(
                    name="my_action",
                    path="/action-name",
                    request_model=MyRequest,
                    handler=self.handle_my_action,
                ),
            ]

        async def handle_my_action(self, request: MyRequest):
            # Implement the stateless logic here.
            return {"echo": request.payload}
    ```

    **With path parameters:**
    ```python
    class PathParams(BaseModel):
        user_id: str

    StatelessAction(
        name="get_user",
        path="/users/{user_id}",
        request_model=MyRequest,
        path_params_model=PathParams,  # Path parameters
        handler=self.handle_get_user,
    )

    async def handle_get_user(self, request: MyRequest, path_params: PathParams):
        return {"user_id": path_params.user_id, "data": request.payload}
    ```

    **With custom response model:**
    ```python
    class MyResponse(BaseModel):
        result: str
        count: int

    StatelessAction(
        name="my_action",
        path="/action-name",
        request_model=MyRequest,
        response_model=MyResponse,  # Custom response
        handler=self.handle_my_action,
    )

    async def handle_my_action(self, request: MyRequest) -> MyResponse:
        return MyResponse(result=request.payload, count=len(request.payload))
    ```

2. Instantiate the API with `stateless_microservice.create_app(processor, ServiceConfig(...))`.

    ```python
    from stateless_microservice import ServiceConfig, create_app

    app = create_app(
        MyProcessor(),
        ServiceConfig(description="My stateless service."),
    )
    ```
3. Use the helper utilities from `stateless_microservice.direct` when you need to read/write objects in the configured S3 bucket without managing boto3 boilerplate.

    ```python
    from stateless_microservice.direct import (
        fetch_s3_bytes,
        render_bytes,
        run_blocking,
    )

    await fetch_s3_bytes("s3://bucket/key")  # Read object bytes with shared client/session.
    render_bytes(b"...", media_type="image/png")  # Wrap raw bytes for FastAPI responses.
    await run_blocking(callable_fn)  # Offload CPU-bound work to a thread pool.
    ```
4. Copy the example Dockerfile/compose setup to deploy dedicated services (each service keeps its own dependencies and scale profile).
   
    ```
    my-stateless-service/
    ├── docker-compose.yml
    ├── Dockerfile
    ├── pyproject.toml          # Declares dependencies (including amplify-stateless)
    └── my_stateless_service/   # Python package for your processor + entrypoint
        ├── __init__.py
        ├── processor.py        # Subclass of BaseProcessor with StatelessAction definitions
        └── main.py             # create_app + uvicorn entrypoint
    ```

## Aggregating API Documentation

Use `aggregate_openapi.py` to combine OpenAPI specs from multiple microservices into a single Swagger UI.

**IMPORTANT:** Service URLs must use the same public hostname to enable "Try it out" functionality in Swagger UI/ReDoc.

**Basic usage:**
```bash
python aggregate_openapi.py https://hostname/service1 https://hostname/service2
# Access at http://localhost:8000/docs
```

**Behind Apache reverse proxy:**
```bash
python aggregate_openapi.py https://hostname/service1 https://hostname/service2 \
  --path /api-docs --port 8080 --apache-config --hostname hostname
# Copy the printed Apache config into your Apache configuration
# Access at https://hostname/api-docs/docs
```
