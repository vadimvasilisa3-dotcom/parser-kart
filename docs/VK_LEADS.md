# Лиды «ВК под ключ»

Парсер собирает салоны с Яндекс.Карт, вытаскивает ссылку ВК из `social_media`, оценивает группу (если есть токен) и отдаёт таблицу лидов.

## Запуск

```bash
cd C:\Projects\parser-kart
# в .env: VK_ACCESS_TOKEN=... (опционально), VK_SCORING_ENABLED=true|false
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Job

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d "{\"category\":\"Салоны красоты\",\"city\":\"Калуга\",\"max_results\":30,\"filter_vk_hot\":true,\"dedupe\":true}"
```

UI: пресет **«ВК лиды»** — категория «Салоны красоты», фильтры hot + no_vk.

## Скачать лиды

```bash
curl -OJ http://127.0.0.1:8000/api/jobs/{job_id}/leads
```

Файлы в сессии: `leads.xlsx`, `leads.csv`. Кнопка в UI: **Лиды ВК**.

## Метки

| Метка | Оффер |
|-------|--------|
| `no_vk` | Создать ВК — 2 990 ₽ |
| `hot` (score ≥ 50) | Довести до записи — 2 000 ₽ |
| `warm` | Пакет «Запись» |
| `ok` | Не звоним |

Без `VK_ACCESS_TOKEN` или при `VK_SCORING_ENABLED=false`: `vk_url` заполняется, `vk_score=null`.

## Тесты

```bash
python -m pytest tests/test_vk_leads.py tests/test_smoke.py -v
```
