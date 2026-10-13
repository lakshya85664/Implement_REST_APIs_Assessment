
import pytest

from src.observability import EventLogger, Metrics
from src.reliability import (
    IdempotencyConflict,
    IdempotencyStore,
    RateLimiter,
    call_with_retries,
)


def test_rate_limiter_rejects_calls_over_limit():
    limiter = RateLimiter(limit=2, window_seconds=60)

    assert limiter.allow("user-1") is True
    assert limiter.allow("user-1") is True
    assert limiter.allow("user-1") is False


def test_rate_limiter_separates_keys():
    limiter = RateLimiter(limit=1, window_seconds=60)

    assert limiter.allow("user-1") is True
    assert limiter.allow("user-2") is True


def test_idempotency_reuses_cached_result():
    store = IdempotencyStore()
    result = {"status": "ok", "order_id": "ORD-1001"}

    store.put("req-1", "fingerprint-a", result)

    assert store.get("req-1", "fingerprint-a") == result


def test_idempotency_rejects_changed_request():
    store = IdempotencyStore()
    store.put("req-1", "fingerprint-a", {"status": "ok"})

    with pytest.raises(IdempotencyConflict):
        store.get("req-1", "fingerprint-b")


def test_retry_succeeds_after_transient_failure():
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            raise TimeoutError("temporary failure")

        return "success"

    result, retries = call_with_retries(
        operation,
        retry_exceptions=(TimeoutError,),
        max_retries=2,
    )

    assert result == "success"
    assert retries == 2
    assert attempts == 3


def test_retry_stops_at_budget():
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        raise TimeoutError("still failing")

    with pytest.raises(TimeoutError):
        call_with_retries(
            operation,
            retry_exceptions=(TimeoutError,),
            max_retries=2,
        )

    assert attempts == 3


def test_metrics_track_counts_and_latency():
    metrics = Metrics()
    metrics.increment("requests")
    metrics.increment("requests")
    metrics.record_latency(10.0)
    metrics.record_latency(20.0)

    result = metrics.snapshot()

    assert result["counters"]["requests"] == 2
    assert result["latency_count"] == 2
    assert result["latency_mean_ms"] == 15.0
    assert result["latency_max_ms"] == 20.0


def test_event_logger_redacts_sensitive_fields():
    logger = EventLogger()
    logger.emit(
        "request_received",
        tool="order_lookup",
        api_key="do-not-log",
        arguments={"password": "do-not-log"},
    )

    output = logger.export_json()

    assert "order_lookup" in output
    assert "do-not-log" not in output
    assert "api_key" not in output
