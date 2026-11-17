from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

ProfileName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Phone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\+[1-9][0-9]{6,14}$", max_length=16),
]


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid", hide_input_in_errors=True, json_schema_extra={"minProperties": 1}
    )

    name: ProfileName | None = Field(default=None, examples=["Иван Петров"])
    phone: Phone | None = Field(default=None, examples=["+79991234567"])
    # May be omitted, but explicit null is rejected and not advertised in OpenAPI.
    email: Annotated[EmailStr, Field(max_length=254)] | SkipJsonSchema[None] = Field(
        default=None, examples=["client@example.com"]
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Email must not be null")
        return value.lower()

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one profile field is required")
        return self


class ClientProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    phone: str | None
    email: EmailStr
