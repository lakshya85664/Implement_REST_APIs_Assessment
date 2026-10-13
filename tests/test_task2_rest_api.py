
from src.contracts import ToolCall, ToolStatus
from src.gateway import dispatch
from src.gateway_setup import build_test_environment


def make_call(
    tool_name: str,
    arguments: dict,
    role: str = "operator",
    request_id: str = "req-001",
) -> ToolCall:
    return ToolCall(
        request_id=request_id,
        tool_name=tool_name,
        version="1.0",
        arguments=arguments,
        principal="test-user",
        role=role,
    )


def test_real_http_lookup_success():
    server, client, registry = build_test_environment()
    try:
        result = dispatch(
            make_call("order_lookup", {"order_id": "ORD-1001"}),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        assert result.status == ToolStatus.OK
        assert result.data["order_id"] == "ORD-1001"
        assert result.data["status"] == "processing"
        assert server.request_counts["/orders/ORD-1001"] == 1
    finally:
        client.close()
        server.stop()


def test_real_http_update_success():
    server, client, registry = build_test_environment()
    try:
        result = dispatch(
            make_call(
                "order_update",
                {
                    "order_id": "ORD-1001",
                    "new_status": "shipped",
                },
            ),
            {"id": "test-user", "role": "operator"},
            registry,
            client,
        )

        assert result.status == ToolStatus.OK
        assert result.data["status"] == "shipped"
        assert result.data["updated"] is True
    finally:
        client.close()
        server.stop()


def test_invalid_input_does_not_call_server():
    server, client, registry = build_test_environment()
    try:
        result = dispatch(
            make_call("order_lookup", {"order_id": "bad-id"}),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        assert result.status == ToolStatus.INVALID
        assert server.request_counts == {}
    finally:
        client.close()
        server.stop()


def test_unknown_tool_does_not_call_server():
    server, client, registry = build_test_environment()
    try:
        result = dispatch(
            make_call("unknown_tool", {}),
            {"id": "test-user", "role": "admin"},
            registry,
            client,
        )

        assert result.status == ToolStatus.DENIED
        assert server.request_counts == {}
    finally:
        client.close()
        server.stop()


def test_unauthorized_update_has_no_side_effect():
    server, client, registry = build_test_environment()
    try:
        result = dispatch(
            make_call(
                "order_update",
                {
                    "order_id": "ORD-1001",
                    "new_status": "cancelled",
                },
                role="viewer",
            ),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        assert result.status == ToolStatus.DENIED
        assert server.orders["ORD-1001"]["status"] == "processing"
        assert server.request_counts == {}
    finally:
        client.close()
        server.stop()


def test_unknown_order_maps_to_not_found():
    server, client, registry = build_test_environment()
    try:
        result = dispatch(
            make_call("order_lookup", {"order_id": "ORD-9999"}),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        assert result.status == ToolStatus.NOT_FOUND
    finally:
        client.close()
        server.stop()


def test_provider_error_maps_to_structured_status():
    server, client, registry = build_test_environment()
    try:
        server.failure_modes["/orders/ORD-1001"] = "server_error"

        result = dispatch(
            make_call("order_lookup", {"order_id": "ORD-1001"}),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        assert result.status == ToolStatus.PROVIDER_ERROR
    finally:
        client.close()
        server.stop()


def test_timeout_maps_to_structured_status():
    server, client, registry = build_test_environment(timeout_seconds=0.05)
    try:
        server.failure_modes["/orders/ORD-1001"] = "timeout"

        result = dispatch(
            make_call("order_lookup", {"order_id": "ORD-1001"}),
            {"id": "test-user", "role": "viewer"},
            registry,
            client,
        )

        assert result.status == ToolStatus.TIMEOUT
    finally:
        client.close()
        server.stop()
