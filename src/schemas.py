
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order_id: str = Field(
        min_length=4,
        max_length=30,
        pattern=r"^ORD-[0-9]{4}$",
    )


class OrderUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order_id: str = Field(
        min_length=4,
        max_length=30,
        pattern=r"^ORD-[0-9]{4}$",
    )
    new_status: Literal["processing", "shipped", "cancelled"]


class OrderLookupOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    status: str
    amount: float = Field(ge=0)


class OrderUpdateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    status: Literal["processing", "shipped", "cancelled"]
    amount: float = Field(ge=0)
    updated: bool
