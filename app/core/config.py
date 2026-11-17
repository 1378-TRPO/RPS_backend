from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(min_length=1, repr=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    jwt_secret: SecretStr = Field(min_length=32, repr=False)
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    jwt_issuer: str = Field(default="rps-auth-service", min_length=1)
    jwt_audience: str = Field(default="rps-api", min_length=1)

    @field_validator("jwt_secret")
    @classmethod
    def reject_blank_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("JWT_SECRET must not be blank")
        return value


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
