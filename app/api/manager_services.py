import json
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models import Service, UserRole
from app.schemas.auth import ErrorResponse
from app.schemas.service import ManagerServiceResponse, ServiceCreate, ServiceUpdate


class DecimalJSONRequest(Request):
    async def json(self) -> Any:
        # Preserve JSON price literals before validating their decimal scale.
        if not hasattr(self, "_decimal_json"):
            try:
                self._decimal_json = json.loads(await self.body(), parse_float=Decimal)
            except InvalidOperation as error:
                raise json.JSONDecodeError("Invalid decimal number", "", 0) from error
        return self._decimal_json


class DecimalJSONRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            return await handler(DecimalJSONRequest(request.scope, request.receive))

        return handle


router = APIRouter(
    prefix="/manager/services",
    tags=["Manager services"],
    route_class=DecimalJSONRoute,
    dependencies=[Depends(require_roles(UserRole.MANAGER))],
    responses={
        401: {"model": ErrorResponse, "description": "Нет действительного Bearer-токена"},
        403: {"model": ErrorResponse, "description": "Доступно только менеджеру"},
    },
)
DBSession = Annotated[Session, Depends(get_db)]
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Услуга не найдена"}}


def get_service(db: Session, service_id: UUID) -> Service:
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


@router.get("", summary="Список активных и неактивных услуг")
def list_services(db: DBSession) -> list[ManagerServiceResponse]:
    statement = select(Service).order_by(Service.name.asc(), Service.id.asc())
    return [ManagerServiceResponse.model_validate(service) for service in db.scalars(statement)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать активную услугу",
)
def create_service(data: ServiceCreate, db: DBSession) -> ManagerServiceResponse:
    service = Service(**data.model_dump())
    db.add(service)
    db.flush()
    result = ManagerServiceResponse.model_validate(service)
    db.commit()
    return result


@router.patch(
    "/{service_id}",
    summary="Изменить переданные поля услуги",
    responses=NOT_FOUND,
)
def update_service(service_id: UUID, data: ServiceUpdate, db: DBSession) -> ManagerServiceResponse:
    service = get_service(db, service_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    result = ManagerServiceResponse.model_validate(service)
    db.commit()
    return result


@router.delete(
    "/{service_id}",
    summary="Деактивировать услугу",
    description="Повторный запрос возвращает ту же неактивную услугу.",
    responses=NOT_FOUND,
)
def deactivate_service(service_id: UUID, db: DBSession) -> ManagerServiceResponse:
    service = get_service(db, service_id)
    service.is_active = False
    result = ManagerServiceResponse.model_validate(service)
    db.commit()
    return result
