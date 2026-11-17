"""Import models so SQLAlchemy and Alembic discover all tables."""

from app.models.user import User, UserRole

__all__ = ["User", "UserRole"]
