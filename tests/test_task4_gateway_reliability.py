
from src.contracts import ToolCall, ToolStatus
from src.gateway import ToolGateway
from src.gateway_setup import build_test_environment


def make_call(
    tool: str,
    arguments: dict,
    request_id: str,
    role: str = "operator",
) -> ToolCall:
    return ToolCall(
        request_id=request_id,
        tool_name=tool,
        version="1.0",
        arguments=arguments,
        principal="test-user",
        role=role,
    )


def test_write_replay_does_not_repeat_http_update():
    server, client, registry = build_test_environment()
    try:
        gateway = ToolGateway(registry, client)
        call = make_call(
            "order_update",
            {"order_id": "ORD-1001", "new_status": "shipped"},
            "write-replay-1",
        )
        principal = {"id": "test-user", "role": "operator"}

        first = gateway.execute(call, principal)
        second = gateway.execute(call, principal)

        assert first.status == ToolStatus.OK
        assert second.status == ToolStatus.OK
        assert second.data == first.data
        assert server.request_counts["/orders/ORD-1001"] == 1
        assert gateway.metrics.snapshot()["counters"]["idempotency.cache_hit"] == 1
    finally:
        client.close()
        server.stop()


def test_reused_idempotency_key_with_changed_arguments_is_rejected():
    server, client, registry = build_test_environment()
    try:
        gateway = ToolGateway(registry, client)
        principal = {"id": "test-user", "role": "operator"}

        first = gateway.execute(
            make_call(
                "order_update",
                {"order_id": "ORD-1001", "new_status": "shipped"},
                "same-key",
            ),
            principal,
        )
        second = gateway.execute(
            make_call(
                "order_update",
                {"order_id": "ORD-1001", "new_status": "cancelled"},
                "same-key",
            ),
            principal,
        )

        assert first.status == ToolStatus.OK
        assert second.status == ToolStatus.INVALID
        assert server.orders["ORD-1001"]["status"] == "shipped"
        assert server.request_counts["/orders/ORD-1001"] == 1
    finally:
        client.close()
        server.stop()


def test_read_timeout_uses_bounded_retries():
    server, client, registry = build_test_environment(timeout_seconds=0.03)
    try:
        server.failure_modes["/orders/ORD-1001"] = "timeout"
        gateway = ToolGateway(registry, client, max_read_retries=2)

        result = gateway.execute(
            make_call(
                "order_lookup",
                {"order_id": "ORD-1001"},
                "read-timeout",
                role="viewer",
            ),
            {"id": "test-user", "role": "viewer"},
        )

        assert result.status == ToolStatus.TIMEOUT
        assert server.request_counts["/orders/ORD-1001"] == 3
        assert gateway.metrics.snapshot()["counters"]["retry.attempts"] == 2
        assert gateway.metrics.snapshot()["counters"]["provider.attempts"] == 3
    finally:
        client.close()
        server.stop()


def test_rate_limiter_blocks_excess_requests():
    server, client, registry = build_test_environment()
    try:
        gateway = ToolGateway(
            registry,
            client,
            rate_limit=1,
            rate_window_seconds=60,
        )
        principal = {"id": "test-user", "role": "viewer"}

        first = gateway.execute(
            make_call(
                "order_lookup",
                {"order_id": "ORD-1001"},
                "rate-1",
                role="viewer",
            ),
            principal,
        )
        second = gateway.execute(
            make_call(
                "order_lookup",
                {"order_id": "ORD-1001"},
                "rate-2",
                role="viewer",
            ),
            principal,
        )

        assert first.status == ToolStatus.OK
        assert second.status == ToolStatus.RATE_LIMITED
        assert server.request_counts["/orders/ORD-1001"] == 1
    finally:
        client.close()
        server.stop()


def test_gateway_emits_redacted_events_and_metrics():
    server, client, registry = build_test_environment()
    try:
        gateway = ToolGateway(registry, client)
        result = gateway.execute(
            make_call(
                "order_lookup",
                {"order_id": "ORD-1001"},
                "metrics-1",
                role="viewer",
            ),
            {"id": "test-user", "role": "viewer"},
        )

        snapshot = gateway.metrics.snapshot()
        trace = gateway.logger.export_json()

        assert result.status == ToolStatus.OK
        assert snapshot["counters"]["requests.total"] == 1
        assert snapshot["counters"]["outcome.ok"] == 1
        assert snapshot["latency_count"] == 1
        assert "arguments" not in trace
    finally:
        client.close()
        server.stop()
