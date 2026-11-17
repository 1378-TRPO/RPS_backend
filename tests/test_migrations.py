from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_upgrade_downgrade_and_upgrade(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            assert "users" in inspect(connection).get_table_names()
            unique = inspect(connection).get_unique_constraints("users")
            assert any(item["column_names"] == ["email"] for item in unique)
            command.check(config)
            command.downgrade(config, "base")
            assert "users" not in inspect(connection).get_table_names()
            command.upgrade(config, "head")
            assert "users" in inspect(connection).get_table_names()
    finally:
        engine.dispose()
