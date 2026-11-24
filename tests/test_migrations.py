from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


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


def test_profile_migration_preserves_existing_account(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'existing_account.db'}")
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0001")
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role) "
                    "VALUES (:id, :email, :hash, 'client')"
                ),
                {"id": "a" * 32, "email": "existing@example.com", "hash": "existing-hash"},
            )
            command.upgrade(config, "head")
            record = connection.execute(text("SELECT * FROM users")).mappings().one()
            assert record["email"] == "existing@example.com"
            assert record["password_hash"] == "existing-hash"
            assert record["role"] == "client"
            assert record["name"] is None and record["phone"] is None
            connection.execute(text("UPDATE users SET name = 'Existing', phone = '+79991234567'"))
            command.downgrade(config, "0001")
            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            assert "name" not in columns and "phone" not in columns
            assert connection.scalar(text("SELECT email FROM users")) == "existing@example.com"
            command.upgrade(config, "head")
            record = connection.execute(text("SELECT * FROM users")).mappings().one()
            assert record["email"] == "existing@example.com"
            assert record["name"] is None and record["phone"] is None
            command.check(config)
    finally:
        engine.dispose()


def test_vehicle_migration_adds_owner_fk_and_preserves_accounts(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'garage_migration.db'}")
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0002")
            assert "vehicles" not in inspect(connection).get_table_names()
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role) "
                    "VALUES (:id, 'existing@example.com', :hash, 'client')"
                ),
                {"id": "b" * 32, "hash": "example-hash"},
            )

            command.upgrade(config, "0003")
            schema = inspect(connection)
            assert schema.get_pk_constraint("vehicles")["constrained_columns"] == ["id"]
            [owner_fk] = schema.get_foreign_keys("vehicles")
            assert owner_fk["constrained_columns"] == ["client_id"]
            assert owner_fk["referred_table"] == "users"
            assert owner_fk["referred_columns"] == ["id"]
            assert {col["name"] for col in schema.get_columns("vehicles")} == {
                "id",
                "client_id",
                "make",
                "model",
                "year",
                "plate",
                "created_at",
            }
            assert connection.scalar(text("SELECT email FROM users")) == "existing@example.com"

            command.downgrade(config, "0002")
            assert "vehicles" not in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT email FROM users")) == "existing@example.com"
            command.upgrade(config, "head")
            command.check(config)
    finally:
        engine.dispose()
