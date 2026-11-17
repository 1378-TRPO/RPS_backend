import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    url = os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    options = {}
    if url.startswith("sqlite"):
        options = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    engine = create_engine(url, **options)

    def override_db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_db] = override_db
    try:
        with TestClient(application) as test_client:
            yield test_client
    finally:
        engine.dispose()
