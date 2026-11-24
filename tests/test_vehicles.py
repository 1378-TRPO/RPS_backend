from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import AuthSettings, get_auth_settings
from app.core.tokens import create_access_token
from app.db.session import get_db
from app.main import create_app
from app.models import UserRole, Vehicle
from app.schemas.auth import RegisterRequest
from app.services.registration import create_staff_user, register_client

PATH = "/users/me/vehicles"
VEHICLE = {"make": "Toyota", "model": "Corolla", "year": 2020, "plate": "XY 123-Z"}
PASSWORD = "test-garage-password"


@pytest.fixture
def client_headers(db: Session, auth_settings: AuthSettings) -> dict[str, str]:
    user = register_client(db, RegisterRequest(email="garage@example.com", password=PASSWORD))
    token = create_access_token(user.id, user.role, auth_settings)
    return {"Authorization": f"Bearer {token}"}


def test_vehicle_is_owned_by_client_and_persists_across_database_connections(
    tmp_path: Path, auth_settings: AuthSettings
) -> None:
    url = URL.create("sqlite+pysqlite", database=str(tmp_path / "garage.db"))
    engine = create_engine(url)
    application = create_app()

    def open_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_db] = open_session
    application.dependency_overrides[get_auth_settings] = lambda: auth_settings
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        with TestClient(application) as api:
            credentials = {"email": "owner@example.com", "password": PASSWORD}
            registered = api.post("/auth/register", json=credentials)
            assert registered.status_code == 201
            owner_id = UUID(registered.json()["id"])
            login = api.post("/auth/login", json=credentials)
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            created = api.post(
                PATH,
                headers=headers,
                json={**VEHICLE, "make": "  Toyota ", "model": " Corolla ", "plate": " XY 123-Z "},
            )
            assert created.status_code == 201
            result = created.json()
            assert {field: result[field] for field in VEHICLE} == VEHICLE
            assert set(result) == {*VEHICLE, "id", "created_at"}
            assert result["created_at"]
            vehicle_id = UUID(result["id"])

            duplicate = api.post(PATH, headers=headers, json=VEHICLE)
            assert duplicate.status_code == 201
            assert duplicate.json()["id"] != result["id"]
    finally:
        engine.dispose()

    reopened_engine = create_engine(url)
    try:
        with Session(reopened_engine) as db:
            persisted = db.get(Vehicle, vehicle_id)
            assert persisted is not None
            assert persisted.client_id == owner_id
            assert {field: getattr(persisted, field) for field in VEHICLE} == VEHICLE
            assert persisted.created_at == datetime.fromisoformat(result["created_at"])
            assert db.scalar(select(func.count()).select_from(Vehicle)) == 2
    finally:
        reopened_engine.dispose()


def test_post_vehicle_saves_authenticated_client_id(
    client: TestClient, db: Session, client_headers: dict[str, str]
) -> None:
    response = client.post(PATH, json=VEHICLE, headers=client_headers)
    assert response.status_code == 201
    owner = client.get("/auth/me", headers=client_headers)
    vehicle = db.get(Vehicle, UUID(response.json()["id"]))
    assert vehicle is not None
    assert str(vehicle.client_id) == owner.json()["id"]


@pytest.mark.parametrize("authorization", [None, "Bearer invalid"])
def test_vehicle_requires_valid_jwt(
    client: TestClient, db: Session, authorization: str | None
) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    response = client.post(PATH, json=VEHICLE, headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert db.scalar(select(func.count()).select_from(Vehicle)) == 0


@pytest.mark.parametrize("role", [UserRole.MECHANIC, UserRole.MANAGER])
def test_staff_cannot_add_vehicle(
    client: TestClient, db: Session, auth_settings: AuthSettings, role: UserRole
) -> None:
    staff = create_staff_user(
        db, RegisterRequest(email="staff@example.com", password=PASSWORD), role
    )
    token = create_access_token(staff.id, staff.role, auth_settings)
    response = client.post(PATH, json=VEHICLE, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert db.scalar(select(func.count()).select_from(Vehicle)) == 0


@pytest.mark.parametrize(
    "payload",
    [
        *[{k: v for k, v in VEHICLE.items() if k != field} for field in VEHICLE],
        {**VEHICLE, "make": " \t "},
        {**VEHICLE, "model": ""},
        {**VEHICLE, "plate": "\n"},
        {**VEHICLE, "make": 12},
        {**VEHICLE, "model": None},
        {**VEHICLE, "plate": "XY\x0012"},
        {**VEHICLE, "year": "2020"},
        {**VEHICLE, "year": 2020.0},
        {**VEHICLE, "year": True},
        {**VEHICLE, "year": 2**31},
        {**VEHICLE, "client_id": "8193fe67-4f8d-418d-84bd-e102144301a8"},
        {**VEHICLE, "owner_id": None},
        {**VEHICLE, "id": None},
    ],
)
def test_invalid_vehicle_is_rejected_without_insert(
    client: TestClient, db: Session, client_headers: dict[str, str], payload: dict
) -> None:
    response = client.post(PATH, json=payload, headers=client_headers)
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(Vehicle)) == 0


def test_openapi_describes_garage_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][PATH]["post"]
    assert operation["security"] == [{"HTTPBearer": []}]
    assert {"201", "401", "403", "422"} <= operation["responses"].keys()
    request = schema["components"]["schemas"]["VehicleCreate"]
    assert set(request["required"]) == set(VEHICLE)
    assert request["additionalProperties"] is False
    response = schema["components"]["schemas"]["VehicleResponse"]
    assert set(response["properties"]) == {*VEHICLE, "id", "created_at"}
