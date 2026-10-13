
import pytest
from pydantic import ValidationError

from src.contracts import AccessMode
from src.registry import ToolRegistry, ToolSpec
from src.schemas import (
    OrderLookupInput,
    OrderLookupOutput,
    OrderUpdateInput,
    OrderUpdateOutput,
)
from src.tool_setup import build_registry


def test_valid_lookup_input():
    result = OrderLookupInput(order_id="ORD-1001")
    assert result.order_id == "ORD-1001"


@pytest.mark.parametrize(
    "payload",
    [
        {"order_id": "1001"},
        {"order_id": "ORD-ABC1"},
        {"order_id": ""},
        {"order_id": "ORD-1001", "unexpected": True},
    ],
)
def test_invalid_lookup_input(payload):
    with pytest.raises(ValidationError):
        OrderLookupInput.model_validate(payload)


def test_valid_update_input():
    result = OrderUpdateInput(
        order_id="ORD-1001",
        new_status="shipped",
    )
    assert result.new_status == "shipped"


def test_invalid_update_status():
    with pytest.raises(ValidationError):
        OrderUpdateInput(
            order_id="ORD-1001",
            new_status="delivered",
        )


def test_output_schema_rejects_negative_amount():
    with pytest.raises(ValidationError):
        OrderLookupOutput(
            order_id="ORD-1001",
            status="processing",
            amount=-1,
        )


def test_registry_contains_versioned_tools():
    registry = build_registry()

    assert registry.get("order_lookup", "1.0") is not None
    assert registry.get("order_update", "1.0") is not None
    assert registry.get("order_lookup", "2.0") is None


def test_registry_access_modes_and_roles():
    registry = build_registry()
    lookup = registry.get("order_lookup", "1.0")
    update = registry.get("order_update", "1.0")

    assert lookup is not None
    assert update is not None
    assert lookup.access_mode == AccessMode.READ
    assert update.access_mode == AccessMode.WRITE
    assert "viewer" in lookup.roles
    assert "viewer" not in update.roles


def test_duplicate_registration_is_rejected():
    registry = ToolRegistry()
    spec = ToolSpec(
        name="order_lookup",
        version="1.0",
        access_mode=AccessMode.READ,
        roles=frozenset({"viewer"}),
        input_model=OrderLookupInput,
        output_model=OrderLookupOutput,
    )

    registry.register(spec)

    with pytest.raises(ValueError):
        registry.register(spec)


def test_registry_lists_json_schemas():
    entries = build_registry().list_tools()

    assert len(entries) == 2
    assert entries[0]["input_schema"]["type"] == "object"
    assert entries[1]["output_schema"]["type"] == "object"
