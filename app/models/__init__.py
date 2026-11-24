"""Import models so SQLAlchemy and Alembic discover all tables."""

from app.models.service import Service
from app.models.user import User, UserRole
from app.models.vehicle import Vehicle

__all__ = ["Service", "User", "UserRole", "Vehicle"]
