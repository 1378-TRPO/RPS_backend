from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.auth import LoginRequest

# Unknown emails still perform an Argon2 verification, like known accounts.
DUMMY_PASSWORD_HASH = hash_password("dummy-password-not-used-for-any-account")


def authenticate_user(db: Session, data: LoginRequest) -> User | None:
    user = db.scalar(select(User).where(User.email == data.email))
    stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(data.password.get_secret_value(), stored_hash)
    if user is None or not password_valid:
        return None
    return user
