"""Main entrypoint for auth service."""

import uvicorn

from .api import app
from .config import settings

if __name__ == "__main__":
    uvicorn.run(
        "auth_service.api:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
        log_level="info"
    )
