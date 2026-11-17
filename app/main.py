from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.core.errors import validation_error_handler


def create_app() -> FastAPI:
    application = FastAPI(
        title="RPS auth-service",
        description="Сервис пользователей и доступа. Учебный проект RPS.",
        version="0.1.0",
    )
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.include_router(health_router)
    application.include_router(auth_router)
    return application


app = create_app()
