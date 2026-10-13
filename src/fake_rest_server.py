
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any
from urllib.parse import urlparse


class FakeOrderServer:
    """Local HTTP server for deterministic REST API tests."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.orders: dict[str, dict[str, Any]] = {
            "ORD-1001": {
                "order_id": "ORD-1001",
                "status": "processing",
                "amount": 1499.0,
            },
            "ORD-1002": {
                "order_id": "ORD-1002",
                "status": "shipped",
                "amount": 2499.0,
            },
        }
        self.lock = threading.Lock()
        self.request_counts: dict[str, int] = {}
        self.failure_modes: dict[str, str] = {}
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def _json(self, status_code: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                try:
                    self.send_response(status_code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # The client may have disconnected after a timeout.
                    pass

            def _mode(self, key: str) -> str | None:
                return owner.failure_modes.get(key)

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                with owner.lock:
                    owner.request_counts[path] = (
                        owner.request_counts.get(path, 0) + 1
                    )
                    mode = self._mode(path)

                if mode == "timeout":
                    # Delay beyond the client's configured timeout.
                    threading.Event().wait(0.5)
                elif mode == "server_error":
                    self._json(503, {"error": "provider unavailable"})
                    return
                elif mode == "malformed_json":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b"{malformed")
                    return

                prefix = "/orders/"
                if not path.startswith(prefix):
                    self._json(404, {"error": "not found"})
                    return

                order_id = path.removeprefix(prefix)
                with owner.lock:
                    order = owner.orders.get(order_id)

                if order is None:
                    self._json(404, {"error": "order not found"})
                    return

                self._json(200, order)

            def do_PATCH(self) -> None:
                path = urlparse(self.path).path
                with owner.lock:
                    owner.request_counts[path] = (
                        owner.request_counts.get(path, 0) + 1
                    )
                    mode = self._mode(path)

                if mode == "timeout":
                    threading.Event().wait(0.5)
                elif mode == "server_error":
                    self._json(503, {"error": "provider unavailable"})
                    return

                prefix = "/orders/"
                if not path.startswith(prefix):
                    self._json(404, {"error": "not found"})
                    return

                order_id = path.removeprefix(prefix)
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    payload = json.loads(self.rfile.read(length))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._json(400, {"error": "invalid JSON"})
                    return

                new_status = payload.get("status")
                allowed = {"processing", "shipped", "cancelled"}
                if new_status not in allowed:
                    self._json(422, {"error": "invalid status"})
                    return

                with owner.lock:
                    order = owner.orders.get(order_id)
                    if order is None:
                        self._json(404, {"error": "order not found"})
                        return
                    order["status"] = new_status
                    response = {**order, "updated": True}

                self._json(200, response)

            def log_message(self, format: str, *args: Any) -> None:
                # Keep standard HTTP server logs quiet in the test output.
                return

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None
