"""FastAPI application factory for stateless request/response services."""

import inspect
import logging
import re
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .models import ErrorResponse, HealthResponse
from .processor import BaseProcessor, StatelessAction

logger = logging.getLogger(__name__)


class EmptyRequestModel(BaseModel):
    """ Empty request model, used when no request model specified. """
    pass


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
        # Create empty model if no request_model provided
        if action.request_model is None:
            RequestModel = EmptyRequestModel
        else:
            RequestModel = action.request_model
        PathParamsModel = action.path_params_model

        if PathParamsModel: # Payload and path params
            # Check if RequestModel has any fields
            has_request_fields = len(RequestModel.model_fields) > 0

            if has_request_fields:
                # RequestModel has fields (body/query params)
                async def endpoint(request: Request, payload: RequestModel):
                    path_params = PathParamsModel(**request.path_params)
                    call_result = action.handler(payload, path_params)

                    if inspect.isawaitable(call_result):
                        call_result = await call_result
                    if isinstance(call_result, Response):
                        return call_result
                    if action.media_type and isinstance(call_result, (bytes, bytearray, memoryview)):
                        return Response(content=bytes(call_result), media_type=action.media_type)
                    return call_result
            else:
                # Empty RequestModel: create empty instance directly, don't parse from request
                async def endpoint(request: Request):
                    path_params = PathParamsModel(**request.path_params)
                    payload = RequestModel()  # Empty instance
                    call_result = action.handler(payload, path_params)

                    if inspect.isawaitable(call_result):
                        call_result = await call_result
                    if isinstance(call_result, Response):
                        return call_result
                    if action.media_type and isinstance(call_result, (bytes, bytearray, memoryview)):
                        return Response(content=bytes(call_result), media_type=action.media_type)
                    return call_result
        else: # Payload only
            async def endpoint(payload: RequestModel):
                call_result = action.handler(payload)

                if inspect.isawaitable(call_result):
                    call_result = await call_result
                if isinstance(call_result, Response):
                    return call_result
                if action.media_type and isinstance(call_result, (bytes, bytearray, memoryview)):
                    return Response(content=bytes(call_result), media_type=action.media_type)
                return call_result

        return endpoint

    for action in actions:
        logger.info("Registering stateless action '%s' at %s", action.name, action.path)

        if action.path_params_model:
            path_param_names = set(re.findall(r'\{(\w+)\}', action.path))

            model_field_names = set(action.path_params_model.model_fields.keys())

            if path_param_names != model_field_names:
                raise ValueError(
                    f"Path parameters in '{action.path}' do not match "
                    f"path_params_model fields for action '{action.name}'."
                    f"Path has {path_param_names}, model has {model_field_names}"
                )

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
