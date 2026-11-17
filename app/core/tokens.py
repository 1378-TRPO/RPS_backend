from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import AuthSettings
from app.models import UserRole

ALGORITHM = "HS256"


def create_access_token(user_id: UUID, role: UserRole, settings: AuthSettings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "role": role.value,
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str, settings: AuthSettings) -> UUID:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "role", "iat", "exp", "iss", "aud"]},
        )
        UserRole(claims["role"])
        if type(claims["iat"]) is not int or type(claims["exp"]) is not int:
            raise ValueError("Invalid token timestamps")
        if claims["exp"] <= claims["iat"]:
            raise ValueError("Invalid token lifetime")
        return UUID(claims["sub"])
    except (TypeError, ValueError, AttributeError, OverflowError) as error:
        raise jwt.InvalidTokenError("Invalid token claims") from error
