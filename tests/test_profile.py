from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import AuthSettings
from app.core.tokens import create_access_token
from app.models import User, UserRole
from app.schemas.auth import RegisterRequest
from app.schemas.profile import ProfileUpdate
from app.services.profile import update_client_profile
from app.services.registration import (
    EmailAlreadyRegisteredError,
    create_staff_user,
    register_client,
)

PASSWORD = "ExamplePass123!"


@pytest.fixture
def profile_user(db: Session) -> User:
    return register_client(db, RegisterRequest(email="profile@example.com", password=PASSWORD))


@pytest.fixture
def headers(profile_user: User, auth_settings: AuthSettings) -> dict[str, str]:
    token = create_access_token(profile_user.id, profile_user.role, auth_settings)
    return {"Authorization": f"Bearer {token}"}


def test_new_client_profile_has_optional_fields(
    client: TestClient, profile_user: User, headers: dict
) -> None:
    response = client.get("/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "id": str(profile_user.id),
        "name": None,
        "phone": None,
        "email": profile_user.email,
    }
    assert PASSWORD not in response.text
    assert profile_user.password_hash not in response.text


def test_update_full_profile_and_persist(
    client: TestClient, profile_user: User, db: Session, headers: dict
) -> None:
    original_hash = profile_user.password_hash
    response = client.patch(
        "/users/me",
        headers=headers,
        json={"name": "  Иван Петров  ", "phone": " +79991234567 ", "email": " New@Example.COM "},
    )
    assert response.status_code == 200
    expected = {
        "id": str(profile_user.id),
        "name": "Иван Петров",
        "phone": "+79991234567",
        "email": "new@example.com",
    }
    assert response.json() == expected
    assert client.get("/users/me", headers=headers).json() == expected
    db.refresh(profile_user)
    assert profile_user.name == "Иван Петров"
    assert profile_user.phone == "+79991234567"
    assert profile_user.email == "new@example.com"
    assert profile_user.role == UserRole.CLIENT
    assert profile_user.password_hash == original_hash


def test_partial_update_keeps_unspecified_fields(
    client: TestClient, profile_user: User, db: Session, headers: dict
) -> None:
    profile_user.name, profile_user.phone = "Иван", "+79991234567"
    db.commit()
    response = client.patch("/users/me", headers=headers, json={"name": "Пётр"})
    assert response.status_code == 200
    assert response.json()["name"] == "Пётр"
    assert response.json()["phone"] == "+79991234567"
    assert response.json()["email"] == "profile@example.com"


def test_null_clears_name_and_phone(
    client: TestClient, profile_user: User, db: Session, headers: dict
) -> None:
    profile_user.name, profile_user.phone = "Иван", "+79991234567"
    db.commit()
    response = client.patch("/users/me", headers=headers, json={"name": None, "phone": None})
    assert response.status_code == 200
    assert response.json()["name"] is None
    assert response.json()["phone"] is None
    assert response.json()["email"] == "profile@example.com"


def test_own_email_is_not_a_duplicate(client: TestClient, headers: dict) -> None:
    response = client.patch("/users/me", headers=headers, json={"email": " PROFILE@Example.COM "})
    assert response.status_code == 200
    assert response.json()["email"] == "profile@example.com"


def test_changed_email_is_used_for_login_and_old_token_remains_valid(
    client: TestClient, headers: dict, profile_user: User
) -> None:
    user_id = str(profile_user.id)
    assert (
        client.patch("/users/me", headers=headers, json={"email": "new@example.com"}).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/login", json={"email": "profile@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    login = client.post("/auth/login", json={"email": "NEW@EXAMPLE.COM", "password": PASSWORD})
    assert login.status_code == 200
    assert client.get("/users/me", headers=headers).json()["id"] == user_id
    assert client.get("/auth/me", headers=headers).json()["email"] == "new@example.com"
    new_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/users/me", headers=new_headers).json()["id"] == user_id
    # The old email can be registered by a different user, without taking over this token.
    registered = client.post(
        "/auth/register", json={"email": "profile@example.com", "password": PASSWORD}
    )
    assert registered.status_code == 201
    assert registered.json()["id"] != user_id
    assert client.get("/users/me", headers=headers).json()["id"] == user_id


@pytest.mark.parametrize("role", list(UserRole))
def test_duplicate_email_does_not_change_any_field(
    client: TestClient, profile_user: User, db: Session, headers: dict, role: UserRole
) -> None:
    data = RegisterRequest(email="occupied@example.com", password=PASSWORD)
    other = (
        register_client(db, data) if role == UserRole.CLIENT else create_staff_user(db, data, role)
    )
    response = client.patch(
        "/users/me",
        headers=headers,
        json={
            "name": "Should not persist",
            "phone": "+79991234567",
            "email": "OCCUPIED@EXAMPLE.COM",
        },
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Email already registered"}
    db.refresh(profile_user)
    assert profile_user.email == "profile@example.com"
    assert profile_user.name is None and profile_user.phone is None
    db.refresh(other)
    assert other.email == "occupied@example.com"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": None},
        {"email": ""},
        {"email": "not-an-email"},
        {"email": "x" * 243 + "@example.com"},
        {"name": ""},
        {"name": "  "},
        {"name": "x" * 101},
        {"name": 123},
        {"phone": ""},
        {"phone": "79991234567"},
        {"phone": "+7 (999) 123-45-67"},
        {"phone": "+0123456789"},
        {"phone": "+123456"},
        {"phone": "+" + "1" * 16},
        {"phone": 79991234567},
        {"phone": "+１２３４５６７８９"},
        {"role": "manager"},
        {"password": "sensitive-new-password"},
        {"password_hash": "sensitive-hash"},
        {"id": "another-user-id"},
        {"created_at": "2026-11-17"},
        {"unknown": "value"},
        {"name": "Valid name", "phone": "invalid"},
        [],
        None,
    ],
)
def test_invalid_profile_patch_is_atomic_and_safe(
    client: TestClient, profile_user: User, db: Session, headers: dict, payload
) -> None:
    original_hash = profile_user.password_hash
    response = client.patch("/users/me", headers=headers, json=payload)
    assert response.status_code == 422
    assert "sensitive-new-password" not in response.text
    assert "sensitive-hash" not in response.text
    assert all(set(error) == {"type", "loc", "msg"} for error in response.json()["detail"])
    db.refresh(profile_user)
    assert profile_user.email == "profile@example.com"
    assert profile_user.name is None and profile_user.phone is None
    assert profile_user.role == UserRole.CLIENT
    assert profile_user.password_hash == original_hash


@pytest.mark.parametrize("phone", ["+1234567", "+" + "1" * 15])
def test_phone_length_boundaries(client: TestClient, headers: dict, phone: str) -> None:
    response = client.patch("/users/me", headers=headers, json={"phone": phone})
    assert response.status_code == 200
    assert response.json()["phone"] == phone


def test_name_maximum_length(client: TestClient, headers: dict) -> None:
    response = client.patch("/users/me", headers=headers, json={"name": "Я" * 100})
    assert response.status_code == 200
    assert response.json()["name"] == "Я" * 100


@pytest.mark.parametrize("method", ["get", "patch"])
@pytest.mark.parametrize("authorization", [None, "Bearer invalid"])
def test_profile_requires_authentication(client: TestClient, method: str, authorization) -> None:
    kwargs = {"headers": {"Authorization": authorization}} if authorization else {}
    if method == "patch":
        kwargs["json"] = {"name": "Иван"}
    response = getattr(client, method)("/users/me", **kwargs)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("role", [UserRole.MECHANIC, UserRole.MANAGER])
def test_staff_cannot_access_client_profile(
    client: TestClient, db: Session, auth_settings: AuthSettings, role: UserRole
) -> None:
    user = create_staff_user(
        db, RegisterRequest(email="staff@example.com", password=PASSWORD), role
    )
    token = create_access_token(user.id, user.role, auth_settings)
    headers = {"Authorization": f"Bearer {token}"}
    for response in [
        client.get("/users/me", headers=headers),
        client.patch("/users/me", headers=headers, json={"name": "New name"}),
    ]:
        assert response.status_code == 403
        assert response.json() == {"detail": "Insufficient permissions"}
    assert client.get("/auth/me", headers=headers).status_code == 200
    db.refresh(user)
    assert user.name is None


def test_role_change_affects_profile_access(
    client: TestClient, profile_user: User, db: Session, headers: dict
) -> None:
    profile_user.role = UserRole.MECHANIC
    db.commit()
    assert client.get("/users/me", headers=headers).status_code == 403


def test_user_cannot_target_another_profile(
    client: TestClient, profile_user: User, db: Session, auth_settings: AuthSettings, headers: dict
) -> None:
    other = register_client(db, RegisterRequest(email="other@example.com", password=PASSWORD))
    other_token = create_access_token(other.id, other.role, auth_settings)
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert client.get("/users/me", headers=other_headers).json()["id"] == str(other.id)
    response = client.patch(
        "/users/me", headers=headers, json={"id": str(other.id), "name": "Attack"}
    )
    assert response.status_code == 422
    assert client.get(f"/users/{other.id}", headers=headers).status_code == 404
    assert client.patch("/users/me", headers=headers, json={"name": "Own name"}).status_code == 200
    db.refresh(other)
    assert other.name is None
    assert client.get("/users/me", headers=headers).json()["id"] == str(profile_user.id)


def test_email_race_rolls_back_all_profile_changes(
    profile_user: User, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = register_client(db, RegisterRequest(email="occupied@example.com", password=PASSWORD))
    # A stale precheck is followed by a real DB uniqueness violation on UPDATE.
    monkeypatch.setattr(db, "scalar", Mock(side_effect=[None, other.id]))
    with pytest.raises(EmailAlreadyRegisteredError):
        update_client_profile(
            db, profile_user, ProfileUpdate(name="Must roll back", email="occupied@example.com")
        )
    monkeypatch.undo()
    db.refresh(profile_user)
    assert profile_user.name is None
    assert profile_user.email == "profile@example.com"
    updated = update_client_profile(db, profile_user, ProfileUpdate(name="Works after rollback"))
    assert updated.name == "Works after rollback"


def test_unrelated_integrity_error_is_not_a_duplicate(
    profile_user: User, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "commit", Mock(side_effect=IntegrityError("UPDATE", {}, Exception())))
    with pytest.raises(IntegrityError):
        update_client_profile(db, profile_user, ProfileUpdate(name="New name"))


def test_openapi_documents_profile(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    path = schema["paths"]["/users/me"]
    for method in ("get", "patch"):
        assert path[method]["security"] == [{"HTTPBearer": []}]
        assert {"200", "401", "403"} <= path[method]["responses"].keys()
    assert {"409", "422"} <= path["patch"]["responses"].keys()
    request = schema["components"]["schemas"]["ProfileUpdate"]
    assert set(request["properties"]) == {"name", "phone", "email"}
    assert request["additionalProperties"] is False
    assert request["minProperties"] == 1
    assert request["properties"]["email"]["type"] == "string"
    assert "anyOf" not in request["properties"]["email"]
    response = schema["components"]["schemas"]["ClientProfile"]
    assert set(response["properties"]) == {"id", "name", "phone", "email"}
