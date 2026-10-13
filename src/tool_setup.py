
from typing import Any

from src.contracts import AccessMode
from src.registry import ToolRegistry, ToolSpec
from src.schemas import (
    OrderLookupInput,
    OrderLookupOutput,
    OrderUpdateInput,
    OrderUpdateOutput,
)


def handle_order_lookup(arguments: OrderLookupInput, client: Any) -> dict[str, Any]:
    return client.lookup(arguments.order_id)


def handle_order_update(arguments: OrderUpdateInput, client: Any) -> dict[str, Any]:
    return client.update(arguments.order_id, arguments.new_status)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        ToolSpec(
            name="order_lookup",
            version="1.0",
            access_mode=AccessMode.READ,
            roles=frozenset({"viewer", "operator", "admin"}),
            input_model=OrderLookupInput,
            output_model=OrderLookupOutput,
            handler=handle_order_lookup,
        )
    )

    registry.register(
        ToolSpec(
            name="order_update",
            version="1.0",
            access_mode=AccessMode.WRITE,
            roles=frozenset({"operator", "admin"}),
            input_model=OrderUpdateInput,
            output_model=OrderUpdateOutput,
            handler=handle_order_update,
        )
    )

    return registry
