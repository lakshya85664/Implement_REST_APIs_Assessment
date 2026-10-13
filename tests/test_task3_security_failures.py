
import json

from src.contracts import ToolCall, ToolStatus
from src.gateway import dispatch
from src.gateway_setup import build_test_environment


def make_call(
    tool_name: str,
    arguments: dict,
    role: str = "viewer",
    request_id: str = "task3-001",
) -> ToolCall:
    return ToolCall(
        request_id=request_id,
        tool_name=tool_name,
        version="1.0",
        arguments=arguments,
        principal="test-user",
        role=role,
    )


def test_unauthorized_write_does_not_change_order():
    server, client, registry = build_test_environment()
    try:
        original = dict(server.orders["ORD-1001"])

        result = dispatch(
            make_call(
                "order_update",
                {
                    "order_id": "ORD-1001",
                    "new_status": "cancelled",
                },
            ),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        assert result.status == ToolStatus.DENIED
        assert server.orders["ORD-1001"] == original
        assert server.request_counts == {}
    finally:
        client.close()
        server.stop()


def test_unknown_tool_is_denied_without_http_request():
    server, client, registry = build_test_environment()
    try:
        result = dispatch(
            make_call("admin_override", {}),
            {"id": "test-user", "role": "admin"},
            registry,
            client,
        )

        assert result.status == ToolStatus.DENIED
        assert server.request_counts == {}
    finally:
        client.close()
        server.stop()


def test_invalid_arguments_are_rejected_before_http():
    server, client, registry = build_test_environment()
    try:
        result = dispatch(
            make_call("order_update", {
                "order_id": "ORD-1001",
                "new_status": "refund",
            }, role="operator"),
            {"id": "test-user", "role": "operator"},
            registry,
            client,
        )

        assert result.status == ToolStatus.INVALID
        assert server.request_counts == {}
        assert server.orders["ORD-1001"]["status"] == "processing"
    finally:
        client.close()
        server.stop()


def test_server_error_does_not_leak_provider_details():
    server, client, registry = build_test_environment()
    try:
        server.failure_modes["/orders/ORD-1001"] = "server_error"

        result = dispatch(
            make_call("order_lookup", {"order_id": "ORD-1001"}),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        serialized = json.dumps(result.model_dump(mode="json"))
        assert result.status == ToolStatus.PROVIDER_ERROR
        assert "provider unavailable" not in serialized
        assert "Traceback" not in serialized
    finally:
        client.close()
        server.stop()


def test_timeout_does_not_leak_exception_details():
    server, client, registry = build_test_environment(
        timeout_seconds=0.05
    )
    try:
        server.failure_modes["/orders/ORD-1001"] = "timeout"

        result = dispatch(
            make_call("order_lookup", {"order_id": "ORD-1001"}),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        serialized = json.dumps(result.model_dump(mode="json"))
        assert result.status == ToolStatus.TIMEOUT
        assert "Traceback" not in serialized
        assert "127.0.0.1" not in serialized
    finally:
        client.close()
        server.stop()


def test_missing_order_does_not_change_any_order():
    server, client, registry = build_test_environment()
    try:
        before = {key: dict(value) for key, value in server.orders.items()}

        result = dispatch(
            make_call("order_update", {
                "order_id": "ORD-9999",
                "new_status": "cancelled",
            }, role="operator"),
            {"id": "test-user", "role": "operator"},
            registry,
            client,
        )

        assert result.status == ToolStatus.NOT_FOUND
        assert server.orders == before
    finally:
        client.close()
        server.stop()


def test_wrong_version_is_denied():
    server, client, registry = build_test_environment()
    try:
        call = make_call("order_lookup", {"order_id": "ORD-1001"})
        call = call.model_copy(update={"version": "9.9"})

        result = dispatch(
            call,
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        assert result.status == ToolStatus.DENIED
        assert server.request_counts == {}
    finally:
        client.close()
        server.stop()


def test_malformed_provider_response_is_rejected():
    server, client, registry = build_test_environment()
    try:
        server.failure_modes["/orders/ORD-1001"] = "malformed_json"

        result = dispatch(
            make_call("order_lookup", {"order_id": "ORD-1001"}),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        assert result.status == ToolStatus.PROVIDER_ERROR
        assert result.next_action == "review_provider_response"
    finally:
        client.close()
        server.stop()
