"""Tests for render_bytes function."""

from stateless_microservice.direct import render_bytes


def test_render_bytes_with_headers():
    """Test that custom headers are included in the response."""
    headers = {"X-Custom-Header": "test-value", "Content-Disposition": "attachment"}

    response = render_bytes(b"test data", "application/octet-stream", headers=headers)

    assert response.headers["x-custom-header"] == "test-value"
    assert response.headers["content-disposition"] == "attachment"


def test_render_bytes_without_headers():
    """Test that response works without headers."""
    response = render_bytes(b"test data", "application/octet-stream")

    assert response.body == b"test data"
    assert response.media_type == "application/octet-stream"
