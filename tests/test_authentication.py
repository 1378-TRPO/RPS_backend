from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.config import AuthSettings
from app.core.tokens import create_access_token
from app.models import User, UserRole
from app.schemas.auth import RegisterRequest
from app.services.registration import create_staff_user, register_client

PASSWORD = "ExamplePass123!"


@pytest.fixture
def user(db: Session) -> User:
    return register_client(db, RegisterRequest(email="auth.client@example.com", password=PASSWORD))


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sign_claims(claims: dict, settings: AuthSettings) -> str:
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def token_claims(user: User, settings: AuthSettings) -> dict:
    now = int(datetime.now(UTC).timestamp())
    return {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": now,
        "exp": now + 1800,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }


@pytest.mark.parametrize("role", list(UserRole))
def test_login_and_current_account_for_each_role(
    client: TestClient, db: Session, auth_settings: AuthSettings, role: UserRole
) -> None:
    data = RegisterRequest(email="login@example.com", password=PASSWORD)
    account = (
        register_client(db, data) if role == UserRole.CLIENT else create_staff_user(db, data, role)
    )
    response = client.post(
        "/auth/login", json={"email": " LOGIN@Example.COM ", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    data = response.json()
    assert set(data) == {"access_token", "token_type", "expires_in"}
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 1800
    claims = jwt.decode(
        data["access_token"],
        auth_settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=auth_settings.jwt_issuer,
        audience=auth_settings.jwt_audience,
    )
    assert claims["sub"] == str(account.id)
    assert claims["role"] == role.value
    assert claims["exp"] - claims["iat"] == data["expires_in"]
    assert "email" not in claims
    assert "password" not in claims
    assert "password_hash" not in claims
    current = client.get("/auth/me", headers=auth_header(data["access_token"]))
    assert current.status_code == 200
    assert current.json()["id"] == str(account.id)
    assert current.json()["role"] == role.value
    assert set(current.json()) == {"id", "email", "role", "created_at"}
    assert PASSWORD not in current.text
    assert account.password_hash not in current.text


def test_wrong_password_and_unknown_email_have_same_error(client: TestClient, user: User) -> None:
    wrong_password = client.post("/auth/login", json={"email": user.email, "password": "wrong"})
    unknown = client.post(
        "/auth/login", json={"email": "unknown@example.com", "password": PASSWORD}
    )
    for response in (wrong_password, unknown):
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json() == {"detail": "Invalid email or password"}
        assert "access_token" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "client@example.com"},
        {"email": "bad", "password": PASSWORD},
        {"email": "client@example.com", "password": ""},
        {"email": "client@example.com", "password": "x" * 129},
        {"email": "client@example.com", "password": 12345678},
        {"email": "client@example.com", "password": PASSWORD, "role": "manager"},
    ],
)
def test_invalid_login_does_not_echo_secrets(client: TestClient, payload: dict) -> None:
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert "access_token" not in response.text
    assert all("input" not in error for error in response.json()["detail"])


@pytest.mark.parametrize(
    "authorization", [None, "Basic abc", "Bearer", "Bearer junk", "Bearer a.b.c"]
)
def test_missing_or_malformed_token_is_401(client: TestClient, authorization: str | None) -> None:
    headers = {"Authorization": authorization} if authorization is not None else {}
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("exp", 1),
        ("iat", 9999999999),
        ("sub", "not-a-uuid"),
        ("sub", 123),
        ("role", "admin"),
        ("role", []),
        ("iss", "another-service"),
        ("aud", "another-api"),
        ("exp", None),
        ("exp", "not-a-date"),
        ("exp", True),
        ("iat", None),
    ],
)
def test_invalid_signed_claims_are_401(
    client: TestClient, user: User, auth_settings: AuthSettings, claim: str, value
) -> None:
    claims = token_claims(user, auth_settings)
    claims[claim] = value
    response = client.get("/auth/me", headers=auth_header(sign_claims(claims, auth_settings)))
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired token"}


@pytest.mark.parametrize("claim", ["sub", "role", "exp", "iat", "iss", "aud"])
def test_missing_required_claim_is_401(
    client: TestClient, user: User, auth_settings: AuthSettings, claim: str
) -> None:
    claims = token_claims(user, auth_settings)
    del claims[claim]
    response = client.get("/auth/me", headers=auth_header(sign_claims(claims, auth_settings)))
    assert response.status_code == 401


@pytest.mark.parametrize("algorithm", ["HS384", "none"])
def test_other_algorithms_are_rejected(
    client: TestClient, user: User, auth_settings: AuthSettings, algorithm: str
) -> None:
    key = "" if algorithm == "none" else auth_settings.jwt_secret.get_secret_value()
    token = jwt.encode(token_claims(user, auth_settings), key, algorithm=algorithm)
    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401


def test_wrong_signature_is_rejected(
    client: TestClient, user: User, auth_settings: AuthSettings
) -> None:
    token = jwt.encode(
        token_claims(user, auth_settings),
        "a-different-signing-key-with-at-least-32-chars",
        algorithm="HS256",
    )
    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401


def test_deleted_user_token_is_rejected(
    client: TestClient, user: User, db: Session, auth_settings: AuthSettings
) -> None:
    token = create_access_token(user.id, user.role, auth_settings)
    db.delete(user)
    db.commit()
    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401


def test_unknown_subject_is_rejected(client: TestClient, auth_settings: AuthSettings) -> None:
    token = create_access_token(uuid4(), UserRole.CLIENT, auth_settings)
    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.parametrize("allowed_role", list(UserRole))
def test_role_access_matrix(
    client: TestClient,
    user: User,
    db: Session,
    auth_settings: AuthSettings,
    role: UserRole,
    allowed_role: UserRole,
) -> None:
    user.role = role
    db.commit()

    def protected(account: Annotated[User, Depends(require_roles(allowed_role))]) -> dict:
        return {"id": str(account.id)}

    client.app.get("/test-role-only")(protected)
    token = create_access_token(user.id, user.role, auth_settings)
    response = client.get("/test-role-only", headers=auth_header(token))
    assert response.status_code == (200 if role == allowed_role else 403)
    if role != allowed_role:
        assert response.json() == {"detail": "Insufficient permissions"}


def test_downgraded_role_cannot_use_old_token(
    client: TestClient, user: User, db: Session, auth_settings: AuthSettings
) -> None:
    user.role = UserRole.MANAGER
    db.commit()
    token = create_access_token(user.id, user.role, auth_settings)

    def manager_only(account: Annotated[User, Depends(require_roles(UserRole.MANAGER))]) -> dict:
        return {"id": str(account.id)}

    client.app.get("/test-manager-only")(manager_only)
    user.role = UserRole.CLIENT
    db.commit()
    assert client.get("/test-manager-only", headers=auth_header(token)).status_code == 403
    assert client.get("/auth/me", headers=auth_header(token)).json()["role"] == "client"


def test_multiple_allowed_roles(
    client: TestClient, user: User, auth_settings: AuthSettings
) -> None:
    def shared(account: Annotated[User, Depends(require_roles(UserRole.CLIENT, UserRole.MANAGER))]):
        return {"id": str(account.id)}

    client.app.get("/test-shared")(shared)
    token = create_access_token(user.id, user.role, auth_settings)
    assert client.get("/test-shared", headers=auth_header(token)).status_code == 200
    assert client.get("/test-shared").status_code == 401


def test_corrupted_password_hash_fails_closed(client: TestClient, user: User, db: Session) -> None:
    user.password_hash = "invalid-hash"
    db.commit()
    response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 401


def test_openapi_has_bearer_authorization(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    login = schema["paths"]["/auth/login"]["post"]
    current = schema["paths"]["/auth/me"]["get"]
    assert not login.get("security")
    assert {"200", "401", "422"} <= login["responses"].keys()
    assert current["security"] == [{"HTTPBearer": []}]
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
