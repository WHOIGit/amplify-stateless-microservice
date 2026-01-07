"""Tests for the @stateless_action decorator."""

import pytest
from pydantic import BaseModel, Field

from stateless_microservice import BaseProcessor, StatelessAction, stateless_action


class SampleRequest(BaseModel):
    """Sample request model."""

    value: str = Field(..., description="Test value")


class SampleResponse(BaseModel):
    """Sample response model."""

    result: str = Field(..., description="Test result")


class DecoratorTestProcessor(BaseProcessor):
    """Test processor using decorators."""

    @property
    def name(self) -> str:
        return "decorator-test"

    @stateless_action(
        name="test_action",
        path="/test",
        request_model=SampleRequest,
        response_model=SampleResponse,
        methods=("POST",),
        summary="Test action",
        description="A test action for decorator verification",
        required_scopes=["read"],
    )
    async def handle_test(self, request: SampleRequest) -> SampleResponse:
        """Handle test request."""
        return SampleResponse(result=f"Processed: {request.value}")

    @stateless_action(
        name="simple_action",
        path="/simple",
        methods=("GET",),
        summary="Simple action",
    )
    def handle_simple(self) -> dict:
        """Handle simple request with no models."""
        return {"status": "ok"}


def test_decorator_discovery():
    """Test that decorated methods are auto-discovered."""
    processor = DecoratorTestProcessor()
    actions = processor.get_stateless_actions()

    # Should find both decorated methods
    assert len(actions) == 2

    # Check that actions are StatelessAction instances
    assert all(isinstance(action, StatelessAction) for action in actions)

    # Find the test_action
    test_action = next(a for a in actions if a.name == "test_action")
    assert test_action.path == "/test"
    assert test_action.request_model == SampleRequest
    assert test_action.response_model == SampleResponse
    assert test_action.methods == ("POST",)
    assert test_action.summary == "Test action"
    assert test_action.description == "A test action for decorator verification"
    assert test_action.required_scopes == ["read"]

    # Find the simple_action
    simple_action = next(a for a in actions if a.name == "simple_action")
    assert simple_action.path == "/simple"
    assert simple_action.methods == ("GET",)
    assert simple_action.summary == "Simple action"
    assert simple_action.request_model is None
    assert simple_action.response_model is None


def test_decorator_handler_binding():
    """Test that handlers are properly bound to the processor instance."""
    processor = DecoratorTestProcessor()
    actions = processor.get_stateless_actions()

    test_action = next(a for a in actions if a.name == "test_action")

    # The handler should be bound to the processor instance
    assert test_action.handler.__self__ is processor


@pytest.mark.asyncio
async def test_decorator_handler_execution():
    """Test that decorated handlers execute correctly."""
    processor = DecoratorTestProcessor()
    actions = processor.get_stateless_actions()

    # Test the async handler
    test_action = next(a for a in actions if a.name == "test_action")
    request = SampleRequest(value="hello")
    response = await test_action.handler(request)
    assert isinstance(response, SampleResponse)
    assert response.result == "Processed: hello"

    # Test the sync handler
    simple_action = next(a for a in actions if a.name == "simple_action")
    response = simple_action.handler()
    assert response == {"status": "ok"}


class MixedProcessor(BaseProcessor):
    """Test processor mixing decorators and manual actions."""

    @property
    def name(self) -> str:
        return "mixed-test"

    @stateless_action(
        name="decorated_action",
        path="/decorated",
        methods=("GET",),
    )
    def decorated_method(self) -> dict:
        """Decorated method."""
        return {"type": "decorated"}

    def manual_method(self) -> dict:
        """Manual method (not decorated)."""
        return {"type": "manual"}

    def get_stateless_actions(self):
        """Mix auto-discovered and manual actions."""
        # Get auto-discovered actions
        actions = super().get_stateless_actions()

        # Add a manual action
        actions.append(
            StatelessAction(
                name="manual_action",
                path="/manual",
                handler=self.manual_method,
                methods=("GET",),
            )
        )

        return actions


def test_mixed_decorator_and_manual():
    """Test that decorators and manual StatelessAction definitions can coexist."""
    processor = MixedProcessor()
    actions = processor.get_stateless_actions()

    # Should find both the decorated and manual action
    assert len(actions) == 2

    action_names = {a.name for a in actions}
    assert "decorated_action" in action_names
    assert "manual_action" in action_names


def test_backward_compatibility():
    """Test that processors without decorators still work (backward compatibility)."""

    class LegacyProcessor(BaseProcessor):
        """Old-style processor without decorators."""

        @property
        def name(self) -> str:
            return "legacy"

        def get_stateless_actions(self):
            """Manually define actions the old way."""
            return [
                StatelessAction(
                    name="legacy_action",
                    path="/legacy",
                    handler=self.handle_legacy,
                    methods=("POST",),
                )
            ]

        def handle_legacy(self) -> dict:
            """Handle legacy request."""
            return {"status": "legacy"}

    processor = LegacyProcessor()
    actions = processor.get_stateless_actions()

    assert len(actions) == 1
    assert actions[0].name == "legacy_action"
    assert actions[0].path == "/legacy"
