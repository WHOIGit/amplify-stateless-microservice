"""Entrypoint for the base64 grayscale stateless service."""

from fastapi import FastAPI

from stateless_microservice import ServiceConfig, create_app

from .processor import GrayscaleProcessor


processor = GrayscaleProcessor()

app: FastAPI = create_app(
    processor,
    ServiceConfig(
        name="base64-grayscale-service",
        description="Minimal example that converts a base64 image into grayscale.",
        version="0.1.0",
    ),
)
