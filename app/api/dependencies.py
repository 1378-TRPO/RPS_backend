from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import AuthSettings, get_auth_settings
from app.core.tokens import decode_access_token
from app.db.session import get_db
from app.models import User, UserRole

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="JWT из POST /auth/login. В Swagger вставьте только access_token.",
)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> User:
    if credentials is None:
        raise unauthorized("Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError as error:
        raise unauthorized("Invalid or expired token") from error

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized("Invalid or expired token")
    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    if not roles:
        raise ValueError("At least one allowed role is required")

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        # The database is authoritative; the token's role is only a snapshot.
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return user

    return dependency
