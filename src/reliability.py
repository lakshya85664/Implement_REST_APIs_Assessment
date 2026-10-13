
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


class RateLimitExceeded(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


@dataclass
class CachedResult:
    fingerprint: str
    value: object
    created_at: float


class RateLimiter:
    """Thread-safe process-local sliding-window rate limiter."""

    def __init__(self, limit: int = 10, window_seconds: float = 60.0):
        if limit < 1 or window_seconds <= 0:
            raise ValueError("Limit and window must be positive")

        self.limit = limit
        self.window_seconds = window_seconds
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            calls = self._calls[key]

            while calls and calls[0] <= cutoff:
                calls.popleft()

            if len(calls) >= self.limit:
                return False

            calls.append(now)
            return True


class IdempotencyStore:
    """In-memory successful-result cache keyed by request identifier."""

    def __init__(self):
        self._entries: dict[str, CachedResult] = {}
        self._lock = threading.Lock()

    def get(self, key: str, fingerprint: str):
        with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                return None

            if entry.fingerprint != fingerprint:
                raise IdempotencyConflict(
                    "Idempotency key reused with different request"
                )

            return entry.value

    def put(self, key: str, fingerprint: str, value: object) -> None:
        with self._lock:
            existing = self._entries.get(key)

            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise IdempotencyConflict(
                        "Idempotency key reused with different request"
                    )
                return

            self._entries[key] = CachedResult(
                fingerprint=fingerprint,
                value=value,
                created_at=time.monotonic(),
            )


def call_with_retries(
    operation: Callable[[], T],
    retry_exceptions: tuple[type[Exception], ...],
    max_retries: int = 2,
) -> tuple[T, int]:
    """Return the operation result and number of retries performed."""

    if max_retries < 0:
        raise ValueError("max_retries cannot be negative")

    retries = 0

    while True:
        try:
            return operation(), retries
        except retry_exceptions:
            if retries >= max_retries:
                raise

            retries += 1
            time.sleep(0.02 * retries)
