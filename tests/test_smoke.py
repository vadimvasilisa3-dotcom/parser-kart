"""Локальные smoke-тесты API и логики jobs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.database import init_db
from app.jobs import _build_search_query, _normalize_result, _passes_filters, filter_match_labels
from app.main import app

init_db()
client = TestClient(app)


def _ru_key(s: str) -> str:
    return s.replace("Ё", "Е").replace("ё", "е").lower()


def test_build_search_query():
    assert _build_search_query("Салоны красоты", "Чебоксары", None) == "Салоны красоты Чебоксары"
    assert _build_search_query(None, None, "  кафе Москва  ") == "кафе Москва"
    assert _build_search_query(None, None, None) == "организации"


def test_passes_filters():
    base = {
        "website": "",
        "phone": "+7",
        "social_media": [],
        "has_photos": True,
        "has_reviews": False,
        "has_menu": True,
    }
    # ИЛИ: нет отзывов — проходит, хотя есть фото
    assert _passes_filters(
        base,
        {"no_website": True, "no_photos": True, "no_reviews": True, "no_menu": True, "mode": "any"},
    )
    # И: нужны все пустые поля — не проходит
    assert not _passes_filters(
        base,
        {"no_website": True, "no_photos": True, "no_reviews": True, "no_menu": True, "mode": "all"},
    )
    assert _passes_filters(base, {"no_website": True, "mode": "any"})
    assert not _passes_filters({**base, "website": "https://x.ru"}, {"no_website": True, "mode": "any"})


def test_filter_match_labels():
    from app.jobs import filter_match_labels

    place = {"website": "", "has_photos": True, "has_reviews": False, "has_menu": False, "phone": "", "social_media": []}
    labels = filter_match_labels(
        place,
        {"no_website": True, "no_photos": True, "no_reviews": True, "no_menu": True, "mode": "any"},
    )
    assert "отзывов" in labels
    assert "меню" in labels
    assert "сайта" in labels
    assert "фото" not in labels


def test_normalize_result():
    raw = {"name": "Тест", "features": {"Wi‑Fi": True, "Парковка": "есть"}}
    out = _normalize_result(raw)
    assert out["name"] == "Тест"
    assert "Wi‑Fi" in out["services"]


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_jobs_validation():
    r = client.post("/api/jobs", json={})
    assert r.status_code == 400


def test_start_job_returns_id():
    r = client.post(
        "/api/jobs",
        json={"category": "тест", "city": "Москва", "max_results": 1},
    )
    assert r.status_code == 200
    assert "job_id" in r.json()


def test_cities_json():
    path = ROOT / "static" / "cities.json"
    assert path.exists()
    cities = json.loads(path.read_text(encoding="utf-8"))
    assert len(cities) >= 50
    assert "Чебоксары" in cities
    assert "Москва" in cities


def test_cities_sorted_alphabetically():
    path = ROOT / "static" / "cities.json"
    cities = json.loads(path.read_text(encoding="utf-8"))
    sorted_cities = sorted(cities, key=_ru_key)
    assert cities == sorted_cities, f"Города не по алфавиту: {cities[:5]} ..."


def test_cities_served_at_root():
    r = client.get("/cities.json")
    assert r.status_code == 200
    cities = r.json()
    assert len(cities) >= 50


def test_menu_helpers():
    from scraper.menu import format_menu_line, menu_to_services, with_tab

    url = with_tab("https://yandex.ru/maps/org/test/123/", "prices")
    assert "tab=prices" in url
    menu = [{"category": "Стрижки", "name": "Мужская", "price": "1500 ₽"}]
    services, prices = menu_to_services(menu)
    assert services == ["[Стрижки] Мужская — 1500 ₽"]
    assert prices == ["1500 ₽"]
    assert format_menu_line(menu[0]) == "[Стрижки] Мужская — 1500 ₽"


def test_normalize_menu():
    raw = {
        "name": "Салон",
        "menu": [{"category": "Ногти", "name": "Маникюр", "price": "2000 ₽"}],
        "features": {"Wi‑Fi": True},
    }
    out = _normalize_result(raw)
    assert out["menu_count"] == 1
    assert "Маникюр — 2000 ₽" in out["services"][0]
    assert out["prices"] == ["2000 ₽"]


def test_prompt_export():
    from app.prompt_export import build_prompt_md

    places = [
        {
            "name": "Тест",
            "category": "Салон",
            "address": "ул. Ленина",
            "phone": "+7",
            "reviews": [{"author": "Иван", "text": "Отлично", "rating": "5"}],
            "photos": ["/tmp/photo_1.jpg"],
            "services": ["Стрижка"],
        }
    ]
    md = build_prompt_md("тест запрос", places)
    assert "AGENT_WEBSITE.md" in md
    assert "Тест" in md
    assert "Иван" in md


def test_agent_website_prompt():
    from app.agent_website_prompt import build_agent_website_md, write_agent_website_file

    places = [
        {"name": "Салон", "photos": ["a.jpg", "b.jpg", "c.jpg"], "has_photos": True, "folder_path": "/x/orgs/001_Salon"},
        {"name": "Пустой", "photos": [], "has_photos": False},
    ]
    md = build_agent_website_md(places)
    assert "Палитра" in md
    assert "вопрос" in md.lower()
    assert "Салон" in md
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = write_agent_website_file(tmp, places)
        assert Path(path).name == "AGENT_WEBSITE.md"
        assert Path(path).exists()


def test_prompt_references_agent():
    from app.prompt_export import build_prompt_md

    md = build_prompt_md("тест", [{"name": "X", "photos": [], "has_photos": False}])
    assert "AGENT_WEBSITE.md" in md
    assert "Фото для палитры" in md


def test_static_index_has_city_select():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="city"' in html
    assert "city_custom" in html
    assert "scrape_photos" in html
    assert "scrape_menu" in html
    assert 'id="dedupe"' in html
    assert 'id="org_url"' in html


def test_gallery_category_match():
    from scraper.gallery_categories import match_category_slug, section_title

    assert match_category_slug("Услуги") == "uslugi"
    assert match_category_slug("Снаружи") == "snaruzhi"
    assert match_category_slug("Внутри") == "vnutri"
    assert match_category_slug("Вход") == "vhod"
    assert match_category_slug("Все фото") is None
    assert section_title("uslugi") == "Услуги"


def test_normalize_org_url():
    from scraper.url_utils import has_numeric_org_id, is_org_url, normalize_org_url, org_key_from_url, resolve_org_url

    raw = "https://yandex.com/maps/org/tolko_ya/201015300188/gallery/?ll=36.27&z=14"
    norm = normalize_org_url(raw)
    assert norm == "https://yandex.ru/maps/org/tolko_ya/201015300188/"
    assert is_org_url(raw)
    assert org_key_from_url(raw) == "201015300188"

    oid = "https://yandex.ru/maps/?ll=36.27&z=14&oid=201015300188"
    assert is_org_url(oid)
    assert normalize_org_url(oid) == "https://yandex.ru/maps/org/201015300188/"
    assert has_numeric_org_id(normalize_org_url(oid))

    short = "https://yandex.ru/maps/-/CLcQMAk8"
    assert is_org_url(short)
    assert normalize_org_url("https://yandex.ru/maps/org/201015300188/") == "https://yandex.ru/maps/org/201015300188/"
    resolved = resolve_org_url("https://yandex.ru/maps/org/only_me/201015300188/")
    assert "201015300188" in resolved

    poi = (
        "https://yandex.ru/maps/6/kaluga/?ll=36.252692%2C54.512924&mode=poi"
        "&poi%5Bpoint%5D=36.252629%2C54.512939"
        "&poi%5Buri%5D=ymapsbm1%3A%2F%2Forg%3Foid%3D201015300188"
    )
    assert is_org_url(poi)
    assert normalize_org_url(poi) == "https://yandex.ru/maps/org/201015300188/"


def test_start_job_by_url_poi_mode():
    poi = (
        "https://yandex.ru/maps/6/kaluga/?ll=36.252692%2C54.512924&mode=poi"
        "&poi%5Bpoint%5D=36.252629%2C54.512939"
        "&poi%5Buri%5D=ymapsbm1%3A%2F%2Forg%3Foid%3D201015300188"
    )
    r = client.post("/api/jobs/by-url", json={"org_url": poi})
    assert r.status_code == 200
    assert "201015300188" in r.json()["org_url"]


def test_start_job_by_url_gallery_tolko_ya():
    gallery = "https://yandex.com/maps/org/tolko_ya/201015300188/gallery/?ll=36.271210%2C54.509072&z=14"
    r = client.post("/api/jobs/by-url", json={"org_url": gallery})
    assert r.status_code == 200
    assert "201015300188" in r.json()["org_url"]


def test_start_job_by_url_null_limits():
    r = client.post(
        "/api/jobs/by-url",
        json={
            "org_url": "https://yandex.ru/maps/org/test/123456789/",
            "max_photos": None,
            "max_reviews": None,
            "max_menu_items": None,
        },
    )
    assert r.status_code == 200


def test_start_job_by_url_gallery():
    gallery = "https://yandex.com/maps/org/only_me/201015300188/gallery/?ll=36.271210%2C54.509072&z=14"
    r = client.post("/api/jobs/by-url", json={"org_url": gallery})
    assert r.status_code == 200
    assert "201015300188" in r.json()["org_url"]


def test_start_job_custom_query_org_url_redirect():
    gallery = "https://yandex.com/maps/org/only_me/201015300188/gallery/?ll=36.27&z=14"
    r = client.post(
        "/api/jobs",
        json={"custom_query": gallery, "max_results": 1},
    )
    assert r.status_code == 200
    assert "job_id" in r.json()


def test_start_job_by_url():
    r = client.post(
        "/api/jobs/by-url",
        json={"org_url": "https://yandex.ru/maps/org/test/123456789/"},
    )
    assert r.status_code == 200
    assert "job_id" in r.json()
    assert "123456789" in r.json()["org_url"]


def test_start_job_by_url_invalid():
    r = client.post("/api/jobs/by-url", json={"org_url": "https://google.com"})
    assert r.status_code == 400


def test_build_scope_key():
    from app.dedupe import build_scope_key

    assert build_scope_key("Салоны красоты", "Москва", None) == "салоны красоты|москва"
    assert build_scope_key(None, None, "кафе") == "кафе"


def test_collected_count_api():
    from app.database import mark_collected_org

    scope = "тест|город"
    mark_collected_org(scope, "999", "Тест", "job-test")
    r = client.get("/api/collected/count", params={"category": "тест", "city": "город"})
    assert r.status_code == 200
    assert r.json()["count"] >= 1


def test_place_folder_structure():
    import os
    import tempfile

    from scraper.storage import DataManager

    with tempfile.TemporaryDirectory() as tmp:
        dm = DataManager(base_dir=tmp)
        dm.setup_session_directory("тест")
        place = dm.create_place_folder("Салон Красоты", 1)
        assert "001_Салон_Красоты" in place.replace("\\", "/")
        dm.save_place_bundle(
            place,
            {
                "name": "Салон",
                "reviews": [{"author": "Иван", "text": "Ок", "rating": "5"}],
                "menu": [{"name": "Стрижка", "price": "1000 ₽", "category": "Волосы"}],
            },
        )
        assert os.path.isfile(os.path.join(place, "profile.json"))
        assert os.path.isfile(os.path.join(place, "reviews", "reviews.json"))
        assert os.path.isfile(os.path.join(place, "menu", "menu.json"))
        for cat in ("uslugi", "snaruzhi", "vnutri", "vhod"):
            assert os.path.isdir(os.path.join(place, "photos", cat))


def test_cleanup_job_output():
    import tempfile

    from app.cleanup import cleanup_job_output
    from app.database import create_job, get_job, update_job

    init_db()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "session"
        out.mkdir()
        (out / "places_data.json").write_text("{}", encoding="utf-8")
        job_id = create_job("q", "cat", "city", 1, {})
        update_job(job_id, output_dir=str(out), excel_path=str(out / "places_data.json"))
        cleanup_job_output(job_id, str(out))
        assert not out.exists()
        job = get_job(job_id)
        assert job["files_cleaned"] == 1


if __name__ == "__main__":
    import traceback

    tests = [
        test_build_search_query,
        test_passes_filters,
        test_filter_match_labels,
        test_normalize_result,
        test_health,
        test_jobs_validation,
        test_start_job_returns_id,
        test_cities_json,
        test_cities_sorted_alphabetically,
        test_cities_served_at_root,
        test_menu_helpers,
        test_normalize_menu,
        test_prompt_export,
        test_agent_website_prompt,
        test_prompt_references_agent,
        test_gallery_category_match,
        test_static_index_has_city_select,
        test_normalize_org_url,
        test_start_job_by_url_poi_mode,
        test_start_job_by_url,
        test_start_job_by_url_invalid,
        test_build_scope_key,
        test_collected_count_api,
        test_place_folder_structure,
        test_cleanup_job_output,
    ]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL {fn.__name__}: {exc}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
