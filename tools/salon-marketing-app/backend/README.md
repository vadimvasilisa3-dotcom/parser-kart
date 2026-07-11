# Бэкенд OAuth — Салон-Маркетолог v2

```powershell
cd tools/salon-marketing-app/backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# заполните VK_CLIENT_ID, VK_CLIENT_SECRET, YANDEX_* при необходимости
uvicorn main:app --reload --port 8000
```

Проверка:
```powershell
python smoke_test.py
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/oauth/status?salon_id=test"
```

Без ключей провайдера `/oauth/vk/start` вернёт `503 provider_not_configured` — это нормально.
