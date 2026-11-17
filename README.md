# RPS backend — auth-service

Учебный backend на Python + FastAPI. Открывайте в VS Code папку с этим README,
`pyproject.toml` и `.git` (после клонирования она может оказаться вложенной).

## Состояние

Подготовлена основа сервиса и реализована **1.1 — регистрация клиента по email и паролю**.
Добавлены таблица `users`, миграция `0001`, Argon2 и тесты регистрации.
JWT, вход и профиль относятся к следующим задачам 1.2 и 1.3.

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
| POST | `/auth/register` | Регистрация клиента по email и паролю | Нет | `201`, ошибки `409` и `422` |

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

### Регистрация — 1.1

Требуется применить миграции. Через Swagger `/docs` или PowerShell:

```powershell
$registrationBody = @{ email = "client@example.com"; password = "ExamplePass123!" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/auth/register `
  -ContentType "application/json" -Body $registrationBody
```

Запрос:

```json
{"email":"client@example.com","password":"ExamplePass123!"}
```

Ответ `201 Created` (ID и время формируются сервером):

```json
{
  "id": "c905f54c-dfc1-4e91-8d95-1386a340d8de",
  "email": "client@example.com",
  "role": "client",
  "created_at": "2026-11-17T12:00:00Z"
}
```

- Email проверяется на формат и длину до 254 символов; внешние пробелы убираются,
  весь адрес приводится к нижнему регистру. `Client@Example.com` и `client@example.com`
  считаются одним адресом. Уникальность обеспечена также ограничением БД.
- Пароль — строка из 8–128 символов, без требований к набору символов.
  Пробелы пароля сохраняются, пароль не обрезается. В БД хранится только Argon2id-хеш.
- Разрешены только поля `email`, `password`. Роль всегда `client`;
  передача `role` (даже `client`), `id`, `password_hash` или других полей даёт `422`.
- Занятый email → `409 {"detail":"Email already registered"}`;
  неверные/отсутствующие поля или некорректный JSON → `422`.
- В ошибках валидации оставлены `type`, `loc`, `msg`, без исходных значений и тела запроса.
  Пароль и хеш не возвращаются ни в успешном ответе, ни в ошибках валидации.
- Регистрация пока не выдаёт JWT и не подтверждает email.

Повторите запрос с тем же адресом, затем с `CLIENT@EXAMPLE.COM`: оба дадут `409`.
Проверьте пароль `short`, неверный email, отсутствие пароля и добавление `role: manager`:
каждый запрос должен дать `422`, без создания пользователя. Для новых успешных проверок
выбирайте новый email. Подробные сценарии: `docs/pr/1.1-registration.md`.

## Команды разработчика

```powershell
.\.venv\Scripts\python.exe scripts/manage.py check   # линтер + форматирование + тесты
.\.venv\Scripts\python.exe scripts/manage.py test
.\.venv\Scripts\python.exe scripts/manage.py lint
.\.venv\Scripts\python.exe scripts/manage.py format  # изменяет файлы
.\.venv\Scripts\python.exe scripts/manage.py migrate
.\.venv\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist .
```

Локальные тесты используют изолированную SQLite in-memory, подготовленную через Alembic.
Для PostgreSQL задайте `TEST_DATABASE_URL` **отдельной пустой тестовой БД**: тесты применяют
к ней миграции; данные каждого теста откатываются внешней транзакцией.
Не направляйте тесты на рабочую БД. CI использует PostgreSQL 17:
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
Текст PR регистрации: `docs/pr/1.1-registration.md`. PR открывает автор проекта вручную.

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
- [FastAPI: хеширование паролей с pwdlib/Argon2](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
