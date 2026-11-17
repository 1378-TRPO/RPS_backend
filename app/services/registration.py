from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import User, UserRole
from app.schemas.auth import RegisterRequest


class EmailAlreadyRegisteredError(Exception):
    pass


def register_client(db: Session, data: RegisterRequest) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise EmailAlreadyRegisteredError

    user = User(
        email=data.email,
        password_hash=hash_password(data.password.get_secret_value()),
        role=UserRole.CLIENT,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A second request can insert the same email after our initial SELECT.
        # Only an email conflict becomes 409; unrelated DB failures stay errors.
        if db.scalar(select(User.id).where(User.email == data.email)) is not None:
            raise EmailAlreadyRegisteredError from None
        raise
    db.refresh(user)
    return user
