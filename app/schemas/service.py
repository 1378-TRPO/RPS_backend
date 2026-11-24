from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema


def reject_null_character(value: str) -> str:
    if "\x00" in value:
        raise ValueError("NUL characters are not allowed")
    return value


def reject_extra_fractional_digits(value: Decimal) -> Decimal:
    if value.as_tuple().exponent < -2:
        raise ValueError("Price must have at most two fractional digits")
    return value


ServiceText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
    AfterValidator(reject_null_character),
]
ServicePrice = Annotated[
    Decimal,
    Field(gt=0, max_digits=12, decimal_places=2, examples=["1250.50"]),
    AfterValidator(reject_extra_fractional_digits),
]
ServiceDuration = Annotated[int, Field(strict=True, gt=0, le=2**31 - 1)]


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: ServiceText
    description: ServiceText
    price: ServicePrice
    duration_minutes: ServiceDuration


class ServiceUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid", hide_input_in_errors=True, json_schema_extra={"minProperties": 1}
    )

    name: ServiceText | SkipJsonSchema[None] = None
    description: ServiceText | SkipJsonSchema[None] = None
    price: ServicePrice | SkipJsonSchema[None] = None
    duration_minutes: ServiceDuration | SkipJsonSchema[None] = None

    @field_validator("name", "description", "price", "duration_minutes", mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field must not be null")
        return value

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one service field is required")
        return self


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    price: Decimal = Field(
        description="Десятичная строка с двумя знаками после точки.",
        examples=["1250.50"],
    )
    duration_minutes: int

    @field_serializer("price", when_used="json")
    def serialize_price(self, price: Decimal) -> str:
        return format(price, ".2f")


class ManagerServiceResponse(ServiceResponse):
    is_active: bool
