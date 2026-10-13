
from src.fake_rest_server import FakeOrderServer
from src.rest_client import RestOrderClient
from src.tool_setup import build_registry


def build_test_environment(timeout_seconds: float = 0.2):
    server = FakeOrderServer()
    server.start()

    client = RestOrderClient(
        base_url=server.base_url,
        timeout_seconds=timeout_seconds,
    )
    registry = build_registry()

    return server, client, registry
