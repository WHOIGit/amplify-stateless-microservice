"""Stateless Microservice toolkit for synchronous FastAPI services."""

from .processor import BaseProcessor, StatelessAction
from .api import create_app, ServiceConfig
from .config import settings
from .direct import fetch_s3_bytes, run_blocking, render_bytes
from .apache_conf import ApacheConfigParams, generate_apache_vhost_config
from .auth import AuthClient, TokenInfo, create_auth_dependency

__version__ = "1.0.0"


__all__ = [
    "BaseProcessor",
    "StatelessAction",
    "create_app",
    "ServiceConfig",
    "settings",
    "fetch_s3_bytes",
    "run_blocking",
    "render_bytes",
    "ApacheConfigParams",
    "generate_apache_vhost_config",
    "AuthClient",
    "TokenInfo",
    "create_auth_dependency",
]
