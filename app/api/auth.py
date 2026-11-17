from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, unauthorized
from app.core.config import AuthSettings, get_auth_settings
from app.core.tokens import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    AuthenticatedUser,
    ErrorResponse,
    LoginRequest,
    RegisteredUser,
    RegisterRequest,
    TokenResponse,
)
from app.services.authentication import authenticate_user
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


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход по email и паролю; получение JWT",
    description=(
        "Принимает JSON с email и паролем. Неверный пароль и неизвестный email "
        "дают одинаковый ответ 401. Работает для клиента, механика и менеджера."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Неверный email или пароль"},
        422: {"description": "Некорректный формат запроса"},
    },
)
def login(
    data: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> TokenResponse:
    user = authenticate_user(db, data)
    if user is None:
        raise unauthorized("Invalid email or password")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, settings),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get(
    "/me",
    response_model=AuthenticatedUser,
    summary="Текущая учётная запись и роль",
    description=(
        "Требуется Authorization: Bearer <access_token>. Доступно всем трём ролям. "
        "Пользователь и актуальная роль читаются из БД; пароль и хеш не возвращаются. "
        "Это проверка учётной записи, а не редактирование профиля из задачи 1.3."
    ),
    responses={401: {"model": ErrorResponse, "description": "Нет токена или токен недействителен"}},
)
def me(user: Annotated[User, Depends(get_current_user)]) -> AuthenticatedUser:
    return AuthenticatedUser.model_validate(user)
