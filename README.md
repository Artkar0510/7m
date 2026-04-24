# Auth Service

Микросервис авторизации на `FastAPI` с использованием:

- `PostgreSQL` для хранения пользователей
- `Redis` для кеша и blacklist refresh-токенов
- `SQLAlchemy` для моделей и работы с БД
- `Alembic` для миграций
- `PyJWT` для `access` и `refresh` токенов

## Структура проекта

```text
.
├── api/
├── core/
├── db/
├── migrations/
├── schemas/
├── tests/
├── utils/
├── main.py
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
└── requirements.txt
```

## Что умеет сервис

- Регистрация пользователя по `email` и `password`
- Хэширование пароля через `pbkdf2_hmac` с динамической солью
- Логин с выдачей `access` и `refresh` токенов
- Logout с отзывом `refresh token` через blacklist в `Redis`
- Кеширование пользователя в `Redis` для уменьшения числа запросов к `PostgreSQL`
- Интроспекция `access token` для других внутренних сервисов
- Вход и автоматическая регистрация через `Yandex OAuth`

## Конфигурация

Проект использует `.env` файл и вложенные настройки с разделителем `__`.

Пример переменных лежит в [.env.example](/Users/anastasia/Documents/course/6m/.env.example:1).

Основные группы настроек:

- `APP__...` настройки приложения
- `POSTGRES__...` настройки PostgreSQL
- `REDIS__...` настройки Redis и кеша
- `JWT__...` настройки токенов
- `INTERNAL_AUTH__...` служебная авторизация для внутренних сервисов
- `PASSWORD_HASH__...` параметры хэширования пароля
- `TRACING__...` настройки трассировки и `X-Request-Id`
- `YANDEX_OAUTH__...` настройки входа через Яндекс ID

Профиль пользователя в `users` теперь также поддерживает:

- `country_code`
- `region_code`
- `birth_date`
- `last_device_type`

## Локальный запуск

### 1. Установить зависимости

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Создать `.env`

```bash
cp .env.example .env
```

Если запуск локальный вне Docker, обрати внимание на хосты:

- для PostgreSQL обычно `localhost`
- для Redis обычно `localhost`

В `.env.example` сейчас указаны контейнерные имена `postgres` и `redis`, они подходят для `docker compose`.

### 3. Поднять PostgreSQL и Redis

Если сервисы уже установлены локально, можно использовать их.

Если нет, удобнее поднять их через Docker:

```bash
docker compose up -d postgres redis
```

### 4. Применить миграции

```bash
alembic upgrade head
```

В проекте уже добавлена первая миграция для создания таблицы `users`.

### 5. Запустить приложение

```bash
uvicorn main:app --reload
```

После запуска сервис будет доступен по адресу:

- `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Запуск через Docker Compose

### 1. Создать `.env`

```bash
cp .env.example .env
```

### 2. Поднять весь стенд

```bash
docker compose up --build
```

Будут запущены:

- `app` на `http://localhost:8000`
- `postgres` на порту `5432`
- `redis` на порту `6379`
- `jaeger` UI на `http://localhost:16686`

При запуске `app` контейнер автоматически выполняет:

```bash
alembic upgrade head
```

Только после этого стартует `uvicorn`.

Если нужно запустить контейнеры в фоне:

```bash
docker compose up -d --build
```

Остановить стенд:

```bash
docker compose down
```

Остановить стенд и удалить volumes:

```bash
docker compose down -v
```

## Взаимодействие с сервисом

Базовый префикс API:

```text
/api/v1/auth
```

### Проверка здоровья сервиса

`GET /api/v1/auth/health`

Пример:

```bash
curl http://localhost:8000/api/v1/auth/health
```

Ответ:

```json
{
  "status": "ok"
}
```

В каждом ответе сервис возвращает заголовок `X-Request-Id`. Если клиент прислал свой `X-Request-Id`, сервис использует его же; если нет, генерирует новый.

## Трассировка

Сервис экспортирует трассировки в Jaeger через OTLP HTTP.

Настройки по умолчанию:

- `TRACING__ENABLED=true`
- `TRACING__SERVICE_NAME=auth-service`
- `TRACING__JAEGER_ENDPOINT=http://jaeger:4318/v1/traces`
- `TRACING__REQUEST_ID_HEADER=X-Request-Id`

После запуска `docker compose up --build` Jaeger UI доступен по адресу `http://localhost:16686`.

## Вход через Яндекс ID

Интеграция реализована по документации Yandex OAuth: сервис получает `code`, обменивает его на OAuth-токен через `https://oauth.yandex.ru/token`, затем запрашивает профиль пользователя через `https://login.yandex.ru/info`.

Что делает Auth-сервис:

- создаёт одноразовый `state` и хранит его в Redis с TTL
- ищет пользователя по `yandex_user_id`
- если не нашёл, ищет по email и привязывает Яндекс-аккаунт
- если пользователя нет, создаёт нового пользователя без локального пароля
- после этого выдаёт локальные `access` и `refresh` токены сервиса

Для включения интеграции заполните переменные:

- `YANDEX_OAUTH__ENABLED=true`
- `YANDEX_OAUTH__CLIENT_ID=<client_id>`
- `YANDEX_OAUTH__CLIENT_SECRET=<client_secret>`
- `YANDEX_OAUTH__REDIRECT_URI=<redirect_uri>`

Новые endpoint'ы:

- `GET /api/v1/auth/oauth/yandex/authorize`
- `POST /api/v1/auth/oauth/yandex/login`
- `GET /api/v1/auth/oauth/yandex/callback?code=...`

Пример получения URL авторизации:

```bash
curl http://localhost:8000/api/v1/auth/oauth/yandex/authorize
```

Ответ содержит `authorization_url` и `state`. Этот же `state` нужно вернуть в Auth-сервис после редиректа от Яндекса.

Пример завершения входа:

```bash
curl -X POST http://localhost:8000/api/v1/auth/oauth/yandex/login \
  -H "Content-Type: application/json" \
  -d '{
    "code": "yandex-authorization-code",
    "state": "oauth-state-from-authorize-step"
  }'
```

### Регистрация пользователя

`POST /api/v1/auth/register`

Тело запроса:

```json
{
  "email": "user@example.com",
  "password": "strongpass123"
}
```

Пример:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "strongpass123"
  }'
```

Условия:

- `email` должен быть уникальным
- `password` должен быть длиной от 8 символов
- email нормализуется в lowercase перед сохранением

Ответ:

```json
{
  "email": "user@example.com",
  "is_active": true
}
```

### Логин

`POST /api/v1/auth/login`

Тело запроса:

```json
{
  "email": "user@example.com",
  "password": "strongpass123"
}
```

Пример:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "strongpass123"
  }'
```

Пример ответа:

```json
{
  "access_token": "jwt-access-token",
  "refresh_token": "jwt-refresh-token",
  "token_type": "bearer",
  "access_token_expires_in": 1800,
  "refresh_token_expires_in": 2592000
}
```

### Logout

`POST /api/v1/auth/logout`

Тело запроса:

```json
{
  "refresh_token": "jwt-refresh-token"
}
```

Пример:

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "jwt-refresh-token"
  }'
```

Поведение:

- сервис декодирует `refresh token`
- проверяет, не был ли он уже отозван
- кладет `jti` токена в blacklist в `Redis`
- blacklist живет до истечения срока жизни токена

### Интроспекция access token для других сервисов

`POST /api/v1/auth/introspect`

Этот endpoint нужен для внутренних микросервисов.

Он защищен заголовком:

```text
X-Service-Token: <internal service token>
```

Значение токена задается в `.env`:

```text
INTERNAL_AUTH__SERVICE_TOKEN
```

Тело запроса:

```json
{
  "access_token": "jwt-access-token"
}
```

Пример:

```bash
curl -X POST http://localhost:8000/api/v1/auth/introspect \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: internal-service-token" \
  -d '{
    "access_token": "jwt-access-token"
  }'
```

Пример ответа:

```json
{
  "active": true,
  "user_id": 1,
  "email": "user@example.com",
  "token_type": "access",
  "expires_at": 1760000000
}
```

## Как другим сервисам работать с auth-сервисом

Рекомендуемый сценарий:

1. Клиент логинится через auth-сервис и получает `access_token` и `refresh_token`.
2. Клиент передает `access_token` в другие микросервисы.
3. Другой микросервис отправляет `access_token` в `POST /api/v1/auth/introspect`.
4. Auth-сервис подтверждает валидность токена и возвращает claims пользователя.
5. Downstream-сервис принимает решение, разрешать доступ или нет.

Преимущества такого подхода:

- вся логика аутентификации централизована в одном сервисе
- другие сервисы не работают с паролями и не лезут в таблицу пользователей
- можно расширять claims и политики доступа централизованно

## Тесты

Если установлен `pytest`, можно запустить:

```bash
pytest
```

Если команда `pytest` недоступна:

```bash
python3 -m pytest
```

## Текущее состояние проекта

На данный момент в проекте уже есть:

- каркас auth-сервиса
- регистрация
- login/logout
- JWT
- Redis cache
- Redis blacklist refresh-токенов
- introspect endpoint для межсервисной авторизации
- Dockerfile и Docker Compose

Что еще стоит добавить следующим шагом:

- endpoint `refresh` с ротацией refresh-токенов
- роли и права доступа
- более строгую стратегию service-to-service authentication
