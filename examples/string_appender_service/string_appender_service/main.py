"""Entrypoint for the string appender stateless service."""

from fastapi import FastAPI

from stateless_microservice import ServiceConfig, create_app

from .processor import StringAppenderProcessor


processor = StringAppenderProcessor()

app: FastAPI = create_app(
    processor,
    ServiceConfig(
        name="string-appender-service",
        description="Example service demonstrating path parameter usage by appending two strings.",
        version="0.1.0",
    ),
)
