from datetime import datetime
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.schemas.auth import RegisterRequest
from app.services.registration import EmailAlreadyRegisteredError, register_client

PASSWORD = "ExamplePass123!"
PAYLOAD = {"email": "client@example.com", "password": PASSWORD}


def test_registration_creates_client_and_hashes_password(client: TestClient, db: Session) -> None:
    response = client.post("/auth/register", json=PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert set(data) == {"id", "email", "role", "created_at"}
    assert UUID(data["id"])
    assert datetime.fromisoformat(data["created_at"])
    assert data["email"] == PAYLOAD["email"]
    assert data["role"] == "client"
    assert PASSWORD not in response.text

    user = db.scalar(select(User).where(User.email == PAYLOAD["email"]))
    assert user is not None
    assert str(user.id) == data["id"]
    assert user.role == UserRole.CLIENT
    assert user.password_hash.startswith("$argon2id$")
    assert PasswordHash.recommended().verify(PASSWORD, user.password_hash)
    assert user.password_hash not in response.text


@pytest.mark.parametrize(
    "email", ["client@example.com", "CLIENT@EXAMPLE.COM", "Client@Example.com"]
)
def test_duplicate_email_is_case_insensitive(client: TestClient, db: Session, email: str) -> None:
    assert client.post("/auth/register", json=PAYLOAD).status_code == 201
    response = client.post("/auth/register", json={**PAYLOAD, "email": email})
    assert response.status_code == 409
    assert response.json() == {"detail": "Email already registered"}
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_email_is_trimmed_and_lowercased(client: TestClient) -> None:
    response = client.post("/auth/register", json={**PAYLOAD, "email": " Client@Example.COM "})
    assert response.status_code == 201
    assert response.json()["email"] == "client@example.com"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "client@example.com"},
        {"password": PASSWORD},
        {**PAYLOAD, "email": "not-an-email"},
        {**PAYLOAD, "email": ""},
        {**PAYLOAD, "email": None},
        {**PAYLOAD, "email": "x" * 243 + "@example.com"},
        {**PAYLOAD, "password": ""},
        {**PAYLOAD, "password": "1234567"},
        {**PAYLOAD, "password": "x" * 129},
        {**PAYLOAD, "password": None},
        {**PAYLOAD, "password": 12345678},
        {**PAYLOAD, "role": "manager"},
        {**PAYLOAD, "role": "mechanic"},
        {**PAYLOAD, "role": "client"},
        {**PAYLOAD, "password_hash": "injected_hash"},
        {**PAYLOAD, "id": "injected_id"},
        [],
        None,
    ],
)
def test_invalid_request_does_not_create_user(client: TestClient, db: Session, payload) -> None:
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(User)) == 0
    for error in response.json()["detail"]:
        assert set(error) == {"type", "loc", "msg"}
    assert PASSWORD not in response.text
    assert "injected_hash" not in response.text


@pytest.mark.parametrize("password", ["12345678", "x" * 128, "  пароль  "])
def test_valid_password_boundaries_preserve_password(
    client: TestClient, db: Session, password: str
) -> None:
    response = client.post("/auth/register", json={**PAYLOAD, "password": password})
    assert response.status_code == 201
    user = db.scalar(select(User).where(User.email == PAYLOAD["email"]))
    assert PasswordHash.recommended().verify(password, user.password_hash)


def test_passwords_have_independent_salts(client: TestClient, db: Session) -> None:
    for email in ["first@example.com", "second@example.com"]:
        assert client.post("/auth/register", json={**PAYLOAD, "email": email}).status_code == 201
    hashes = list(db.scalars(select(User.password_hash)))
    assert len(hashes) == 2
    assert hashes[0] != hashes[1]


def test_malformed_json_does_not_echo_password(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        content='{"password":"very_sensitive_password",',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "very_sensitive_password" not in response.text


def test_database_enforces_unique_email(db: Session) -> None:
    db.add(User(email=PAYLOAD["email"], password_hash="test_hash"))
    db.commit()
    db.add(User(email=PAYLOAD["email"], password_hash="another_hash"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_insert_race_becomes_email_conflict(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    existing = register_client(db, RegisterRequest(**PAYLOAD))
    # Simulate a stale initial SELECT; the INSERT hits the real DB unique constraint.
    monkeypatch.setattr(db, "scalar", Mock(side_effect=[None, existing.id]))
    with pytest.raises(EmailAlreadyRegisteredError):
        register_client(db, RegisterRequest(**PAYLOAD))
    monkeypatch.undo()
    assert db.scalar(select(func.count()).select_from(User)) == 1
    # The rollback leaves the session usable for another successful request.
    another = register_client(db, RegisterRequest(email="another@example.com", password=PASSWORD))
    assert another.role == UserRole.CLIENT


def test_unrelated_integrity_error_is_not_reported_as_duplicate(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "commit", Mock(side_effect=IntegrityError("INSERT", {}, Exception())))
    with pytest.raises(IntegrityError):
        register_client(db, RegisterRequest(**PAYLOAD))


def test_openapi_documents_registration(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/auth/register"]["post"]
    assert {"201", "409", "422"} <= operation["responses"].keys()
    assert not operation.get("security")
    request = schema["components"]["schemas"]["RegisterRequest"]
    assert set(request["properties"]) == {"email", "password"}
    assert request["additionalProperties"] is False
    assert request["properties"]["password"]["writeOnly"] is True
    response = schema["components"]["schemas"]["RegisteredUser"]
    assert "password" not in response["properties"]
    assert "password_hash" not in response["properties"]
