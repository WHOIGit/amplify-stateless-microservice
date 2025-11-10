"""Base processor interface for stateless (request/response) microservices."""

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
        request_model: Pydantic model for request validation.
        response_model: Optional Pydantic model for response serialization.
        methods: HTTP methods to expose (defaults to POST).
        summary: Optional OpenAPI summary.
        description: Optional longer description.
        tags: Optional OpenAPI tags.
        media_type: Optional override for response media type.
    """

    name: str
    path: str
    handler: Callable[["BaseProcessor", BaseModel], Awaitable[Any] | Any]
    request_model: type[BaseModel]
    response_model: type[BaseModel] | None = None
    methods: tuple[str, ...] = ("POST",)
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] | None = None
    media_type: str | None = None


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

        Override in subclasses to expose synchronous microservice endpoints.
        """
        return []
