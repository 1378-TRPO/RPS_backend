from collections.abc import Iterator
from datetime import UTC, date, datetime
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


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("authorization", [None, "Bearer invalid"])
def test_vehicle_requires_valid_jwt(
    client: TestClient, db: Session, method: str, authorization: str | None
) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    response = client.request(
        method, PATH, json=VEHICLE if method == "POST" else None, headers=headers
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert db.scalar(select(func.count()).select_from(Vehicle)) == 0


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("role", [UserRole.MECHANIC, UserRole.MANAGER])
def test_staff_cannot_access_garage(
    client: TestClient, db: Session, auth_settings: AuthSettings, method: str, role: UserRole
) -> None:
    staff = create_staff_user(
        db, RegisterRequest(email="staff@example.com", password=PASSWORD), role
    )
    token = create_access_token(staff.id, staff.role, auth_settings)
    response = client.request(
        method,
        PATH,
        json=VEHICLE if method == "POST" else None,
        headers={"Authorization": f"Bearer {token}"},
    )
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
        {**VEHICLE, "year": 1899},
        {**VEHICLE, "year": date.today().year + 2},
        {**VEHICLE, "year": 2**31},
        {**VEHICLE, "make": "M" * 101},
        {**VEHICLE, "model": "M" * 101},
        {**VEHICLE, "plate": "P" * 33},
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


@pytest.mark.parametrize("year", [1900, date.today().year + 1])
def test_vehicle_accepts_year_and_trimmed_length_limits(
    client: TestClient, client_headers: dict[str, str], year: int
) -> None:
    make, model, plate = "M" * 100, "X" * 100, "P" * 32
    response = client.post(
        PATH,
        headers=client_headers,
        json={"make": f" {make} ", "model": f" {model} ", "year": year, "plate": f" {plate} "},
    )
    assert response.status_code == 201
    assert {key: response.json()[key] for key in VEHICLE} == {
        "make": make,
        "model": model,
        "year": year,
        "plate": plate,
    }


def test_openapi_describes_garage_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][PATH]["post"]
    assert operation["security"] == [{"HTTPBearer": []}]
    assert {"201", "401", "403", "422"} <= operation["responses"].keys()
    request = schema["components"]["schemas"]["VehicleCreate"]
    assert set(request["required"]) == set(VEHICLE)
    assert request["additionalProperties"] is False
    assert request["properties"]["make"]["maxLength"] == 100
    assert request["properties"]["model"]["maxLength"] == 100
    assert request["properties"]["plate"]["maxLength"] == 32
    assert request["properties"]["year"]["minimum"] == 1900
    response = schema["components"]["schemas"]["VehicleResponse"]
    assert set(response["properties"]) == {*VEHICLE, "id", "created_at"}

    listing = schema["paths"][PATH]["get"]
    assert listing["security"] == [{"HTTPBearer": []}]
    assert not listing.get("parameters")
    assert "requestBody" not in listing
    assert {"200", "401", "403"} <= listing["responses"].keys()
    list_schema = listing["responses"]["200"]["content"]["application/json"]["schema"]
    assert list_schema["type"] == "array"
    assert list_schema["items"]["$ref"] == "#/components/schemas/VehicleResponse"


def test_empty_garage_returns_empty_array(
    client: TestClient, client_headers: dict[str, str]
) -> None:
    response = client.get(PATH, headers=client_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_garage_list_orders_by_date_then_id_descending(
    client: TestClient, db: Session, client_headers: dict[str, str]
) -> None:
    account = client.get("/auth/me", headers=client_headers)
    assert account.status_code == 200
    owner_id = UUID(account.json()["id"])
    newer = datetime(2026, 11, 24, 10, tzinfo=UTC)
    older = datetime(2026, 11, 23, 10, tzinfo=UTC)
    db.add_all(
        [
            Vehicle(id=UUID(int=1), client_id=owner_id, created_at=newer, **VEHICLE),
            Vehicle(id=UUID(int=3), client_id=owner_id, created_at=older, **VEHICLE),
            Vehicle(id=UUID(int=2), client_id=owner_id, created_at=newer, **VEHICLE),
        ]
    )
    db.commit()

    response = client.get(PATH, headers=client_headers)
    assert response.status_code == 200
    data = response.json()
    assert [UUID(item["id"]).int for item in data] == [2, 1, 3]
    assert all(set(item) == {*VEHICLE, "id", "created_at"} for item in data)
    assert client.get(PATH, headers=client_headers).json() == data


def test_garage_list_isolates_two_clients(
    client: TestClient, db: Session, auth_settings: AuthSettings, client_headers: dict[str, str]
) -> None:
    other_client = register_client(
        db, RegisterRequest(email="other-garage@example.com", password=PASSWORD)
    )
    other_token = create_access_token(other_client.id, other_client.role, auth_settings)
    other_headers = {"Authorization": f"Bearer {other_token}"}
    own_vehicle = client.post(PATH, headers=client_headers, json=VEHICLE)
    assert own_vehicle.status_code == 201

    empty = client.get(PATH, headers=other_headers)
    assert empty.status_code == 200
    assert empty.json() == []

    other_vehicle = client.post(PATH, headers=other_headers, json={**VEHICLE, "plate": "OTHER 2"})
    assert other_vehicle.status_code == 201

    own_list = client.get(
        PATH,
        headers=client_headers,
        params={"client_id": str(other_client.id), "user_id": str(other_client.id)},
    )
    other_list = client.get(PATH, headers=other_headers)
    assert own_list.status_code == other_list.status_code == 200
    assert own_list.json() == [own_vehicle.json()]
    assert other_list.json() == [other_vehicle.json()]
