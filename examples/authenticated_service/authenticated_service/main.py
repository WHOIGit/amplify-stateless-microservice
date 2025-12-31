"""
Main entrypoint for authenticated service.

This shows how to integrate auth with your microservice.
"""

import os

import uvicorn

from stateless_microservice import create_app, ServiceConfig, AuthClient
from .processor import Processor


# Get auth service URL from environment
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8000")

# Create auth client
auth_client = AuthClient(auth_service_url=AUTH_SERVICE_URL)

# Create processor
processor = Processor()

# Create FastAPI app with auth integration
app = create_app(
    processor=processor,
    config=ServiceConfig(
        description="Example microservice with token authentication"
    ),
    auth_client=auth_client  # Pass auth_client to enable authentication
)

# Store service name for audit logging
app.state.service_name = processor.name


if __name__ == "__main__":
    uvicorn.run(
        "authenticated_service.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
