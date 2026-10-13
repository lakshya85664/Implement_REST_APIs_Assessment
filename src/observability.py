
import json
import time
from collections import Counter
from threading import Lock
from typing import Any


class Metrics:
    def __init__(self):
        self._counts: Counter[str] = Counter()
        self._latencies_ms: list[float] = []
        self._lock = Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counts[name] += amount

    def record_latency(self, milliseconds: float) -> None:
        with self._lock:
            self._latencies_ms.append(milliseconds)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = list(self._latencies_ms)
            counts = dict(self._counts)

        return {
            "counters": counts,
            "latency_count": len(latencies),
            "latency_mean_ms": (
                round(sum(latencies) / len(latencies), 3)
                if latencies else 0.0
            ),
            "latency_max_ms": (
                round(max(latencies), 3)
                if latencies else 0.0
            ),
        }


class EventLogger:
    """Structured logger that omits request arguments and secrets."""

    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self._lock = Lock()

    def emit(self, event: str, **fields: Any) -> None:
        safe_fields = {
            key: value
            for key, value in fields.items()
            if key.lower() not in {
                "arguments", "authorization", "api_key",
                "token", "password", "secret",
            }
        }

        record = {
            "timestamp": time.time(),
            "event": event,
            **safe_fields,
        }

        with self._lock:
            self.events.append(record)

    def export_json(self) -> str:
        with self._lock:
            snapshot = list(self.events)

        return json.dumps(snapshot, indent=2)
