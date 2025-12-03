FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"
ENV PYTHONUNBUFFERED=1

COPY . /app/repo

WORKDIR /app/repo

RUN uv pip install --system .

WORKDIR /app/repo/examples/string_appender_service

RUN uv pip install --system .

EXPOSE 8030

CMD ["uvicorn", "string_appender_service.main:app", "--host", "0.0.0.0", "--port", "8030"]
