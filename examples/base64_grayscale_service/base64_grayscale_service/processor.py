"""Simple processor that converts a base64 image payload to grayscale."""

import base64
import io
from typing import List

from pydantic import BaseModel, Field
from PIL import Image, ImageOps

from stateless_microservice import BaseProcessor, StatelessAction, run_blocking


class GrayscaleRequest(BaseModel):
    """Incoming payload that carries a base64 encoded image."""

    image_b64: str = Field(..., description="Base64 encoded image bytes.")


class GrayscaleResponse(BaseModel):
    """Response payload with the grayscale image encoded as base64 PNG."""

    grayscale_b64: str = Field(..., description="Base64 encoded grayscale PNG bytes.")


def _convert_to_grayscale(image_bytes: bytes) -> str:
    """Return base64-encoded PNG data for the grayscale version of the image."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        grayscale = ImageOps.grayscale(img)
        buffer = io.BytesIO()
        grayscale.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class GrayscaleProcessor(BaseProcessor):
    """Processor that exposes a single grayscale conversion action."""

    @property
    def name(self) -> str:
        return "base64-grayscale"

    def get_stateless_actions(self) -> List[StatelessAction]:
        return [
            StatelessAction(
                name="convert_to_grayscale",
                path="/image/grayscale",
                request_model=GrayscaleRequest,
                handler=self.handle_grayscale,
                summary="Convert a base64 image to grayscale PNG (base64).",
                description=(
                    "Accepts any Pillow-supported image bytes in base64 form and returns "
                    "a grayscale PNG encoded in base64. Does not require S3."
                ),
            ),
        ]

    async def handle_grayscale(self, request: GrayscaleRequest) -> GrayscaleResponse:
        image_bytes = base64.b64decode(request.image_b64)
        grayscale_b64 = await run_blocking(_convert_to_grayscale, image_bytes)
        return GrayscaleResponse(grayscale_b64=grayscale_b64)
