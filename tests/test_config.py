from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import AuthSettings, Settings


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_environment_overrides_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=sqlite:///from_file.db\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from_environment.db")
    settings = Settings(_env_file=env_file)
    assert settings.database_url == "sqlite:///from_environment.db"


def test_settings_repr_does_not_expose_credentials() -> None:
    settings = Settings(database_url="postgresql+psycopg://user:secret_password@localhost/db")
    assert "secret_password" not in repr(settings)


def test_jwt_secret_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        AuthSettings(_env_file=None)


@pytest.mark.parametrize("secret", ["", "short", " " * 32])
def test_invalid_jwt_secret_is_rejected(secret: str) -> None:
    with pytest.raises(ValidationError):
        AuthSettings(_env_file=None, jwt_secret=secret)


@pytest.mark.parametrize("minutes", [0, -1, 1441])
def test_invalid_token_lifetime_is_rejected(minutes: int) -> None:
    with pytest.raises(ValidationError):
        AuthSettings(
            _env_file=None,
            jwt_secret="test-secret-with-at-least-32-characters",
            access_token_expire_minutes=minutes,
        )


def test_jwt_secret_is_hidden_in_settings_repr() -> None:
    secret = "test-secret-with-at-least-32-characters"
    assert secret not in repr(AuthSettings(_env_file=None, jwt_secret=secret))
