# chore: подготовить основу auth-service

## Функционал

Техническая задача перед 1.1–1.3: FastAPI-приложение, конфигурация через окружение,
SQLAlchemy, Alembic, PostgreSQL в Compose, health API, команды разработки,
фиксированные зависимости, CI и обязательный шаблон PR для тестировщика.
Регистрация, JWT, роли и профиль в этот PR не входят. Предметных таблиц и ревизий
миграций пока нет; Alembic настроен, первая ревизия появится вместе с пользователями.

## Подготовка проверки

Ветка: `chore/auth-service-setup`. Python 3.13, PostgreSQL 17 или Docker Desktop.
Из папки репозитория, PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
docker compose up -d db
.\.venv\Scripts\python.exe scripts/manage.py migrate
.\.venv\Scripts\python.exe scripts/manage.py run
```

Настройки: `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`.
Используйте локальные значения из `.env.example`; при изменении реквизитов обновите URL.
Тестовые пользователи, токены и роли не требуются.

Base URL: `http://127.0.0.1:8000`. Swagger: `http://127.0.0.1:8000/docs`.

## Ручки для тестировщика

| Метод | Путь | Функционал | Токен / роль | Успех | Ошибки |
| --- | --- | --- | --- | --- | --- |
| GET | `/health` | Доступность приложения без обращения к БД | Не нужны | `200` | — |
| GET | `/health/ready` | Реальное соединение с БД, `SELECT 1` | Не нужны | `200` | `503`, если БД недоступна |

Тело запроса отсутствует. Специальные заголовки не нужны.

```http
GET /health HTTP/1.1
Host: 127.0.0.1:8000
```

Ответ: `200 OK`, `Content-Type: application/json`, тело `{"status":"ok"}`.

```http
GET /health/ready HTTP/1.1
Host: 127.0.0.1:8000
```

При работающей БД: `200 OK`, `Content-Type: application/json`, `{"status":"ok"}`.
При недоступной БД: `503 Service Unavailable`, `Content-Type: application/json`,
`{"detail":"Database unavailable"}`. URL, имя пользователя и пароль БД в ответе отсутствуют.

## Сценарии проверки

| № | Предусловия | Действие | Ожидаемый результат |
| --- | --- | --- | --- |
| 1 | Приложение запущено | GET `/health` | `200`, `{"status":"ok"}` |
| 2 | БД запущена, корректный `DATABASE_URL` | GET `/health/ready` | `200`, `{"status":"ok"}` |
| 3 | `docker compose stop db` | GET `/health` | `200`, `{"status":"ok"}` |
| 4 | БД остановлена, URL всё ещё корректен | GET `/health/ready` | `503`, `{"detail":"Database unavailable"}`, без секретов |
| 5 | `docker compose up -d db`, дождаться готовности | Повторить GET `/health/ready` | `200` без перезапуска API |
| 6 | Приложение запущено | Открыть `/docs` и `/openapi.json` | `200`, обе ручки и статус `503` readiness описаны |

Readiness не проверяет актуальность схемы. Ошибки конфигурации (нет `DATABASE_URL`,
некорректный драйвер/URL) не относятся к сценарию недоступности БД.

## Проверки разработчика

Проверено локально на Python 3.13.2:

- `python scripts/manage.py check`: Ruff и форматирование проходят, **7 тестов проходят**.
- Тесты пройдены на SQLite и на отдельном временном PostgreSQL **18.3**.
  Финальный прогон с PostgreSQL — без предупреждений.
- `python scripts/manage.py migrate`: Alembic подключается к PostgreSQL без ошибок.
- `python -m alembic check`: `No new upgrade operations detected`.
- Проверено через HTTP-интерфейс TestClient с реальным PostgreSQL:
  `/health/ready` → `200`; после остановки БД → `503` с ожидаемым JSON;
  `/health` при остановленной БД → `200`.
- `python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .`:
  пакет `rps_auth_service-0.1.0-py3-none-any.whl` собирается.
- `git diff --check`: ошибок нет.

Тестовый кластер остановлен и удалён; существующие БД не изменялись.
Для отказа соединения добавлен таймаут PostgreSQL 5 секунд.
Docker/Compose и GitHub Actions локально не запускались: Docker отсутствует.
CI настроен на PostgreSQL **17**; результат этого прогона нужно проверить на GitHub.
Проверка браузером Swagger и отдельным процессом Uvicorn остаётся ручным сценарием.

## Definition of Done

- [x] Линтер, форматирование, тесты и сборка проходят локально.
- [x] README и описание API добавлены.
- [x] Функционал, ручки, примеры и сценарии для тестировщика заполнены.
- [ ] CI прошёл на GitHub.
- [ ] PR прошёл review.
- [ ] Результат показан на Sprint Review.
