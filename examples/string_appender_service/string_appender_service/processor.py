"""Simple processor that appends two path parameters together."""

from typing import List

from pydantic import BaseModel, Field

from stateless_microservice import BaseProcessor, StatelessAction


class AppendPathParams(BaseModel):
    """Path parameters for the append operation."""

    first: str = Field(..., description="First string to append.")
    second: str = Field(..., description="Second string to append.")


class AppendResponse(BaseModel):
    """Response with the appended strings."""

    result: str = Field(..., description="The concatenated result of first + second.")


class StringAppenderProcessor(BaseProcessor):
    """Processor that exposes a string append action using path parameters."""

    @property
    def name(self) -> str:
        return "string-appender"

    def get_stateless_actions(self) -> List[StatelessAction]:
        return [
            StatelessAction(
                name="append_strings",
                path="/append/{first}/{second}",
                path_params_model=AppendPathParams,
                response_model=AppendResponse,
                handler=self.handle_append,
                methods=("GET",),
                summary="Append two path parameters together.",
                description=(
                    "Demonstrates path parameter usage by taking two strings from the URL path "
                    "and returning them concatenated together."
                ),
            ),
        ]

    async def handle_append(self, request, path_params: AppendPathParams) -> AppendResponse:
        """Append the two path parameters and return the result."""
        result = path_params.first + path_params.second
        return AppendResponse(result=result)
