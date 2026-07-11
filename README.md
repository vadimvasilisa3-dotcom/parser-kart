# Парсер карт

Свой веб-парсер Яндекс.Карт: форма «Начать сбор», Excel, фото в папках `org_*`.

Движок сбора — адаптация [Koveh/scrape-yandex-maps](https://github.com/Koveh/scrape-yandex-maps) (Selenium + Chrome).

## Локально (Windows / Linux)

```bash
cd c:\Projects\parser-kart
python -m venv .venv
.venv\Scripts\activate   # Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Откройте http://127.0.0.1:8000

**Нужен Google Chrome** (для Selenium).

## Деплой на VDS ([VDSka](https://vdska.ru/control/))

1. Залейте папку проекта на сервер (git clone / scp).
2. На Ubuntu VDS:

```bash
cd parser-kart
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

3. В панели VDSka откройте порт **8000** (или поставьте nginx):

```bash
sudo apt install nginx -y
sudo cp deploy/nginx.conf /etc/nginx/sites-available/parser-kart
sudo ln -sf /etc/nginx/sites-available/parser-kart /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

4. Проверка: `curl http://127.0.0.1:8000/api/health`

## Переменные (.env)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HEADLESS` | `true` | Браузер без окна (для сервера) |
| `MAX_PHOTOS` | `20` | Фото на организацию |
| `PORT` | `8000` | Порт API |

## Выходные данные

```
data/output/20260407_120000_Салоны_красоты_Чебоксары/
├── places_data.xlsx
├── places_data.json
└── org_Камея_20260407_120000/
    └── photos/
        ├── photo_1.jpg
        └── ...
```

## MVP

- ✅ Яндекс.Карты
- ✅ Фильтры: без сайта / соцсетей / телефона
- ✅ Excel + фото
- ⏳ 2ГИС — позже
- ⏳ Вкладка «цены/меню» — доработка парсера

## Disclaimer

Только для легального сбора открытых данных. Соблюдайте правила Яндекс.Карт и лимиты запросов.
