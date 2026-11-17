# RPS backend — auth-service

Учебный backend на Python + FastAPI. Открывайте в VS Code папку с этим README,
`pyproject.toml` и `.git` (после клонирования она может оказаться вложенной).

## Состояние

Подготовлена основа сервиса: конфигурация, SQLAlchemy, Alembic, health endpoints,
тесты, CI и шаблон PR. Регистрация, JWT и профиль будут отдельными фичами.
Предметных таблиц пока нет; первая миграция появится в задаче 1.1.

## Запуск (Windows / PowerShell)

Нужны Python 3.13 и PostgreSQL 17 — локально или через Docker Desktop с Compose.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
docker compose up -d db
docker compose ps
.\.venv\Scripts\python.exe scripts/manage.py migrate
.\.venv\Scripts\python.exe scripts/manage.py run
```

Активация окружения и изменение ExecutionPolicy не нужны. В VS Code выберите
`.venv` через Python: Select Interpreter. Для Linux/macOS используйте `.venv/bin/python`.

Вместо Docker можно создать БД на существующем PostgreSQL и прописать `DATABASE_URL`
в `.env`. Пароль в примере — только для локальной разработки. При изменении
`POSTGRES_*` или порта синхронно измените `DATABASE_URL`. Переменные `POSTGRES_*`
инициализируют новый том БД, но не меняют существующие аккаунты.

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI: <http://127.0.0.1:8000/openapi.json>
- ReDoc: <http://127.0.0.1:8000/redoc>

## API и ручная проверка

| Метод | Путь | Назначение | Авторизация | Ответ |
| --- | --- | --- | --- | --- |
| GET | `/health` | Приложение отвечает, БД не проверяется | Нет | `200 {"status":"ok"}` |
| GET | `/health/ready` | Проверка соединения с БД (`SELECT 1`) | Нет | `200 {"status":"ok"}` или `503 {"detail":"Database unavailable"}` |

Readiness проверяет соединение, но не наличие таблиц и актуальность миграций.
Для PostgreSQL установлен таймаут подключения 5 секунд.
Отсутствующий или некорректный `DATABASE_URL` — ошибка конфигурации, а не ответ `503`.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

При работающей БД обе ручки возвращают `200`. После `docker compose stop db`
первая продолжает возвращать `200`, а вторая возвращает `503` без реквизитов подключения.
Верните БД командой `docker compose up -d db`. Обе ручки должны отображаться в Swagger.

## Команды разработчика

```powershell
.\.venv\Scripts\python.exe scripts/manage.py check   # линтер + форматирование + тесты
.\.venv\Scripts\python.exe scripts/manage.py test
.\.venv\Scripts\python.exe scripts/manage.py lint
.\.venv\Scripts\python.exe scripts/manage.py format  # изменяет файлы
.\.venv\Scripts\python.exe scripts/manage.py migrate
.\.venv\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist .
```

Локальные тесты используют изолированную SQLite in-memory. Для проверки на PostgreSQL
задайте `TEST_DATABASE_URL` отдельной тестовой БД. CI использует PostgreSQL 17:
проверки, применение миграций, проверка расхождений схемы и сборка wheel.

Зависимости описаны в `pyproject.toml`, зафиксированы в `uv.lock` и экспортированы
в `requirements*.txt` для установки обычным pip. После изменения зависимостей:

```powershell
python -m uv lock
python -m uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt
python -m uv export --frozen --no-emit-project --format requirements-txt -o requirements-dev.txt
```

Для этих трёх команд нужен uv (`python -m pip install uv`). Для запуска сервиса он не нужен.

## Миграции

Схема меняется через Alembic, без `create_all()` при старте приложения.
Новые ORM-модели импортируются в `migrations/env.py` для заполнения metadata.

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "describe change"
# Проверьте сгенерированный файл перед применением.
.\.venv\Scripts\python.exe scripts/manage.py migrate
.\.venv\Scripts\python.exe -m alembic check
```

## Agile и Git

| Задача | Ветка | Оценка |
| --- | --- | --- |
| Основа сервиса | `chore/auth-service-setup` | Техническая задача |
| 1.1 Регистрация | `feature/1.1-registration` | 2 SP |
| 1.2 JWT и роли | `feature/1.2-jwt-auth` | 3 SP |
| 1.3 Профиль | `feature/1.3-client-profile` | 1 SP |

Следующую ветку создаём от обновлённой `main` после review и слияния предыдущего PR.
Статусы: To Do → In Progress → Review → Done. Sprint Review отмечаем только после показа.

**Каждый PR обязательно описывает функционал, ручки, авторизацию, примеры запросов
и ответов, ожидаемые статусы и сценарии для тестировщика.** Шаблон:
`.github/pull_request_template.md`. Описание первого PR: `docs/pr/auth-service-setup.md`.

Критерии связанных User Story пока не предоставлены. Предложения для согласования:

- **1.1:** `POST /auth/register`, email и пароль, роль только `client`, `201` при успехе,
  `409` при занятом email, `422` при некорректных данных; пароль хранится как Argon2-хеш.
- **1.2:** `POST /auth/login`, JWT с ограниченным сроком, роли `client`, `mechanic`, `manager`;
  `401` при неверных данных/токене, `403` при недостаточной роли. Для механиков и менеджеров —
  служебная команда, без публичного выбора роли.
- **1.3:** `GET /users/me`, `PATCH /users/me`; свои имя, телефон, уникальный email;
  роль и пароль через профиль не меняются.
- Вне MVP: подтверждение email, восстановление пароля, refresh-токены.

## Официальная документация

- [FastAPI: тестирование](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy: PostgreSQL и psycopg](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)
- [Ruff: интеграция с CI](https://docs.astral.sh/ruff/integrations/)
