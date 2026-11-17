import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import AuthSettings, get_auth_settings
from app.db.session import get_db
from app.main import create_app


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    options = {}
    if url.startswith("sqlite"):
        options = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    engine = create_engine(url, **options)

    if engine.dialect.name == "sqlite":
        # Explicit BEGIN keeps nested SAVEPOINTs inside the test's outer transaction.
        @event.listens_for(engine, "connect")
        def sqlite_connect(dbapi_connection, connection_record):
            dbapi_connection.isolation_level = None

        @event.listens_for(engine, "begin")
        def sqlite_begin(connection: Connection) -> None:
            connection.exec_driver_sql("BEGIN")

    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            try:
                yield session
            finally:
                session.close()
                transaction.rollback()


@pytest.fixture
def auth_settings() -> AuthSettings:
    return AuthSettings(
        _env_file=None, jwt_secret="tests-only-key-that-is-never-used-outside-test-suite"
    )


@pytest.fixture
def client(db: Session, auth_settings: AuthSettings) -> Iterator[TestClient]:

    def override_db() -> Iterator[Session]:
        yield db

    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_auth_settings] = lambda: auth_settings
    with TestClient(application) as test_client:
        yield test_client
