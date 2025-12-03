"""FastAPI application factory for stateless request/response services."""

import inspect
import logging
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Response

from .models import ErrorResponse, HealthResponse
from .processor import BaseProcessor, StatelessAction

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """
    Configuration for building a stateless microservice application.

    Args:
        name: Override service name (defaults to processor.name)
        version: Override service version (defaults to processor.version)
        description: Short description for generated docs
    """

    name: str | None = None
    version: str | None = None
    description: str | None = None


def create_app(processor: BaseProcessor, config: ServiceConfig | None = None) -> FastAPI:
    """
    Create a FastAPI application for a stateless processor.
    """

    config = config or ServiceConfig()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    service_name = config.name or processor.name
    service_version = config.version or processor.version
    service_description = config.description or f"{service_name} stateless API"

    app = FastAPI(
        title=f"{service_name.title()} Stateless API",
        description=service_description,
        version=service_version,
    )

    app.state.processor = processor
    app.state.service_config = config

    @app.get("/", response_model=HealthResponse)
    async def root():
        return HealthResponse(status="healthy", version=service_version)

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        return HealthResponse(status="healthy", version=service_version)

    actions = processor.get_stateless_actions()
    if not actions:
        logger.warning(
            "Processor %s registered with stateless service but get_stateless_actions() returned nothing.",
            processor.name,
        )

    def make_endpoint(action: StatelessAction):
        RequestModel = action.request_model
            
        # Payload only
        async def endpoint(payload: RequestModel):
            call_result = action.handler(payload)

            if inspect.isawaitable(call_result):
                call_result = await call_result
            if isinstance(result, Response):
                return call_result
            if action.media_type and isinstance(call_result, (bytes, bytearray, memoryview)):
                return Response(content=bytes(call_result), media_type=action.media_type)
            return call_result

        return endpoint

    for action in actions:
        logger.info("Registering stateless action '%s' at %s", action.name, action.path)
        endpoint = make_endpoint(action)

        route_kwargs = {
            "methods": list(action.methods),
            "response_model": action.response_model,
            "summary": action.summary,
            "description": action.description,
            "tags": list(action.tags) if action.tags else None,
            "responses": {400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
        }
        route_kwargs = {k: v for k, v in route_kwargs.items() if v is not None}

        app.api_route(action.path, **route_kwargs)(endpoint)

    return app
