# RPS backend — auth-service

Учебный backend на Python + FastAPI. Открывайте в VS Code папку с этим README,
`pyproject.toml` и `.git` (после клонирования она может оказаться вложенной).

## Состояние

Реализованы **1.1 — регистрация**, **1.2 — вход по JWT и роли**, **1.3 — профиль клиента**.
Доступны роли `client`, `mechanic`, `manager`; сотрудники создаются служебной командой.
Клиент может просматривать и менять свои имя, телефон и email.
В гараже клиента доступны добавление автомобиля (**2.1**) и просмотр списка (**2.2**).

## Запуск (Windows / PowerShell)

Нужны [uv](https://docs.astral.sh/uv/) и PostgreSQL 17 — локально или через Docker Desktop
с Compose. Подходящий Python (3.12–3.14) uv подберёт сам. `uv sync` создаёт `.venv`
и ставит зависимости по `uv.lock`, включая dev-группу.

Установка uv, если его ещё нет: `winget install --id=astral-sh.uv -e`
или `python -m pip install uv`.

```powershell
uv sync
Copy-Item .env.example .env
```

Сгенерируйте секрет подписи JWT и вставьте результат в поле `JWT_SECRET` файла `.env`:

```powershell
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Не перезаписывайте существующий `.env`, если он уже настроен; добавьте новые поля вручную.
Затем запустите БД, примените миграции и запустите API:

```powershell
docker compose up -d db
docker compose ps
uv run scripts/manage.py migrate
uv run scripts/manage.py run
```

Активация окружения не нужна: `uv run` использует `.venv` и синхронизирует его по `uv.lock`.
Команды одинаковы на Windows, Linux и macOS. В VS Code выберите `.venv` через
Python: Select Interpreter.

Вместо Docker можно создать БД на существующем PostgreSQL и прописать `DATABASE_URL`
в `.env`. Пароль в примере — только для локальной разработки. При изменении
`POSTGRES_*` или порта синхронно измените `DATABASE_URL`. Переменные `POSTGRES_*`
инициализируют новый том БД, но не меняют существующие аккаунты.
Порт в примере — `5433`, чтобы не конфликтовать с локальным PostgreSQL на `5432`;
хост — `127.0.0.1`, чтобы Windows не подставлял IPv6 `::1`.

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI: <http://127.0.0.1:8000/openapi.json>
- ReDoc: <http://127.0.0.1:8000/redoc>

## API и ручная проверка

| Метод | Путь | Назначение | Авторизация | Ответ |
| --- | --- | --- | --- | --- |
| GET | `/health` | Приложение отвечает, БД не проверяется | Нет | `200 {"status":"ok"}` |
| GET | `/health/ready` | Проверка соединения с БД (`SELECT 1`) | Нет | `200 {"status":"ok"}` или `503 {"detail":"Database unavailable"}` |
| POST | `/auth/register` | Регистрация клиента по email и паролю | Нет | `201`, ошибки `409` и `422` |
| POST | `/auth/login` | Вход по email и паролю, JWT access token | Нет | `200`, ошибки `401`, `422` |
| GET | `/auth/me` | Текущая учётная запись и актуальная роль | Bearer JWT, любая из трёх ролей | `200`, ошибка `401` |
| GET | `/users/me` | Свой профиль клиента: имя, телефон, email | Bearer JWT, только `client` | `200`, ошибки `401`, `403` |
| PATCH | `/users/me` | Частичное обновление своего профиля | Bearer JWT, только `client` | `200`, ошибки `401`, `403`, `409`, `422` |
| POST | `/users/me/vehicles` | Добавление автомобиля в свой гараж | Bearer JWT, только `client` | `201`, ошибки `401`, `403`, `422` |
| GET | `/users/me/vehicles` | Список автомобилей своего гаража | Bearer JWT, только `client` | `200` (массив), ошибки `401`, `403` |

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

### Вход и JWT — 1.2

Сначала зарегистрируйте клиента либо создайте сотрудника командой ниже.
Вход использует **JSON**, а не OAuth2 form-data:

```powershell
$loginBody = @{ email = "client@example.com"; password = "ExamplePass123!" } | ConvertTo-Json
$loginResult = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/auth/login `
  -ContentType "application/json" -Body $loginBody
Invoke-RestMethod -Uri http://127.0.0.1:8000/auth/me `
  -Headers @{ Authorization = "Bearer $($loginResult.access_token)" }
```

Ответ входа: `200 {"access_token":"<JWT>","token_type":"bearer","expires_in":1800}`.
Ручка `/auth/me` возвращает `id`, `email`, `role`, `created_at`; это данные учётной записи,
а не профиль с именем и телефоном из задачи 1.3. Пароль и хеш не возвращаются.
В Swagger выполните `/auth/login`, скопируйте `access_token`, нажмите **Authorize**
и вставьте только токен. Затем выполните `/auth/me`.

- Неверный пароль и неизвестный email: одинаковый `401 {"detail":"Invalid email or password"}`.
- Без Bearer-токена: `401 {"detail":"Not authenticated"}`.
- Поддельный, просроченный токен или удалённый пользователь:
  `401 {"detail":"Invalid or expired token"}`. Все ответы `401` содержат `WWW-Authenticate: Bearer`.
- Некорректный email, пустой/отсутствующий пароль, пароль длиннее 128 символов или лишние поля:
  `422` без исходных значений. Непустой неправильный пароль длиной до 128 символов даёт `401`.
- JWT подписывается только HS256. Проверяются подпись, срок, issuer, audience,
  обязательные `sub`, `role`, `iat`, `exp`, `iss`, `aud` и формат UUID пользователя.
  В JWT нет email, пароля или хеша.
- `role` в токене — снимок при входе. Права определяет актуальная роль из БД;
  понижение роли действует и для уже выданного токена. Удалённый аккаунт теряет доступ.
- Зависимость `require_roles(...)` подключается к будущим бизнес-ручкам;
  недостаточная роль даёт `403 {"detail":"Insufficient permissions"}`.
  Все три роли имеют доступ к `/auth/me`; отдельные бизнес-ручки для них пока не добавлялись.
- Refresh-токенов, logout и индивидуального отзыва токенов пока нет.

Настройки в `.env`:

| Переменная | Значение |
| --- | --- |
| `JWT_SECRET` | Обязательный случайный секрет не короче 32 символов, без значения по умолчанию |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 30 по умолчанию, диапазон 1–1440 |
| `JWT_ISSUER` | `rps-auth-service` по умолчанию |
| `JWT_AUDIENCE` | `rps-api` по умолчанию |

После изменения настроек перезапустите API. Изменение TTL влияет на новые токены;
смена секрета делает недействительными ранее выданные токены. Незаполненный/короткий
секрет — ошибка конфигурации входа и защищённых ручек, а не неверный пароль.
JWT-настройки загружаются при первом обращении к этим ручкам; health и регистрация
работают без JWT-настроек. Реальный секрет храните только в локальном `.env`/окружении.

### Создание механика и менеджера

Доступно оператору с доступом к серверу и БД, без публичного HTTP endpoint:

```powershell
uv run python -m app.cli create-staff --email mechanic@example.com --role mechanic
uv run python -m app.cli create-staff --email manager@example.com --role manager
```

Команда дважды запрашивает пароль скрытым вводом в интерактивном терминале. Пароль
не передаётся аргументом командной строки; требования как у регистрации (8–128 символов).
Коды завершения: `0` — создан; `1` — занят email или ошибка БД; `2` — неверный ввод.
Повторный email не обновляет существующего пользователя и не повышает его роль.
После создания сотрудник входит через тот же `POST /auth/login`.
Текст PR и сценарии: `docs/pr/1.2-jwt-auth.md`.

### Профиль клиента — 1.3

Примените миграцию `0002` командой `uv run scripts/manage.py migrate` из папки `backend`.
Она добавляет nullable-поля `name`, `phone`; существующие аккаунты и реквизиты входа
сохраняются. Имя и телефон нового/существующего клиента изначально равны `null`.
При регистрации по-прежнему принимаются только email и пароль; профиль заполняется отдельно.

Получите JWT клиента через `/auth/login`, как выше, затем:

```powershell
$profileHeaders = @{ Authorization = "Bearer $($loginResult.access_token)" }
Invoke-RestMethod -Uri http://127.0.0.1:8000/users/me -Headers $profileHeaders
$profileBody = @{ name = "Иван Петров"; phone = "+79991234567"; email = "new@example.com" } | ConvertTo-Json
Invoke-RestMethod -Method Patch -Uri http://127.0.0.1:8000/users/me `
  -Headers $profileHeaders -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($profileBody))
```

Обе ручки возвращают `200` с полями `id`, `name`, `phone`, `email`, без пароля и хеша.
ID берётся из JWT; доступа к произвольному пользователю по ID нет.
Доступ разрешён только `client`: механик и менеджер получают `403`,
но по-прежнему могут вызвать `/auth/me` для своей учётной записи.

Правила `PATCH /users/me`:

- Требуется хотя бы одно из полей `name`, `phone`, `email`; пустой `{}` → `422`.
- Неуказанные поля сохраняются. `{"name":null,"phone":null}` очищает эти поля.
- Имя: 1–100 символов после удаления внешних пробелов; пустая строка → `422`.
- Телефон: строка `+` и 7–15 цифр ASCII, первая цифра не `0` (например `+79991234567`).
  Внешние пробелы убираются; внутренние пробелы, скобки и дефисы → `422`.
  Проверяется только формат, существование номера и владение им не проверяются.
- Email: формат и нормализация как при регистрации, максимум 254 символа.
  Поле можно пропустить, но нельзя очистить через `null` или пустую строку.
  Собственный email в другом регистре допустим; email другого аккаунта любой роли → `409`.
- Роль, пароль, ID и другие поля менять нельзя: лишнее поле → `422`.
- Изменения атомарны: при ошибке не сохраняется ни одно поле, включая конфликт email.
- Без действительного JWT → `401`; недостаточная роль → `403`.

После смены email входите с новым адресом и прежним паролем. Старый адрес перестаёт
работать для входа в этот аккаунт. Уже выданный JWT остаётся действителен до истечения
срока: его `sub` содержит постоянный UUID, а не email. Подтверждение нового email не входит в MVP.

Пример запроса: `{"name":"Иван Петров","phone":"+79991234567","email":"new@example.com"}`.
Пример ответа `200` (ID — пример):

```json
{
  "id":"c905f54c-dfc1-4e91-8d95-1386a340d8de",
  "name":"Иван Петров",
  "phone":"+79991234567",
  "email":"new@example.com"
}
```

Откат `uv run alembic downgrade 0001` удаляет имя и телефон вместе с их значениями,
но сохраняет аккаунты. Для обычного запуска откат не нужен.
Текст PR и сценарии проверки: `docs/pr/1.3-client-profile.md`.

### Добавление автомобиля — 2.1

Примените миграцию `0003` командой `uv run scripts/manage.py migrate`. В Swagger выполните
`POST /auth/login` под клиентом и вставьте его `access_token` в **Authorize**.
Затем отправьте `POST /users/me/vehicles` с заголовком `Content-Type: application/json`
и `Authorization: Bearer <access_token>`.

```json
{"make":"Toyota","model":"Corolla","year":2020,"plate":"XY 123-Z"}
```

Ответ `201 Created` содержит UUID автомобиля и время создания:

```json
{
  "id":"4ec2a4fb-4382-4d82-bd8c-25041c470566",
  "make":"Toyota",
  "model":"Corolla",
  "year":2020,
  "plate":"XY 123-Z",
  "created_at":"2026-11-24T10:00:00Z"
}
```

Все четыре поля обязательны. Краевые пробелы у `make`, `model` и `plate` удаляются,
пустые строки отклоняются. `year` — целое JSON-число в диапазоне PostgreSQL `integer`.
Госномер принимается без привязки к стране. Повторный номер допустим.
Владелец определяется по JWT и сохраняется в `vehicles.client_id`.

| Код | Что проверить |
| --- | --- |
| `401` | Отправить запрос без токена или с недействительным Bearer JWT |
| `403` | Отправить запрос с токеном механика или менеджера |
| `422` | Отправить пустое строковое поле, год строкой, пропустить обязательное поле или добавить `client_id` |

Для проверки сохранения запросите строку по полученному UUID из новой сессии тестовой БД.
Поле `client_id` в таблице должно совпадать с `id` из `GET /auth/me` для этого токена.

### Список автомобилей — 2.2

`GET /users/me/vehicles` использует таблицу из миграции `0003`. Войдите через
`POST /auth/login` и передайте `Authorization: Bearer <access_token>` либо используйте
**Authorize** в Swagger. Запрос не принимает тело или параметры для выбора владельца.

Ответ `200 OK` — массив объектов с полями `id`, `make`, `model`, `year`, `plate`,
`created_at`. Сначала идут новые записи (`created_at DESC`). При совпадении даты
сортировка по `id DESC`. Пустой гараж возвращает `200 OK` с телом `[]`.

Для ручной проверки добавьте два автомобиля первому клиенту и один второму через
`POST /users/me/vehicles`. Вызовите GET с каждым токеном и сравните UUID в ответах с
идентификаторами при создании. Запрос без действительного JWT даёт `401`,
с токеном механика или менеджера — `403`.

## Команды разработчика

```powershell
uv run scripts/manage.py check   # линтер + форматирование + тесты
uv run scripts/manage.py test
uv run scripts/manage.py lint
uv run scripts/manage.py format  # изменяет файлы
uv run scripts/manage.py migrate
uv build --wheel
```

Локальные тесты используют изолированную SQLite in-memory, подготовленную через Alembic.
Для PostgreSQL задайте `TEST_DATABASE_URL` **отдельной пустой тестовой БД**: тесты применяют
к ней миграции; данные каждого теста откатываются внешней транзакцией.
Не направляйте тесты на рабочую БД. CI использует PostgreSQL 17:
проверки, применение миграций, проверка расхождений схемы и сборка wheel.

Зависимости описаны в `pyproject.toml`, зафиксированы в `uv.lock` и экспортированы
в `requirements*.txt` для установки обычным pip. После изменения зависимостей:

```powershell
uv lock
uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt
uv export --frozen --no-emit-project --format requirements-txt -o requirements-dev.txt
```

`requirements*.txt` нужны только для установки без uv; для запуска и разработки
используйте `uv sync` и `uv run`.

## Миграции

Схема меняется через Alembic, без `create_all()` при старте приложения.
Новые ORM-модели импортируются в `migrations/env.py` для заполнения metadata.

```powershell
uv run alembic revision --autogenerate -m "describe change"
# Проверьте сгенерированный файл перед применением.
uv run scripts/manage.py migrate
uv run alembic check
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
Текст PR JWT и ролей: `docs/pr/1.2-jwt-auth.md`.
Текст PR профиля клиента: `docs/pr/1.3-client-profile.md`.

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
- [PyJWT: подпись и проверка токенов](https://pyjwt.readthedocs.io/en/stable/usage.html)
