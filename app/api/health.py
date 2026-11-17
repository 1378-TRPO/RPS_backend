from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["Health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("", response_model=HealthResponse, summary="Проверка работы приложения")
def health() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Проверка соединения с базой данных",
    responses={503: {"description": "База данных недоступна"}},
)
def readiness(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from error
    return HealthResponse()
