from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models import Service, UserRole
from app.schemas.auth import ErrorResponse
from app.schemas.service import ServiceResponse

router = APIRouter(prefix="/services", tags=["Service catalog"])


@router.get(
    "",
    response_model=list[ServiceResponse],
    dependencies=[Depends(require_roles(UserRole.CLIENT))],
    summary="Получить каталог активных услуг",
    description=(
        "Услуги отсортированы по названию, при совпадении по возрастанию id. "
        "Если активных услуг нет, возвращается пустой массив."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Нет действительного Bearer-токена"},
        403: {"model": ErrorResponse, "description": "Доступно только клиенту"},
    },
)
def list_services(db: Annotated[Session, Depends(get_db)]) -> list[ServiceResponse]:
    statement = (
        select(Service)
        .where(Service.is_active.is_(True))
        .order_by(Service.name.asc(), Service.id.asc())
    )
    return [ServiceResponse.model_validate(service) for service in db.scalars(statement)]
