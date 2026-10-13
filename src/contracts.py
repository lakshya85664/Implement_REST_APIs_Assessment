
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AccessMode(str, Enum):
    READ = "read"
    WRITE = "write"


class ToolStatus(str, Enum):
    OK = "ok"
    INVALID = "invalid"
    DENIED = "denied"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"
    FAILED = "failed"


class ToolCall(BaseModel):
    """Validated envelope for a tool invocation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=100)
    tool_name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=20)
    arguments: dict[str, Any]
    principal: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=50)


class ToolResult(BaseModel):
    """Stable result envelope returned by the gateway."""

    model_config = ConfigDict(extra="forbid")

    status: ToolStatus
    data: dict[str, Any] = Field(default_factory=dict)
    next_action: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
