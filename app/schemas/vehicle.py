from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

VehicleText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class VehicleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    make: VehicleText = Field(examples=["Toyota"])
    model: VehicleText = Field(examples=["Corolla"])
    year: int = Field(ge=-(2**31), le=2**31 - 1, examples=[2020])
    plate: VehicleText = Field(examples=["XY 123-Z"])

    @field_validator("make", "model", "plate")
    @classmethod
    def reject_null_character(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("NUL characters are not allowed")
        return value


class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    make: str
    model: str
    year: int
    plate: str
    created_at: datetime
