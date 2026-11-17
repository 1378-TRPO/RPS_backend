"""Administrative commands. Run: python -m app.cli create-staff --help."""

import argparse
import sys
import warnings
from getpass import GetPassWarning, getpass

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import UserRole
from app.schemas.auth import RegisterRequest
from app.services.registration import EmailAlreadyRegisteredError, create_staff_user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    staff_parser = commands.add_parser("create-staff", help="Создать механика или менеджера")
    staff_parser.add_argument("--email", required=True)
    staff_parser.add_argument("--role", required=True, choices=["mechanic", "manager"])
    args = parser.parse_args(argv)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("Пароль (8–128 символов): ")
            confirmation = getpass("Повторите пароль: ")
    except (EOFError, KeyboardInterrupt, GetPassWarning):
        print("Нужен интерактивный терминал с безопасным вводом пароля.", file=sys.stderr)
        return 2
    if password != confirmation:
        print("Пароли не совпадают.", file=sys.stderr)
        return 2
    try:
        data = RegisterRequest(email=args.email, password=password)
    except ValidationError:
        print("Некорректный email или пароль: требуется 8–128 символов.", file=sys.stderr)
        return 2
    try:
        with Session(get_engine()) as db:
            user = create_staff_user(db, data, UserRole(args.role))
            print(f"Создан {user.role.value}: {user.email} ({user.id})")
    except EmailAlreadyRegisteredError:
        print(
            "Email уже зарегистрирован; роль существующего аккаунта не изменена.", file=sys.stderr
        )
        return 1
    except (SQLAlchemyError, ValidationError):
        print("Не удалось создать аккаунт. Проверьте DATABASE_URL и миграции.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
