
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from src.contracts import AccessMode


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    access_mode: AccessMode
    roles: frozenset[str]
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[..., Any] | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[tuple[str, str], ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        key = (spec.name, spec.version)

        if key in self._tools:
            raise ValueError(
                f"Tool already registered: {spec.name}@{spec.version}"
            )

        self._tools[key] = spec

    def get(self, name: str, version: str) -> ToolSpec | None:
        return self._tools.get((name, version))

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "version": spec.version,
                "access_mode": spec.access_mode.value,
                "roles": sorted(spec.roles),
                "input_schema": spec.input_model.model_json_schema(),
                "output_schema": spec.output_model.model_json_schema(),
            }
            for spec in sorted(
                self._tools.values(),
                key=lambda item: (item.name, item.version),
            )
        ]
