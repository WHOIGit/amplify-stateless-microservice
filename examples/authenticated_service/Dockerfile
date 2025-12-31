FROM python:3.12-slim

WORKDIR /app

# Install stateless_microservice framework with auth support
COPY stateless_microservice /tmp/stateless_microservice
COPY pyproject.toml /tmp/pyproject.toml
COPY README.md /tmp/README.md
RUN pip install --no-cache-dir /tmp[auth]

# Copy service code
COPY examples/authenticated_service .

# Expose port
EXPOSE 8000

# Run the service
CMD ["python", "-m", "authenticated_service.main"]
