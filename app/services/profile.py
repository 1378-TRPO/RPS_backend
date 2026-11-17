from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.schemas.profile import ProfileUpdate
from app.services.registration import EmailAlreadyRegisteredError


def update_client_profile(db: Session, user: User, data: ProfileUpdate) -> User:
    changes = data.model_dump(exclude_unset=True)
    new_email = changes.get("email")
    user_id = user.id

    def email_taken() -> bool:
        return (
            db.scalar(select(User.id).where(User.email == new_email, User.id != user_id))
            is not None
        )

    if new_email is not None and email_taken():
        raise EmailAlreadyRegisteredError

    for field, value in changes.items():
        setattr(user, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A competing request can claim the email after our initial SELECT.
        if new_email is not None and email_taken():
            raise EmailAlreadyRegisteredError from None
        raise
    db.refresh(user)
    return user
