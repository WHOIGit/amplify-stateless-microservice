FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy application code and dependencies
COPY pyproject.toml README.md ./
COPY auth_service ./auth_service

# Install package
RUN pip install --no-cache-dir .

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "auth_service.main"]
