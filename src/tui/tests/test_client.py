"""Tests for the RSession RPC client."""

import pytest
from rstudio_tui.client import (
    RpcErrorCode,
    RpcResponse,
    ClientEvent,
    RSessionClient,
    EventType,
)


class TestRpcResponse:
    """Tests for RpcResponse dataclass."""

    def test_success_response(self):
        """Test successful response."""
        response = RpcResponse(result={"data": "value"})
        assert response.success is True
        assert response.error_message == ""
        assert response.error_code == RpcErrorCode.NO_ERROR

    def test_error_response(self):
        """Test error response."""
        response = RpcResponse(
            error={"code": RpcErrorCode.METHOD_NOT_FOUND, "message": "Method not found"}
        )
        assert response.success is False
        assert response.error_message == "Method not found"
        assert response.error_code == RpcErrorCode.METHOD_NOT_FOUND

    def test_result_with_none(self):
        """Test response with None result."""
        response = RpcResponse(result=None)
        assert response.success is True
        assert response.result is None


class TestClientEvent:
    """Tests for ClientEvent dataclass."""

    def test_event_creation(self):
        """Test creating a client event."""
        event = ClientEvent(type=EventType.CONSOLE_WRITE_OUTPUT, data="Hello", id=1)
        assert event.type == EventType.CONSOLE_WRITE_OUTPUT
        assert event.data == "Hello"
        assert event.id == 1

    def test_event_defaults(self):
        """Test default values."""
        event = ClientEvent(type=EventType.BUSY, data=True)
        assert event.id == 0


class TestRSessionClient:
    """Tests for RSessionClient."""

    def test_client_creation(self):
        """Test creating a client."""
        client = RSessionClient(host="localhost", port=8888)
        assert client.host == "localhost"
        assert client.port == 8888
        assert client.secure is False
        assert client.base_url == "http://localhost:8888"

    def test_secure_client(self):
        """Test creating a secure client."""
        client = RSessionClient(host="localhost", port=443, secure=True)
        assert client.secure is True
        assert client.base_url == "https://localhost:443"

    def test_event_handler_registration(self):
        """Test registering event handlers."""
        client = RSessionClient()
        handler_called = False

        def handler(event):
            nonlocal handler_called
            handler_called = True

        client.on_event(EventType.CONSOLE_WRITE_OUTPUT, handler)

        # Dispatch an event
        event = ClientEvent(type=EventType.CONSOLE_WRITE_OUTPUT, data="test")
        client._dispatch_event(event)

        assert handler_called

    def test_event_handler_removal(self):
        """Test removing event handlers."""
        client = RSessionClient()
        call_count = 0

        def handler(event):
            nonlocal call_count
            call_count += 1

        client.on_event(EventType.BUSY, handler)
        client.off_event(EventType.BUSY, handler)

        event = ClientEvent(type=EventType.BUSY, data=True)
        client._dispatch_event(event)

        assert call_count == 0


class TestEventTypes:
    """Tests for event type constants."""

    def test_event_type_values(self):
        """Test that event types have expected values."""
        assert EventType.BUSY == 0
        assert EventType.CONSOLE_PROMPT == 1
        assert EventType.CONSOLE_WRITE_OUTPUT == 2
        assert EventType.CONSOLE_WRITE_ERROR == 3

    def test_event_type_comparison(self):
        """Test event type comparison."""
        assert EventType.BUSY == 0
        assert EventType.CONSOLE_PROMPT != EventType.BUSY


class TestRpcErrorCodes:
    """Tests for RPC error codes."""

    def test_standard_error_codes(self):
        """Test standard JSON-RPC error codes."""
        assert RpcErrorCode.PARSE_ERROR == -32700
        assert RpcErrorCode.INVALID_REQUEST == -32600
        assert RpcErrorCode.METHOD_NOT_FOUND == -32601

    def test_rstudio_error_codes(self):
        """Test RStudio-specific error codes."""
        assert RpcErrorCode.NO_ERROR == 0
        assert RpcErrorCode.CONNECTION_ERROR == 1
        assert RpcErrorCode.UNAUTHORIZED == 3
