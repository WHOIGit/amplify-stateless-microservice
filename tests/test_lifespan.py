"""Tests for lifespan passthrough in create_app."""

from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stateless_microservice import BaseProcessor, StatelessAction, create_app


class SimpleProcessor(BaseProcessor):
    @property
    def name(self) -> str:
        return "test-lifespan"

    def get_stateless_actions(self) -> List[StatelessAction]:
        return [
            StatelessAction(
                name="check_state",
                path="/check",
                handler=self.check_state,
                methods=("GET",),
            ),
        ]

    def check_state(self):
        return {"status": "ok"}


def test_lifespan_startup_and_shutdown():
    """Test that lifespan context manager is called on startup and shutdown."""
    events = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        events.append("startup")
        app.state.initialized = True
        yield
        events.append("shutdown")

    processor = SimpleProcessor()
    app = create_app(processor, lifespan=lifespan)

    with TestClient(app) as client:
        assert "startup" in events
        assert app.state.initialized is True
        response = client.get("/check")
        assert response.status_code == 200

    assert "shutdown" in events


def test_no_lifespan_works():
    """Test that create_app still works without lifespan."""
    processor = SimpleProcessor()
    app = create_app(processor)

    with TestClient(app) as client:
        response = client.get("/check")
        assert response.status_code == 200
