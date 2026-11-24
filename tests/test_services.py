from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import AuthSettings
from app.core.tokens import create_access_token
from app.models import Service, UserRole
from app.schemas.auth import RegisterRequest
from app.services.registration import create_staff_user, register_client

PATH = "/services"
SERVICE_FIELDS = {"id", "name", "description", "price", "duration_minutes"}


@pytest.fixture
def catalog_headers(db: Session, auth_settings: AuthSettings) -> dict[str, str]:
    account = register_client(
        db, RegisterRequest(email="catalog@example.com", password="catalog-test-password")
    )
    token = create_access_token(account.id, account.role, auth_settings)
    return {"Authorization": f"Bearer {token}"}


def test_catalog_shows_active_services_sorted_by_name_and_id(
    client: TestClient, db: Session, catalog_headers: dict[str, str]
) -> None:
    db.add_all(
        [
            Service(
                id=UUID(int=1),
                name="Tires",
                description="Tire change",
                price=Decimal("1250.50"),
                duration_minutes=45,
            ),
            Service(
                id=UUID(int=4),
                name="Diagnostics",
                description="Extended diagnostics",
                price=Decimal("9999999999.99"),
                duration_minutes=120,
            ),
            Service(
                id=UUID(int=3),
                name="Diagnostics",
                price=Decimal("0.01"),
                duration_minutes=15,
            ),
            Service(
                id=UUID(int=2),
                name="Alignment",
                description="Archived service",
                price=Decimal("1000.00"),
                duration_minutes=20,
                is_active=False,
            ),
        ]
    )
    db.commit()

    response = client.get(PATH, headers=catalog_headers)
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(UUID(int=3)),
            "name": "Diagnostics",
            "description": None,
            "price": "0.01",
            "duration_minutes": 15,
        },
        {
            "id": str(UUID(int=4)),
            "name": "Diagnostics",
            "description": "Extended diagnostics",
            "price": "9999999999.99",
            "duration_minutes": 120,
        },
        {
            "id": str(UUID(int=1)),
            "name": "Tires",
            "description": "Tire change",
            "price": "1250.50",
            "duration_minutes": 45,
        },
    ]


def test_catalog_stays_empty_when_no_services_are_active(
    client: TestClient, db: Session, catalog_headers: dict[str, str]
) -> None:
    response = client.get(PATH, headers=catalog_headers)
    assert response.status_code == 200
    assert response.json() == []

    db.add(Service(name="Archived", price=Decimal("75.00"), duration_minutes=30, is_active=False))
    db.commit()
    response = client.get(PATH, headers=catalog_headers)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("authorization", [None, "Bearer invalid"])
def test_catalog_requires_valid_jwt(client: TestClient, authorization: str | None) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    response = client.get(PATH, headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("role", [UserRole.MECHANIC, UserRole.MANAGER])
def test_catalog_requires_client_role(
    client: TestClient, db: Session, auth_settings: AuthSettings, role: UserRole
) -> None:
    account = create_staff_user(
        db, RegisterRequest(email="staff@example.com", password="catalog-test-password"), role
    )
    token = create_access_token(account.id, account.role, auth_settings)
    response = client.get(PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_openapi_documents_catalog(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][PATH]["get"]
    assert operation["security"] == [{"HTTPBearer": []}]
    assert not operation.get("parameters")
    assert {"200", "401", "403"} <= operation["responses"].keys()
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["type"] == "array"
    assert response_schema["items"]["$ref"] == "#/components/schemas/ServiceResponse"
    fields = schema["components"]["schemas"]["ServiceResponse"]["properties"]
    assert set(fields) == SERVICE_FIELDS
    assert fields["price"]["type"] == "string"
    assert fields["duration_minutes"]["type"] == "integer"
