# Салон-Маркетолог v2 — контракт бэкенд ↔ фронтенд (OAuth VK / Яндекс)

Этот файл — единственный источник правды по API между воркерами `backend-oauth-api`
и `frontend-v2`. Оба воркера обязаны следовать ему дословно, чтобы интеграция
собралась без переписывания. Не меняйте пути/имена полей — если контракт кажется
неполным, реализуйте по нему и опишите отклонение в handoff (секция Notes).

## Общая архитектура

- Фронтенд `tools/salon-marketing-app/` — статичный (HTML+CSS+vanilla JS), данные в localStorage.
- Бэкенд `tools/salon-marketing-app/backend/` — Python 3 + FastAPI + uvicorn (стек репозитория).
- Секреты OAuth (client_id/secret) и сами токены живут ТОЛЬКО на бэкенде.
  Фронтенду отдаётся исключительно статус подключения (connected: true/false), никогда токены.
- Идентификатор салона: `salon_id` — произвольная непустая строка (фронт генерирует UUID
  и хранит в localStorage под ключом `sm_salon_id`).

## Переменные окружения бэкенда (.env, читаются через существующий app/config.py-стиль)

| Переменная | Назначение |
|------------|-----------|
| `VK_CLIENT_ID`, `VK_CLIENT_SECRET` | приложение VK (VK Ads / VK ID) |
| `YANDEX_CLIENT_ID`, `YANDEX_CLIENT_SECRET` | приложение Яндекс OAuth (Яндекс.Директ scope) |
| `OAUTH_REDIRECT_BASE` | публичный базовый URL бэкенда, напр. `http://127.0.0.1:8000` |
| `FRONTEND_URL` | URL фронтенда для CORS и финального редиректа, напр. `http://127.0.0.1:8777/sites` или файл-хост |
| `TOKENS_DB_PATH` | путь к файлу хранилища токенов (по умолчанию `backend/tokens.sqlite3` или `backend/tokens.json`) |

Отсутствие ключей провайдера не должно ронять сервер: `/oauth/<p>/start` тогда
возвращает 503 с понятным JSON `{ "error": "provider_not_configured", "provider": "vk" }`.

## HTTP endpoints (все под бэкенд-хостом)

- `GET /health` → `200 {"status":"ok","service":"salon-marketolog-backend"}`
- `GET /oauth/{provider}/start?salon_id=<id>` где provider ∈ `vk|yandex`
  → `302` redirect на authorize-URL провайдера. Бэкенд генерирует и хранит `state`
    (CSRF), связывает его с `salon_id`. redirect_uri = `${OAUTH_REDIRECT_BASE}/oauth/{provider}/callback`.
- `GET /oauth/{provider}/callback?code=<c>&state=<s>` (иногда `error=<e>`)
  → бэкенд валидирует `state`, обменивает `code` на access_token (+refresh при наличии),
    сохраняет токен в хранилище под (salon_id, provider), затем `302` redirect на
    `${FRONTEND_URL}?connected={provider}` (при ошибке `?oauth_error={provider}`).
- `GET /oauth/status?salon_id=<id>`
  → `200 {"vk":{"connected":true|false},"yandex":{"connected":true|false}}`.
    Никаких токенов в ответе.
- `POST /oauth/{provider}/disconnect?salon_id=<id>` → `200 {"ok":true}` (удаляет токен).

CORS: разрешить origin из `FRONTEND_URL` (и `*` для локальной разработки как fallback),
методы GET/POST, чтобы фронт мог дергать `/oauth/status` из браузера (fetch).

## Контракт фронтенда

- В существующей вкладке «🔌 Интеграции» добавить для VK Ads и Яндекс.Директ кнопки
  «Подключить», открывающие `${BACKEND_URL}/oauth/{provider}/start?salon_id=<id>`
  в новом окне/вкладке (или через redirect с возвратом по `?connected=`).
- `BACKEND_URL` — настраиваемое поле в приложении (localStorage `sm_backend_url`,
  плейсхолдер `http://127.0.0.1:8000`). Если пусто — показывать подсказку
  «укажите адрес бэкенда» и не ломать остальные модули (backend опционален для v1-функций).
- После возврата с `?connected=<provider>` показать успех; периодически/по кнопке
  опрашивать `GET /oauth/status?salon_id=<id>` и отображать бейджи «Подключено».
- Никогда не хранить и не запрашивать токены на фронте.

## Приёмка интеграции (общая)

- `node tools/salon-marketing-app/test.js` — зелёный (расширенный, без регрессий v1).
- `node --check tools/salon-marketing-app/app.js` и `node --check tools/salon-marketing-app/data.js` — без ошибок.
- Бэкенд стартует: `uvicorn`-приложение импортируется, `GET /health` → ok (smoke-скрипт в backend/).
