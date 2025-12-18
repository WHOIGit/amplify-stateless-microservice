"""Tests for validation error handling in stateless microservices."""

from typing import List, Literal

from fastapi.testclient import TestClient
from pydantic import BaseModel

from stateless_microservice import BaseProcessor, StatelessAction, create_app


class PathParams(BaseModel):
    """Test path parameters with Literal type."""
    action: Literal["start", "stop"]


class RequestPayload(BaseModel):
    """Test request payload."""
    value: int


class TestProcessor(BaseProcessor):
    """Test processor for validation error handling."""

    @property
    def name(self) -> str:
        return "test-validation"

    def get_stateless_actions(self) -> List[StatelessAction]:
        return [
            StatelessAction(
                name="test_path_params",
                path="/test/{action}",
                path_params_model=PathParams,
                handler=self.handle_path_params,
                methods=("GET",),
            ),
            StatelessAction(
                name="test_request_body",
                path="/test/body",
                request_model=RequestPayload,
                handler=self.handle_request_body,
                methods=("POST",),
            ),
        ]

    def handle_path_params(self, path_params: PathParams):
        """Handler for path params test."""
        return {"action": path_params.action}

    def handle_request_body(self, payload: RequestPayload):
        """Handler for request body test."""
        return {"value": payload.value}


def test_path_param_validation_literal_mismatch():
    """Test that invalid Literal path param returns 400."""
    processor = TestProcessor()
    app = create_app(processor)
    client = TestClient(app)

    # Send invalid value "invalid" when only "start" or "stop" are allowed
    response = client.get("/test/invalid")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Validation error" in data["error"]


def test_path_param_validation_type_error():
    """Test that type conversion errors in path params return 400."""
    processor = TestProcessor()
    app = create_app(processor)
    client = TestClient(app)

    # Valid literal value
    response = client.get("/test/start")
    assert response.status_code == 200


def test_request_body_validation_error():
    """Test that invalid request body returns 422 (FastAPI default)."""
    processor = TestProcessor()
    app = create_app(processor)
    client = TestClient(app)

    # Send string when int is expected
    response = client.post("/test/body", json={"value": "not_an_int"})

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_request_body_validation_success():
    """Test that valid request body returns 200."""
    processor = TestProcessor()
    app = create_app(processor)
    client = TestClient(app)

    response = client.post("/test/body", json={"value": 42})

    assert response.status_code == 200
    data = response.json()
    assert data["value"] == 42
