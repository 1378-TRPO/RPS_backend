from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

MIN_YEAR = 1900
MAX_YEAR_AHEAD = 1

VehicleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
VehiclePlate = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class VehicleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    make: VehicleName = Field(examples=["Toyota"])
    model: VehicleName = Field(examples=["Corolla"])
    year: int = Field(
        ge=MIN_YEAR,
        description="От 1900 до текущего года + 1 включительно.",
        examples=[2020],
    )
    plate: VehiclePlate = Field(examples=["XY 123-Z"])

    @field_validator("year")
    @classmethod
    def validate_year_limit(cls, value: int) -> int:
        max_year = date.today().year + MAX_YEAR_AHEAD
        if value > max_year:
            raise ValueError(f"Year must be {max_year} or earlier")
        return value

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
