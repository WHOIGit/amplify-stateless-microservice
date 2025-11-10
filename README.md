# AMPLIfy Stateless Microservices

This repo contains a library for quickly generating stateless microservices. It automates much of the boilerplate around REST API generation, S3 integration, and Apache web server configuration, so developers can focus on the logic behind their microservices. It includes an example image format conversion microservice.

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
2. Instantiate the API with `stateless_microservice.create_app(processor, ServiceConfig(...))`.

    ```python
    from stateless_microservice import ServiceConfig, create_app

    app = create_app(
        MyProcessor(),
        ServiceConfig(description="My stateless service."),
    )
    ```
3. Use the helper utilities from `stateless_microservice.direct` when you need to read/write objects in the configured S3 bucket without managing boto3 boilerplate.
4. Copy the example Dockerfile/compose setup to deploy dedicated services (each service keeps its own dependencies and scale profile).
