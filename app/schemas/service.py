from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


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
