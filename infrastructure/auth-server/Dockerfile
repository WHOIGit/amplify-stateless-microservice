FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy library code
COPY pyproject.toml README.md ./
COPY stateless_microservice ./stateless_microservice

# Install package with auth-server extras
RUN pip install --no-cache-dir .[auth-server]

# Run the auth server
CMD ["amplify-auth-server"]
