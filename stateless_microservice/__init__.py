"""Stateless Microservice toolkit for synchronous FastAPI services."""

from .processor import BaseProcessor, StatelessAction
from .api import create_app, ServiceConfig, Lifespan
from .config import settings
from .direct import fetch_s3_bytes, run_blocking, render_bytes
from .apache_conf import ApacheConfigParams, generate_apache_vhost_config

__version__ = "1.0.0"


__all__ = [
    "BaseProcessor",
    "StatelessAction",
    "create_app",
    "ServiceConfig",
    "Lifespan",
    "settings",
    "fetch_s3_bytes",
    "run_blocking",
    "render_bytes",
    "ApacheConfigParams",
    "generate_apache_vhost_config",
    "AuthClient",
]


def __getattr__(name):
    """Lazy import for optional dependencies."""
    if name == "AuthClient":
        try:
            from .auth import AuthClient
            return AuthClient
        except ImportError as e:
            raise ImportError(
                f"AuthClient requires httpx. Install with: pip install amplify-stateless[auth]"
            ) from e
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
