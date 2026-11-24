from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import AuthSettings
from app.core.tokens import create_access_token
from app.models import Service, UserRole
from app.schemas.auth import RegisterRequest
from app.services.registration import create_staff_user, register_client

PATH = "/manager/services"
PASSWORD = "catalog-test-password"
SERVICE_DATA = {
    "name": "Диагностика",
    "description": "Проверка состояния автомобиля",
    "price": "1250.50",
    "duration_minutes": 45,
}
REQUESTS = [
    ("GET", PATH, None),
    ("POST", PATH, SERVICE_DATA),
    ("PATCH", f"{PATH}/{UUID(int=1)}", {"duration_minutes": 60}),
    ("DELETE", f"{PATH}/{UUID(int=1)}", None),
]


def bearer(user_id: UUID, role: UserRole, settings: AuthSettings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role, settings)}"}


@pytest.fixture
def manager_headers(db: Session, auth_settings: AuthSettings) -> dict[str, str]:
    manager = create_staff_user(
        db, RegisterRequest(email="manager@example.com", password=PASSWORD), UserRole.MANAGER
    )
    return bearer(manager.id, manager.role, auth_settings)


def test_manager_catalog_lifecycle(
    client: TestClient, db: Session, auth_settings: AuthSettings, manager_headers: dict[str, str]
) -> None:
    customer = register_client(db, RegisterRequest(email="customer@example.com", password=PASSWORD))
    customer_headers = bearer(customer.id, customer.role, auth_settings)
    assert client.get(PATH, headers=manager_headers).json() == []
    created = client.post(
        PATH,
        headers=manager_headers,
        json={
            **SERVICE_DATA,
            "name": "  Диагностика  ",
            "description": "  Проверка состояния автомобиля ",
        },
    )
    assert created.status_code == 201
    service_id = UUID(created.json()["id"])
    url = f"{PATH}/{service_id}"
    expected = {"id": str(service_id), **SERVICE_DATA, "is_active": True}
    assert created.json() == expected
    manager_list = client.get(PATH, headers=manager_headers)
    assert manager_list.status_code == 200
    assert manager_list.json() == [expected]
    public = {field: value for field, value in expected.items() if field != "is_active"}
    assert client.get("/services", headers=customer_headers).json() == [public]

    changes = {
        "name": " Расширенная диагностика ",
        "description": " Осмотр всех систем ",
        "price": "9999999999.99",
        "duration_minutes": 75,
    }
    updated = client.patch(url, headers=manager_headers, json=changes)
    assert updated.status_code == 200
    expected.update(
        name="Расширенная диагностика",
        description="Осмотр всех систем",
        price="9999999999.99",
        duration_minutes=75,
    )
    assert updated.json() == expected
    partial = client.patch(url, headers=manager_headers, json={"price": 2000})
    assert partial.status_code == 200
    expected["price"] = "2000.00"
    assert partial.json() == expected
    service = db.get(Service, service_id)
    assert service is not None and service.price == Decimal("2000.00")

    deactivated = client.delete(url, headers=manager_headers)
    assert deactivated.status_code == 200
    expected["is_active"] = False
    assert deactivated.json() == expected
    db.expire_all()
    existing = db.get(Service, service_id)
    assert existing is not None and existing.is_active is False
    assert db.scalar(select(func.count()).select_from(Service)) == 1
    assert client.get(PATH, headers=manager_headers).json() == [expected]
    assert client.get("/services", headers=customer_headers).json() == []

    repeated = client.delete(url, headers=manager_headers)
    assert repeated.status_code == 200
    assert repeated.json() == expected
    rename_archived = client.patch(url, headers=manager_headers, json={"name": "Архив"})
    assert rename_archived.status_code == 200
    assert rename_archived.json()["is_active"] is False
    assert client.get("/services", headers=customer_headers).json() == []


@pytest.mark.parametrize("authorization", [None, "Bearer invalid"])
def test_manager_endpoints_require_valid_jwt(client: TestClient, authorization: str | None) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    for method, path, body in REQUESTS:
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("role", [UserRole.CLIENT, UserRole.MECHANIC])
def test_manager_endpoints_deny_client_and_mechanic(
    client: TestClient, db: Session, auth_settings: AuthSettings, role: UserRole
) -> None:
    data = RegisterRequest(email="operator@example.com", password=PASSWORD)
    user = (
        register_client(db, data) if role == UserRole.CLIENT else create_staff_user(db, data, role)
    )
    headers = bearer(user.id, user.role, auth_settings)
    for method, path, body in REQUESTS:
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 403
    assert db.scalar(select(func.count()).select_from(Service)) == 0


def test_missing_and_invalid_service_ids(
    client: TestClient, manager_headers: dict[str, str]
) -> None:
    for method, body in [("PATCH", {"duration_minutes": 30}), ("DELETE", None)]:
        missing = client.request(
            method, f"{PATH}/{UUID(int=1)}", headers=manager_headers, json=body
        )
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Service not found"}
        invalid = client.request(method, f"{PATH}/not-a-uuid", headers=manager_headers, json=body)
        assert invalid.status_code == 422


def test_invalid_service_values_rejected_on_create_and_update(
    client: TestClient, db: Session, manager_headers: dict[str, str]
) -> None:
    created = client.post(PATH, headers=manager_headers, json=SERVICE_DATA)
    assert created.status_code == 201
    url = f"{PATH}/{created.json()['id']}"
    invalid_fields = [
        {"name": " "},
        {"name": "x" * 201},
        {"name": 0},
        {"name": None},
        {"description": "\t"},
        {"description": "x" * 2001},
        {"description": None},
        {"description": "description\x00"},
        {"price": "0.00"},
        {"price": -1},
        {"price": "12.345"},
        {"price": "12.340"},
        {"price": "10000000000.00"},
        {"price": "NaN"},
        {"price": "Infinity"},
        {"price": True},
        {"price": None},
        {"price": "invalid"},
        {"duration_minutes": 0},
        {"duration_minutes": -1},
        {"duration_minutes": "45"},
        {"duration_minutes": 45.0},
        {"duration_minutes": True},
        {"duration_minutes": 2**31},
        {"duration_minutes": None},
        {"is_active": False},
        {"id": str(UUID(int=2))},
        {"updated_at": "2026-11-24"},
    ]
    for invalid in invalid_fields:
        response = client.post(PATH, headers=manager_headers, json={**SERVICE_DATA, **invalid})
        assert response.status_code == 422, invalid
        response = client.patch(url, headers=manager_headers, json=invalid)
        assert response.status_code == 422, invalid
    for field in SERVICE_DATA:
        missing = {key: value for key, value in SERVICE_DATA.items() if key != field}
        response = client.post(PATH, headers=manager_headers, json=missing)
        assert response.status_code == 422, field
    assert client.patch(url, headers=manager_headers, json={}).status_code == 422
    response = client.patch(
        url, headers=manager_headers, json={"name": "Should not persist", "price": "12.345"}
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(Service)) == 1
    assert client.get(PATH, headers=manager_headers).json() == [created.json()]


def test_service_text_limits_apply_after_trimming(
    client: TestClient, manager_headers: dict[str, str]
) -> None:
    name, description = "Н" * 200, "О" * 2000
    created = client.post(
        PATH,
        headers=manager_headers,
        json={**SERVICE_DATA, "name": f" {name} ", "description": f" {description} "},
    )
    assert created.status_code == 201
    assert created.json()["name"] == name
    assert created.json()["description"] == description

    name, description = "А" * 200, "Б" * 2000
    updated = client.patch(
        f"{PATH}/{created.json()['id']}",
        headers=manager_headers,
        json={"name": f" {name} ", "description": f" {description} "},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == name
    assert updated.json()["description"] == description


def test_numeric_price_preserves_exact_decimal_before_validating(
    client: TestClient, manager_headers: dict[str, str]
) -> None:
    headers = {**manager_headers, "Content-Type": "application/json"}
    created = client.post(
        PATH,
        headers=headers,
        content='{"name":"Diagnosis","description":"Checking","duration_minutes":45,"price":1250.50}',
    )
    assert created.status_code == 201
    assert created.json()["price"] == "1250.50"
    url = f"{PATH}/{created.json()['id']}"
    for invalid in [
        '{"price":1250.500000000000000001}',
        '{"price":1250.500}',
        '{"price":1e99999999999999999999999999}',
    ]:
        response = client.patch(url, headers=headers, content=invalid)
        assert response.status_code == 422
    assert client.get(PATH, headers=manager_headers).json() == [created.json()]


def test_manager_endpoints_are_documented(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for path, method, status_codes in [
        (PATH, "get", {"200", "401", "403"}),
        (PATH, "post", {"201", "401", "403", "422"}),
        (f"{PATH}/{{service_id}}", "patch", {"200", "401", "403", "404", "422"}),
        (f"{PATH}/{{service_id}}", "delete", {"200", "401", "403", "404", "422"}),
    ]:
        operation = paths[path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert status_codes <= operation["responses"].keys()
    schemas = schema["components"]["schemas"]
    assert set(schemas["ManagerServiceResponse"]["properties"]) == {
        "id",
        *SERVICE_DATA,
        "is_active",
    }
    assert schemas["ManagerServiceResponse"]["properties"]["price"]["type"] == "string"
    assert set(schemas["ServiceCreate"]["required"]) == set(SERVICE_DATA)
    assert schemas["ServiceUpdate"]["minProperties"] == 1
    assert schemas["ServiceUpdate"]["additionalProperties"] is False
    for request_model in ("ServiceCreate", "ServiceUpdate"):
        fields = schemas[request_model]["properties"]
        assert fields["name"]["maxLength"] == 200
        assert fields["description"]["maxLength"] == 2000
