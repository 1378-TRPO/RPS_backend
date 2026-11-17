from collections.abc import Iterator
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import create_app


def test_health_does_not_need_database() -> None:
    application = create_app()

    def unavailable_db() -> None:
        raise AssertionError("Liveness must not connect to a database")

    application.dependency_overrides[get_db] = unavailable_db
    with TestClient(application) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_checks_database(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_does_not_expose_connection_details() -> None:
    session = Mock(spec=Session)
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("secret_password"))

    def failing_db() -> Iterator[Session]:
        yield session

    application = create_app()
    application.dependency_overrides[get_db] = failing_db
    with TestClient(application) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "secret_password" not in response.text


def test_openapi_documents_health_endpoints(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "get" in paths["/health"]
    assert "503" in paths["/health/ready"]["get"]["responses"]
