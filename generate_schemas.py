
import json
from pathlib import Path

from src.schemas import (
    OrderLookupInput,
    OrderLookupOutput,
    OrderUpdateInput,
    OrderUpdateOutput,
)
from src.tool_setup import build_registry


SCHEMA_DIR = Path("schemas")
SCHEMA_DIR.mkdir(exist_ok=True)

schemas = {
    "order_lookup_input.json": OrderLookupInput.model_json_schema(),
    "order_lookup_output.json": OrderLookupOutput.model_json_schema(),
    "order_update_input.json": OrderUpdateInput.model_json_schema(),
    "order_update_output.json": OrderUpdateOutput.model_json_schema(),
    "registry.json": build_registry().list_tools(),
}

for filename, schema in schemas.items():
    path = SCHEMA_DIR / filename
    path.write_text(
        json.dumps(schema, indent=2),
        encoding="utf-8",
    )
    print(f"Created: {path}")
