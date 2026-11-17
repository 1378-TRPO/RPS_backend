from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.models import UserRole


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    email: EmailStr = Field(max_length=254, examples=["client@example.com"])

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class RegisterRequest(EmailRequest):
    password: SecretStr = Field(min_length=8, max_length=128, repr=False)


class LoginRequest(EmailRequest):
    password: SecretStr = Field(min_length=1, max_length=128, repr=False)


class RegisteredUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: Literal["client"]
    created_at: datetime


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: UserRole
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0, description="Срок действия access token в секундах")


class ErrorResponse(BaseModel):
    detail: str
