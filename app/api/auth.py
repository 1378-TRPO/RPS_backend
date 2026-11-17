from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import ErrorResponse, RegisteredUser, RegisterRequest
from app.services.registration import EmailAlreadyRegisteredError, register_client

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=RegisteredUser,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация клиента по email и паролю",
    description=(
        "Публичная регистрация с ролью client. Email сравнивается без учёта регистра. "
        "Пароль: 8–128 символов, пробелы сохраняются. Дополнительные поля запрещены. "
        "Пароль, его хеш и JWT в ответе не возвращаются."
    ),
    responses={
        409: {
            "model": ErrorResponse,
            "description": "Email уже зарегистрирован",
            "content": {"application/json": {"example": {"detail": "Email already registered"}}},
        },
        422: {"description": "Некорректные данные; входные значения в ошибке не возвращаются"},
    },
)
def register(data: RegisterRequest, db: Annotated[Session, Depends(get_db)]) -> RegisteredUser:
    try:
        user = register_client(db, data)
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from error
    return RegisteredUser.model_validate(user)
