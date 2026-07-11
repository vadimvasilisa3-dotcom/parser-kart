import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.scraper import YandexMapsScraper

from .config import (
    HEADLESS,
    MAX_MENU_ITEMS_DEFAULT,
    MAX_PHOTOS_DEFAULT,
    MAX_REVIEWS_DEFAULT,
    OUTPUT_DIR,
    SCRAPE_MENU,
    SCRAPE_PHOTOS,
    SCRAPE_REVIEWS,
)
from .database import append_log, get_collected_org_keys, get_job, mark_collected_org, update_job
from .dedupe import build_scope_key
from .prompt_export import write_prompt_file
from .agent_website_prompt import write_agent_website_file
from scraper.menu import menu_to_services
from scraper.url_utils import has_numeric_org_id, is_org_url, normalize_org_url, org_key_from_url, resolve_org_url


def _build_search_query(category: str | None, city: str | None, custom: str | None) -> str:
    if custom and custom.strip():
        return custom.strip()
    parts = [p for p in (category, city) if p and p.strip()]
    return " ".join(parts) if parts else "организации"


def _parse_count(value: str | int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    import re

    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else 0


def _filter_checks(place: dict[str, Any]) -> dict[str, bool]:
    """True = у организации НЕТ этого поля (подходит под «Без …»)."""
    return {
        "no_website": not (place.get("website") or "").strip(),
        "no_phone": not (place.get("phone") or "").strip(),
        "no_social": not (place.get("social_media") or []),
        "no_photos": not place.get("has_photos"),
        "no_reviews": not place.get("has_reviews"),
        "no_menu": not place.get("has_menu"),
    }


def _passes_filters(place: dict[str, Any], filters: dict[str, bool]) -> bool:
    """
    Режим по умолчанию — «любой» (ИЛИ): в выгрузку попадает организация,
    если отсутствует ХОТЯ БЫ ОДИН из отмеченных пунктов.
    Режим «все» (И): должны отсутствовать все отмеченные пункты сразу.
    """
    checks = _filter_checks(place)
    active = [key for key, enabled in filters.items() if enabled and key in checks]
    if not active:
        return True

    matched = [key for key in active if checks[key]]
    mode = filters.get("mode", "any")
    if mode == "all":
        return len(matched) == len(active)
    return len(matched) > 0


def filter_match_labels(place: dict[str, Any], filters: dict[str, bool]) -> list[str]:
    labels = {
        "no_website": "сайта",
        "no_phone": "телефона",
        "no_social": "соцсетей",
        "no_photos": "фото",
        "no_reviews": "отзывов",
        "no_menu": "меню",
    }
    checks = _filter_checks(place)
    active = [key for key, enabled in filters.items() if enabled and key in checks]
    return [labels[key] for key in active if checks[key]]


def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    features = raw.get("features") or {}
    menu = raw.get("menu") or []
    if not isinstance(menu, list):
        menu = []

    if menu:
        services, prices = menu_to_services(menu)
    else:
        services = [f"{k}: {v}" if v is not True else k for k, v in features.items()]
        prices = []

    reviews = raw.get("reviews") or []
    if not isinstance(reviews, list):
        reviews = []
    return {
        "name": raw.get("name") or "",
        "phone": raw.get("phone") or "",
        "category": raw.get("category") or "",
        "description": raw.get("description") or "",
        "address": raw.get("address") or "",
        "website": raw.get("website") or "",
        "rating": raw.get("rating") or "",
        "reviews_count": raw.get("reviews_count") or "",
        "reviews": reviews,
        "reviews_scraped": len(reviews),
        "menu": menu,
        "menu_count": len(menu),
        "services": services,
        "prices": prices,
        "features": list(features.keys()) if isinstance(features, dict) else [],
        "working_hours": raw.get("working_hours") or [],
        "social_media": raw.get("social_media") or [],
        "photos": raw.get("photos") or [],
        "photos_count": len(raw.get("photos") or []),
        "photos_by_category": raw.get("photos_by_category") or {},
        "has_photos": bool(raw.get("has_photos")),
        "has_reviews": bool(raw.get("has_reviews")),
        "has_menu": bool(raw.get("has_menu")),
        "link": raw.get("link") or "",
        "folder_path": raw.get("folder_path") or "",
    }


def _export_results(
    scraper: YandexMapsScraper,
    session_dir: str,
    query: str,
    results: list[dict[str, Any]],
) -> tuple[str, str, str, str]:
    flat = []
    for item in results:
        row = dict(item)
        row["services"] = "; ".join(item.get("services") or [])
        row["prices"] = "; ".join(item.get("prices") or [])
        row["menu_count"] = item.get("menu_count") or 0
        row["social_media"] = "; ".join(item.get("social_media") or [])
        row["photos"] = "; ".join(item.get("photos") or [])
        row["working_hours"] = (
            "; ".join(item.get("working_hours") or [])
            if isinstance(item.get("working_hours"), list)
            else (item.get("working_hours") or "")
        )
        reviews = item.get("reviews") or []
        row["reviews_text"] = " | ".join(
            f"{r.get('author', '')}: {(r.get('text') or '')[:300]}"
            for r in reviews
            if isinstance(r, dict)
        )
        row.pop("reviews", None)
        flat.append(row)
    excel_path = scraper.data_manager.export_to_excel(flat, "places_data.xlsx")
    json_path = str(Path(session_dir) / "places_data.json")
    Path(json_path).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_path = write_prompt_file(session_dir, query, results)
    agent_path = write_agent_website_file(session_dir, results)
    return excel_path, json_path, prompt_path, agent_path


class JobRunner:
    _lock = threading.Lock()
    _running: dict[str, threading.Thread] = {}

    def start(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._running:
                return
            thread = threading.Thread(target=self._run, args=(job_id,), daemon=True)
            self._running[job_id] = thread
            thread.start()

    def _run(self, job_id: str) -> None:
        job = get_job(job_id)
        if not job:
            return

        options = job.get("options") or {}
        if options.get("single_org") and options.get("org_url"):
            self._run_by_url(job_id, job)
            return

        query = _build_search_query(job.get("category"), job.get("city"), job.get("query"))
        filters = job.get("filters") or {}
        max_results = int(job.get("max_results") or 10)
        scrape_photos = bool(options.get("scrape_photos", SCRAPE_PHOTOS))
        scrape_reviews = bool(options.get("scrape_reviews", SCRAPE_REVIEWS))
        scrape_menu = bool(options.get("scrape_menu", SCRAPE_MENU))
        dedupe = bool(options.get("dedupe", True))
        max_photos = int(options.get("max_photos", MAX_PHOTOS_DEFAULT))
        max_reviews = int(options.get("max_reviews", MAX_REVIEWS_DEFAULT))
        max_menu_items = int(options.get("max_menu_items", MAX_MENU_ITEMS_DEFAULT))

        update_job(job_id, status="running", message=f"[Яндекс] Начинаем сбор: «{query}»")
        append_log(job_id, f"[Яндекс] Начинаем сбор: «{query}»")

        results: list[dict[str, Any]] = []

        def on_progress(current: int, total: int, message: str) -> None:
            pct = int((current / total) * 100) if total else 0
            update_job(
                job_id,
                progress=pct,
                found=len(results),
                total=total,
                message=message,
            )
            append_log(job_id, message)

        scraper = YandexMapsScraper(
            headless=HEADLESS,
            max_results=max_results,
            scrape_photos=scrape_photos,
            scrape_reviews=scrape_reviews,
            scrape_menu=scrape_menu,
            max_photos=max_photos,
            max_reviews=max_reviews,
            max_menu_items=max_menu_items,
            browser_type="chrome",
        )
        scraper.data_manager.base_dir = str(OUTPUT_DIR)
        scraper.on_progress = on_progress

        scope_key = build_scope_key(job.get("category"), job.get("city"), job.get("query"))
        skip_keys = get_collected_org_keys(scope_key) if dedupe else set()
        if dedupe:
            append_log(
                job_id,
                f"Дедупликация: уже в базе {len(skip_keys)} организаций по «{scope_key}»",
            )

        try:
            scraper.setup_driver()
            scraper.data_manager.setup_session_directory(query)
            append_log(job_id, "Открываем Яндекс.Карты…")
            scraper.driver.get("https://yandex.ru/maps")
            scraper._perform_search(query)
            append_log(job_id, "Собираем список организаций…")
            place_links = scraper._scroll_and_collect_results(skip_keys=skip_keys, target=max_results)
            total_links = min(len(place_links), max_results)
            update_job(job_id, total=total_links)

            processed = 0
            skipped = 0
            for i, link in enumerate(place_links[:max_results]):
                name_hint = f"организация {i + 1}"
                append_log(job_id, f"Сбор данных компании {name_hint}…")
                on_progress(i, total_links, f"Обработка {i + 1}/{total_links}")

                main_url = link
                if "/gallery/" in main_url:
                    main_url = main_url.replace("/gallery/", "/")
                scraper.driver.get(main_url)
                import time

                time.sleep(3)
                raw = scraper._extract_details(i + 1, query)
                if not raw:
                    continue

                processed += 1
                place = _normalize_result(raw)
                org_key = org_key_from_url(place.get("link") or link)
                if dedupe and org_key:
                    mark_collected_org(scope_key, org_key, place.get("name") or "", job_id)

                if not _passes_filters(place, filters):
                    skipped += 1
                    update_job(job_id, skipped=skipped)
                    append_log(job_id, f"Пропуск (фильтр): {place['name']} — нет ни одного из выбранных «пустых» полей")
                    continue

                match_note = ""
                reasons = filter_match_labels(place, filters)
                if reasons:
                    match_note = f" (нет: {', '.join(reasons)})"

                if place.get("photos"):
                    append_log(
                        job_id,
                        f"Сканируем фото ({min(len(place['photos']), max_photos)}/{max_photos})…",
                    )
                if place.get("reviews_scraped"):
                    append_log(job_id, f"Отзывы: {place['reviews_scraped']} шт.")
                if place.get("menu_count"):
                    append_log(job_id, f"Меню: {place['menu_count']} услуг с ценами")

                results.append(place)
                update_job(job_id, found=len(results), results_json=json.dumps(results, ensure_ascii=False))
                append_log(job_id, f"Найдено: {place['name']}{match_note}")

            session_dir = scraper.data_manager.current_session_dir
            excel_path = ""
            json_path = ""
            prompt_path = ""
            agent_path = ""
            if results:
                excel_path, json_path, prompt_path, agent_path = _export_results(
                    scraper, session_dir, query, results
                )
                append_log(job_id, "Сохранены JSON, Excel, PROMPT.md и AGENT_WEBSITE.md")

            finished = datetime.now(timezone.utc).isoformat()
            summary = f"Готово: {len(results)} в выгрузке"
            if processed:
                summary += f" (обработано {processed}"
                if skipped:
                    summary += f", пропущено фильтром {skipped}"
                summary += ")"
            if dedupe and skip_keys:
                summary += f". В базе по запросу: {len(skip_keys) + processed}"
            update_job(
                job_id,
                status="completed",
                progress=100,
                found=len(results),
                skipped=skipped,
                total=processed,
                output_dir=session_dir,
                excel_path=excel_path or "",
                json_path=json_path or "",
                prompt_path=prompt_path or "",
                agent_prompt_path=agent_path or "",
                results_json=json.dumps(results, ensure_ascii=False),
                message=summary,
                finished_at=finished,
            )
            append_log(job_id, f"Сбор завершён. {summary}")
        except Exception as exc:
            update_job(
                job_id,
                status="failed",
                message=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            append_log(job_id, f"Ошибка: {exc}")
        finally:
            try:
                if scraper.driver:
                    scraper.driver.quit()
            except Exception:
                pass
            with self._lock:
                self._running.pop(job_id, None)

    def _run_by_url(self, job_id: str, job: dict[str, Any]) -> None:
        import time

        options = job.get("options") or {}
        raw_url = str(options.get("raw_org_url") or options.get("org_url") or "").strip()
        org_url = resolve_org_url(raw_url)
        open_url = raw_url if is_org_url(raw_url) else org_url
        org_key = org_key_from_url(org_url)
        label = f"org_{org_key}"

        scrape_photos = bool(options.get("scrape_photos", SCRAPE_PHOTOS))
        scrape_reviews = bool(options.get("scrape_reviews", SCRAPE_REVIEWS))
        scrape_menu = bool(options.get("scrape_menu", SCRAPE_MENU))
        max_photos = int(options.get("max_photos", MAX_PHOTOS_DEFAULT))
        max_reviews = int(options.get("max_reviews", MAX_REVIEWS_DEFAULT))
        max_menu_items = int(options.get("max_menu_items", MAX_MENU_ITEMS_DEFAULT))

        update_job(job_id, status="running", message=f"[Яндекс] Сбор карточки по ссылке…", total=1)
        append_log(job_id, f"[Яндекс] Сбор по ссылке: {raw_url}")
        if open_url != org_url:
            append_log(job_id, f"Нормализовано: {org_url}")
        append_log(job_id, "Режим карточки: фильтры и дедупликация не применяются")

        results: list[dict[str, Any]] = []
        scraper = YandexMapsScraper(
            headless=HEADLESS,
            max_results=1,
            scrape_photos=scrape_photos,
            scrape_reviews=scrape_reviews,
            scrape_menu=scrape_menu,
            max_photos=max_photos,
            max_reviews=max_reviews,
            max_menu_items=max_menu_items,
            browser_type="chrome",
        )
        scraper.data_manager.base_dir = str(OUTPUT_DIR)

        try:
            scraper.setup_driver()
            scraper.data_manager.setup_session_directory(label)
            append_log(job_id, "Открываем карточку организации…")
            scraper.driver.get(open_url)
            time.sleep(4)
            resolved = normalize_org_url(scraper.driver.current_url)
            if has_numeric_org_id(resolved):
                org_url = resolved
                org_key = org_key_from_url(org_url)
                append_log(job_id, f"Карточка: {org_url}")
            elif not has_numeric_org_id(org_url):
                scraper._dismiss_overlays()
                time.sleep(2)
                resolved = normalize_org_url(scraper.driver.current_url)
                if has_numeric_org_id(resolved):
                    org_url = resolved
                    org_key = org_key_from_url(org_url)
                    append_log(job_id, f"Карточка после редиректа: {org_url}")

            if not has_numeric_org_id(org_url):
                raise RuntimeError(
                    "Не удалось открыть карточку организации. "
                    "Вставьте прямую ссылку вида https://yandex.ru/maps/org/…/123456789/ "
                    "или ссылку с параметром ?oid=123456789"
                )

            # Не уходим с /gallery/ до извлечения — иначе теряются фото
            current_path = scraper.driver.current_url.split("?")[0].rstrip("/")
            org_path = org_url.rstrip("/")
            if "/gallery/" not in current_path and current_path != org_path:
                scraper.driver.get(org_url)
                time.sleep(3)

            scraper._wait_for_org_page(timeout=20)
            update_job(job_id, progress=30, message="Сбор данных карточки…")
            raw = scraper._extract_details(1, label)
            if not raw:
                scraper.driver.get(org_url)
                time.sleep(3)
                scraper._wait_for_org_page(timeout=15)
                raw = scraper._extract_details(1, label)
            if not raw:
                raise RuntimeError("Не удалось прочитать карточку — проверьте ссылку")

            place = _normalize_result(raw)
            results.append(place)
            update_job(job_id, progress=80, found=1, results_json=json.dumps(results, ensure_ascii=False))
            append_log(job_id, f"Собрано: {place['name']}")
            if place.get("photos_count"):
                append_log(job_id, f"Фото: {place['photos_count']} шт.")
            if place.get("reviews_scraped"):
                append_log(job_id, f"Отзывы: {place['reviews_scraped']} шт.")
            if place.get("menu_count"):
                append_log(job_id, f"Меню: {place['menu_count']} поз.")

            session_dir = scraper.data_manager.current_session_dir
            excel_path, json_path, prompt_path, agent_path = _export_results(
                scraper, session_dir, place["name"] or label, results
            )
            append_log(job_id, "Сохранены JSON, Excel, PROMPT.md и AGENT_WEBSITE.md")

            summary = f"Готово: {place['name'] or 'организация'}"
            update_job(
                job_id,
                status="completed",
                progress=100,
                found=1,
                skipped=0,
                total=1,
                output_dir=session_dir,
                excel_path=excel_path,
                json_path=json_path,
                prompt_path=prompt_path,
                agent_prompt_path=agent_path,
                results_json=json.dumps(results, ensure_ascii=False),
                message=summary,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            append_log(job_id, summary)
        except Exception as exc:
            update_job(
                job_id,
                status="failed",
                message=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            append_log(job_id, f"Ошибка: {exc}")
        finally:
            try:
                if scraper.driver:
                    scraper.driver.quit()
            except Exception:
                pass
            with self._lock:
                self._running.pop(job_id, None)


job_runner = JobRunner()
