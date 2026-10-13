
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from pydantic import ValidationError

from src.contracts import ToolCall, ToolResult, ToolStatus
from src.observability import EventLogger, Metrics
from src.registry import ToolRegistry
from src.reliability import IdempotencyConflict, IdempotencyStore


class ToolGateway:
    """Gateway for validating, authorizing, and executing tool calls."""

    def __init__(
        self,
        registry: ToolRegistry,
        client: Any,
        *,
        metrics: Metrics | None = None,
        logger: EventLogger | None = None,
        idempotency_store: IdempotencyStore | None = None,
        rate_limit: int = 100,
        rate_window_seconds: int = 60,
        max_read_retries: int = 2,
        retry_attempts: int | None = None,
    ) -> None:
        self.registry = registry
        self.client = client
        self.metrics = metrics or Metrics()
        self.logger = logger or EventLogger()
        self.idempotency_store = (
            idempotency_store or IdempotencyStore()
        )

        self.rate_limit = max(1, rate_limit)
        self.rate_window_seconds = max(1, rate_window_seconds)

        self.max_read_retries = max(
            0,
            max_read_retries
            if retry_attempts is None
            else retry_attempts - 1,
        )

        self._request_times: dict[str, list[float]] = {}

    @staticmethod
    def _fingerprint(call: ToolCall) -> str:
        """Create a stable fingerprint of a tool request."""
        payload = call.model_dump(mode="json")
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _emit(self, event_name: str, **fields: Any) -> None:
        """Emit an event without allowing logging failures to break execution."""
        try:
            self.logger.emit(event_name, **fields)
        except Exception:
            pass

    @staticmethod
    def _is_write(spec: Any) -> bool:
        mode = getattr(spec.access_mode, "value", spec.access_mode)
        return str(mode).lower() == "write"

    @staticmethod
    def _result(
        status: ToolStatus,
        data: dict[str, Any] | None = None,
        next_action: str | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> ToolResult:
        return ToolResult(
            status=status,
            data=data if data is not None else {},
            next_action=next_action,
            events=events if events is not None else [],
        )

    @staticmethod
    def _resolve_role(
        call: ToolCall,
        principal: Any,
    ) -> str | None:
        """Resolve the caller role from the principal or tool call."""
        if isinstance(principal, dict):
            role = principal.get("role")
        else:
            role = getattr(principal, "role", None)

        if role is None:
            role = getattr(call, "role", None)

        return role

    @staticmethod
    def _resolve_principal_id(
        call: ToolCall,
        principal: Any,
        role: str | None,
    ) -> str:
        """Resolve an identifier for rate limiting."""
        if isinstance(principal, dict):
            identifier = (
                principal.get("id")
                or principal.get("name")
                or principal.get("principal")
            )
        else:
            identifier = getattr(principal, "id", None)
            if identifier is None:
                identifier = getattr(principal, "name", None)

        if identifier is None:
            call_principal = getattr(call, "principal", None)

            if isinstance(call_principal, dict):
                identifier = (
                    call_principal.get("id")
                    or call_principal.get("name")
                )
            elif isinstance(call_principal, str):
                identifier = call_principal

        return str(identifier or role or "anonymous")

    def _check_rate_limit(self, principal_id: str) -> bool:
        """Enforce a rolling-window rate limit per principal."""
        now = time.monotonic()
        cutoff = now - self.rate_window_seconds

        recent = [
            timestamp
            for timestamp in self._request_times.get(
                principal_id, []
            )
            if timestamp > cutoff
        ]

        if len(recent) >= self.rate_limit:
            self._request_times[principal_id] = recent
            return False

        recent.append(now)
        self._request_times[principal_id] = recent
        return True

    @staticmethod
    def _map_exception(exc: Exception) -> ToolStatus:
        """Convert internal exceptions into safe public statuses."""
        name = type(exc).__name__
        message = str(exc).lower()

        if name == "RestTimeout" or "timeout" in message:
            return ToolStatus.TIMEOUT

        if name == "RestNotFound" or "not found" in message:
            return ToolStatus.NOT_FOUND

        if (
            name == "RestProviderError"
            or "provider error" in message
        ):
            return ToolStatus.PROVIDER_ERROR

        if (
            name in {"RestRateLimit", "RateLimitError"}
            or "rate limit" in message
        ):
            return ToolStatus.RATE_LIMITED

        if name == "RestResponseError":
            return ToolStatus.PROVIDER_ERROR

        return ToolStatus.FAILED

    def _invoke_handler(
        self,
        spec: Any,
        arguments: Any,
    ) -> Any:
        """Execute the handler, retrying read requests when appropriate."""
        if spec.handler is None:
            raise RuntimeError(
                f"No handler registered for tool '{spec.name}'"
            )

        is_write = self._is_write(spec)
        attempts = 1 if is_write else self.max_read_retries + 1

        for attempt in range(attempts):
            try:
                self.metrics.increment("provider.attempts")
                return spec.handler(arguments, self.client)

            except Exception as exc:
                if is_write or attempt >= attempts - 1:
                    raise

                status = self._map_exception(exc)

                # Retry transient read failures only.
                if status not in {
                    ToolStatus.TIMEOUT,
                    ToolStatus.PROVIDER_ERROR,
                }:
                    raise

                self.metrics.increment("retry.attempts")
                self._emit(
                    "gateway_read_retry",
                    tool_name=spec.name,
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                )

        raise RuntimeError("Read retry loop ended unexpectedly")

    def execute(
        self,
        call: ToolCall,
        principal: Any = None,
        *,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        """Validate, authorize, execute, and record a tool call."""
        started = time.perf_counter()
        request_id = getattr(call, "request_id", "unknown")
        tool_name = getattr(call, "tool_name", "unknown")

        self.metrics.increment("gateway.requests")
        self.metrics.increment("requests.total")

        try:
            # Resolve tool and version.
            try:
                spec = self.registry.get(
                    call.tool_name,
                    call.version,
                )
            except (KeyError, LookupError, ValueError):
                spec = None

            if spec is None:
                self.metrics.increment("requests.not_found")
                self.metrics.increment("outcome.denied")
                self._emit(
                    "gateway_tool_not_found",
                    request_id=request_id,
                    tool_name=tool_name,
                )
                return self._result(ToolStatus.DENIED)

            # Authorize the caller before any external request.
            role = self._resolve_role(call, principal)

            if role not in spec.roles:
                self.metrics.increment("requests.denied")
                self.metrics.increment("outcome.denied")
                self._emit(
                    "gateway_access_denied",
                    request_id=request_id,
                    tool_name=tool_name,
                    role=role,
                )
                return self._result(ToolStatus.DENIED)

            # Enforce the rolling-window rate limit.
            principal_id = self._resolve_principal_id(
                call,
                principal,
                role,
            )

            if not self._check_rate_limit(principal_id):
                self.metrics.increment("requests.rate_limited")
                self.metrics.increment("outcome.rate_limited")
                self._emit(
                    "gateway_rate_limited",
                    request_id=request_id,
                    tool_name=tool_name,
                )
                return self._result(
                    ToolStatus.RATE_LIMITED,
                    next_action="Retry after the rate limit window resets.",
                )

            # Validate input before calling the REST API.
            try:
                arguments = spec.input_model.model_validate(
                    call.arguments
                )
            except (ValidationError, TypeError, ValueError):
                self.metrics.increment("requests.invalid")
                self.metrics.increment("outcome.invalid")
                self._emit(
                    "gateway_invalid_arguments",
                    request_id=request_id,
                    tool_name=tool_name,
                )
                return self._result(ToolStatus.INVALID)

            # Establish idempotency for write operations.
            is_write = self._is_write(spec)
            effective_key = idempotency_key or request_id
            fingerprint = self._fingerprint(call)

            if is_write and effective_key:
                try:
                    cached = self.idempotency_store.get(
                        effective_key,
                        fingerprint,
                    )
                except IdempotencyConflict:
                    self.metrics.increment("requests.invalid")
                    self.metrics.increment("outcome.invalid")
                    self._emit(
                        "gateway_idempotency_conflict",
                        request_id=request_id,
                        tool_name=tool_name,
                    )
                    return self._result(
                        ToolStatus.INVALID,
                        next_action=(
                            "Use a new idempotency key for a different request."
                        ),
                    )

                if cached is not None:
                    self.metrics.increment(
                        "requests.idempotency_replayed"
                    )
                    self.metrics.increment("idempotency.cache_hit")
                    self.metrics.increment("outcome.ok")
                    self._emit(
                        "gateway_idempotency_replay",
                        request_id=request_id,
                        tool_name=tool_name,
                    )
                    return cached

            # Execute the REST handler.
            try:
                raw_output = self._invoke_handler(
                    spec,
                    arguments,
                )
            except Exception as exc:
                status = self._map_exception(exc)
                status_name = status.value.lower()

                self.metrics.increment(f"requests.{status_name}")
                self.metrics.increment(f"outcome.{status_name}")

                self._emit(
                    "gateway_execution_failed",
                    request_id=request_id,
                    tool_name=tool_name,
                    status=status.value,
                    error_type=type(exc).__name__,
                )

                next_action = (
                    "review_provider_response"
                    if status == ToolStatus.PROVIDER_ERROR
                    else "Check the error and retry if appropriate."
                )

                return self._result(
                    status,
                    next_action=next_action,
                )

            # Validate the provider response.
            try:
                validated = spec.output_model.model_validate(
                    raw_output
                )
                output_data = validated.model_dump(mode="json")
            except (ValidationError, TypeError, ValueError):
                self.metrics.increment("requests.provider_error")
                self.metrics.increment("outcome.provider_error")
                self._emit(
                    "gateway_invalid_provider_response",
                    request_id=request_id,
                    tool_name=tool_name,
                )
                return self._result(
                    ToolStatus.PROVIDER_ERROR,
                    next_action="review_provider_response",
                )

            result = self._result(
                ToolStatus.OK,
                data=output_data,
            )

            # Cache successful write operations.
            if is_write and effective_key:
                try:
                    self.idempotency_store.put(
                        effective_key,
                        fingerprint,
                        result,
                    )
                except IdempotencyConflict:
                    self.metrics.increment("requests.invalid")
                    self.metrics.increment("outcome.invalid")
                    self._emit(
                        "gateway_idempotency_conflict",
                        request_id=request_id,
                        tool_name=tool_name,
                    )
                    return self._result(ToolStatus.INVALID)

            self.metrics.increment("requests.success")
            self.metrics.increment("outcome.ok")
            self._emit(
                "gateway_execution_succeeded",
                request_id=request_id,
                tool_name=tool_name,
                status=ToolStatus.OK.value,
            )
            return result

        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            self.metrics.record_latency(elapsed_ms)
            self._emit(
                "gateway_execution_completed",
                request_id=request_id,
                duration_ms=round(elapsed_ms, 2),
            )


def dispatch(
    call: ToolCall,
    principal: Any,
    registry: ToolRegistry,
    client: Any,
) -> ToolResult:
    """Compatibility entry point for Tasks 2 and 3."""
    try:
        spec = registry.get(call.tool_name, call.version)
    except (KeyError, LookupError, ValueError):
        spec = None

    # Unknown tools and versions are denied before any HTTP request.
    if spec is None:
        return ToolResult(
            status=ToolStatus.DENIED,
            data={},
            next_action="Use a registered tool and supported version.",
            events=[],
        )

    gateway = ToolGateway(registry, client)
    return gateway.execute(call, principal)
