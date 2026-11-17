from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.core.security import verify_password
from app.models import User, UserRole
from app.schemas.auth import RegisterRequest
from app.services.registration import create_staff_user, register_client

PASSWORD = "ExamplePass123!"


@pytest.fixture
def cli_db(db: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.setattr(cli, "get_engine", lambda: None)
    monkeypatch.setattr(cli, "Session", lambda engine: nullcontext(db))
    return db


@pytest.mark.parametrize("role", ["mechanic", "manager"])
def test_cli_creates_staff_without_printing_password(
    cli_db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, role: str
) -> None:
    monkeypatch.setattr(cli, "getpass", Mock(side_effect=[PASSWORD, PASSWORD]))
    result = cli.main(["create-staff", "--email", " Staff@Example.COM ", "--role", role])
    assert result == 0
    user = cli_db.scalar(select(User).where(User.email == "staff@example.com"))
    assert user.role == UserRole(role)
    assert verify_password(PASSWORD, user.password_hash)
    output = capsys.readouterr()
    assert role in output.out
    assert PASSWORD not in output.out + output.err
    assert user.password_hash not in output.out + output.err


def test_cli_rejects_password_mismatch(cli_db, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "getpass", Mock(side_effect=[PASSWORD, "different-password"]))
    assert cli.main(["create-staff", "--email", "staff@example.com", "--role", "manager"]) == 2
    assert cli_db.scalar(select(User)) is None
    assert PASSWORD not in capsys.readouterr().err


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_cli_rejects_invalid_password(cli_db, monkeypatch, password) -> None:
    monkeypatch.setattr(cli, "getpass", Mock(side_effect=[password, password]))
    assert cli.main(["create-staff", "--email", "staff@example.com", "--role", "manager"]) == 2
    assert cli_db.scalar(select(User)) is None


def test_cli_rejects_duplicate_without_promoting_client(cli_db, monkeypatch) -> None:
    user = register_client(cli_db, RegisterRequest(email="staff@example.com", password=PASSWORD))
    monkeypatch.setattr(cli, "getpass", Mock(side_effect=[PASSWORD, PASSWORD]))
    assert cli.main(["create-staff", "--email", user.email, "--role", "manager"]) == 1
    cli_db.refresh(user)
    assert user.role == UserRole.CLIENT


def test_staff_service_rejects_client_role(cli_db) -> None:
    with pytest.raises(ValueError):
        create_staff_user(
            cli_db, RegisterRequest(email="staff@example.com", password=PASSWORD), UserRole.CLIENT
        )


def test_cli_requires_interactive_input(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "getpass", Mock(side_effect=cli.GetPassWarning()))
    assert cli.main(["create-staff", "--email", "staff@example.com", "--role", "manager"]) == 2
    assert "интерактивный" in capsys.readouterr().err
