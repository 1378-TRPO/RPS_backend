from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models import User, UserRole, Vehicle
from app.schemas.auth import ErrorResponse
from app.schemas.profile import ClientProfile, ProfileUpdate
from app.schemas.vehicle import VehicleCreate, VehicleResponse
from app.services.profile import update_client_profile
from app.services.registration import EmailAlreadyRegisteredError

router = APIRouter(
    prefix="/users",
    tags=["Client profile"],
    responses={
        401: {"model": ErrorResponse, "description": "Нет действительного Bearer-токена"},
        403: {"model": ErrorResponse, "description": "Профиль доступен только клиенту"},
    },
)
CurrentClient = Annotated[User, Depends(require_roles(UserRole.CLIENT))]


@router.get(
    "/me",
    response_model=ClientProfile,
    summary="Просмотр своего профиля клиента",
    description=(
        "Имя, телефон и email текущего клиента. Имя и телефон могут быть null. "
        "Пользователь определяется только по JWT; чужой профиль запросить нельзя."
    ),
)
def get_profile(user: CurrentClient) -> ClientProfile:
    return ClientProfile.model_validate(user)


@router.patch(
    "/me",
    response_model=ClientProfile,
    summary="Изменение своего профиля клиента",
    description=(
        "Передайте хотя бы одно поле: name, phone, email. Неуказанные поля сохраняются. "
        "null очищает имя или телефон; email не может быть null и должен быть уникальным. "
        "Имя: 1–100 символов после удаления внешних пробелов. Телефон: + и 7–15 цифр, "
        "первая цифра не 0. Email нормализуется как при регистрации. "
        "Изменять роль, пароль и чужие данные через эту ручку нельзя."
    ),
    responses={
        409: {
            "model": ErrorResponse,
            "description": "Email уже зарегистрирован",
            "content": {"application/json": {"example": {"detail": "Email already registered"}}},
        },
        422: {"description": "Некорректные данные, лишние поля или пустое тело изменений"},
    },
)
def patch_profile(
    data: ProfileUpdate,
    user: CurrentClient,
    db: Annotated[Session, Depends(get_db)],
) -> ClientProfile:
    try:
        updated = update_client_profile(db, user, data)
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from error
    return ClientProfile.model_validate(updated)


@router.post(
    "/me/vehicles",
    response_model=VehicleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавление автомобиля в свой гараж",
    description=(
        "Клиент определяется по Bearer JWT. В запросе обязательны make, model, year и plate. "
        "Краевые пробелы убираются. Год передаётся целым числом. "
        "Поля владельца в запросе запрещены. Формат госномера свободный."
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Добавление доступно только клиенту"},
        422: {"description": "Некорректные, отсутствующие или лишние поля"},
    },
)
def add_vehicle(
    data: VehicleCreate,
    user: CurrentClient,
    db: Annotated[Session, Depends(get_db)],
) -> VehicleResponse:
    vehicle = Vehicle(client_id=user.id, **data.model_dump())
    db.add(vehicle)
    db.flush()
    result = VehicleResponse.model_validate(vehicle)
    db.commit()
    return result
