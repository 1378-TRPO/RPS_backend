from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.services import router as services_router
from app.api.users import router as users_router
from app.core.errors import validation_error_handler


def create_app() -> FastAPI:
    application = FastAPI(
        title="RPS auth-service",
        description="Пользователи, доступ и каталог услуг. Учебный проект RPS.",
        version="0.1.0",
    )
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(users_router)
    application.include_router(services_router)
    return application


app = create_app()
