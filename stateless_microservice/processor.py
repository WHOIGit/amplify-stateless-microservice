"""Base processor interface for stateless (request/response) microservices."""

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List

from pydantic import BaseModel


@dataclass
class StatelessAction:
    """
    Definition of a stateless API route backed by a processor method.

    Attributes:
        name: Short identifier used for logging and OpenAPI docs.
        path: FastAPI route path (e.g., "/transform").
        handler: Callable invoked with the processor instance and validated payload.
        request_model: Optional Pydantic model for request validation (defaults to empty model).
        response_model: Optional Pydantic model for response serialization.
        methods: HTTP methods to expose (defaults to POST).
        path_params_model: Optional Pydantic model for path parameter validation.
        summary: Optional OpenAPI summary.
        description: Optional longer description.
        tags: Optional OpenAPI tags.
        media_type: Optional override for response media type.
        required_scopes: Optional list of scopes required for authentication.
    """

    name: str
    path: str
    handler: Callable[[BaseModel], Awaitable[Any] | Any]
    request_model: type[BaseModel] | None = None
    response_model: type[BaseModel] | None = None
    methods: tuple[str, ...] = ("POST",)
    path_params_model: type[BaseModel] | None = None
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] | None = None
    media_type: str | None = None
    required_scopes: list[str] | None = None


def stateless_action(
    name: str,
    path: str,
    request_model: type[BaseModel] | None = None,
    response_model: type[BaseModel] | None = None,
    methods: tuple[str, ...] = ("POST",),
    path_params_model: type[BaseModel] | None = None,
    summary: str | None = None,
    description: str | None = None,
    tags: tuple[str, ...] | None = None,
    media_type: str | None = None,
    required_scopes: list[str] | None = None,
):
    """
    Decorator to mark a method as a stateless action endpoint.

    This decorator stores metadata on the method that will be automatically
    discovered by BaseProcessor.get_stateless_actions().

    Args:
        name: Short identifier used for logging and OpenAPI docs.
        path: FastAPI route path (e.g., "/transform").
        request_model: Optional Pydantic model for request validation.
        response_model: Optional Pydantic model for response serialization.
        methods: HTTP methods to expose (defaults to POST).
        path_params_model: Optional Pydantic model for path parameter validation.
        summary: Optional OpenAPI summary.
        description: Optional longer description.
        tags: Optional OpenAPI tags.
        media_type: Optional override for response media type.
        required_scopes: Optional list of scopes required for authentication.

    Example:
        @stateless_action(
            name="echo",
            path="/echo",
            request_model=EchoRequest,
            response_model=EchoResponse,
            summary="Echo a message"
        )
        async def echo_message(self, request: EchoRequest) -> EchoResponse:
            return EchoResponse(message=request.message)
    """

    def decorator(func):
        # Store metadata on the function
        func._stateless_action_metadata = {
            "name": name,
            "path": path,
            "request_model": request_model,
            "response_model": response_model,
            "methods": methods,
            "path_params_model": path_params_model,
            "summary": summary,
            "description": description,
            "tags": tags,
            "media_type": media_type,
            "required_scopes": required_scopes,
        }
        return func

    return decorator


class BaseProcessor(ABC):
    """Hook point for stateless microservices."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Processor/service name used for logging and metadata."""

    @property
    def version(self) -> str:
        """Optional semantic version string."""
        return "1.0.0"

    def get_stateless_actions(self) -> List[StatelessAction]:
        """
        Return the list of stateless actions provided by this processor.

        By default, this automatically discovers methods decorated with @stateless_action.
        Subclasses can override this method to manually define actions or mix both approaches.
        """
        actions = []

        # Auto-discover decorated methods
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            # Check if the method has action metadata
            if hasattr(method, "_stateless_action_metadata"):
                metadata = method._stateless_action_metadata
                actions.append(
                    StatelessAction(
                        name=metadata["name"],
                        path=metadata["path"],
                        handler=method,
                        request_model=metadata["request_model"],
                        response_model=metadata["response_model"],
                        methods=metadata["methods"],
                        path_params_model=metadata["path_params_model"],
                        summary=metadata["summary"],
                        description=metadata["description"],
                        tags=metadata["tags"],
                        media_type=metadata["media_type"],
                        required_scopes=metadata["required_scopes"],
                    )
                )

        return actions
