"""Генерация PROMPT.md для передачи данных в ИИ (сайт, лендинг)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _photo_status_from_place(photos: list, has_photos_on_maps: bool | None) -> tuple[int, str]:
    count = len(photos) if photos else 0
    if count >= 3:
        return count, "достаточно — агент анализирует photos/ и подбирает палитру"
    if count > 0:
        return count, "мало файлов — палитра предварительная"
    if has_photos_on_maps:
        return 0, "на Яндексе есть, в ZIP нет — включите «Фото» при сборе"
    return 0, "нет — агент должен спросить стиль и цвета у заказчика"


def _reviews_block(reviews: list[dict[str, Any]], limit: int = 15) -> str:
    if not reviews:
        return "_Отзывы не собраны._"
    lines = []
    for i, r in enumerate(reviews[:limit], 1):
        author = r.get("author") or "Аноним"
        rating = r.get("rating") or "—"
        date = r.get("date") or ""
        text = (r.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"{i}. **{author}** ({rating}, {date})\n   {text}")
    return "\n\n".join(lines) if lines else "_Тексты отзывов пусты._"


def build_prompt_md(query: str, places: list[dict[str, Any]]) -> str:
    sections = [
        "# Бриф: данные компании (факты, услуги, отзывы)",
        "",
        "> **Инструкции для агента-сайтбилдера** — в файле `AGENT_WEBSITE.md` (палитра по фото, процесс, вопросы).",
        "> Прикрепи в чат агенту: **AGENT_WEBSITE.md** + этот файл + папку `orgs/`.",
        "",
        f"**Поисковый запрос:** {query}",
        f"**Компаний в выгрузке:** {len(places)}",
        "",
        "---",
        "",
        "## Задача",
        "",
        "Используй `AGENT_WEBSITE.md` как системный промпт. Здесь — только **данные** по организациям.",
        "Палитру и стиль подбирай по фото в `orgs/…/photos/`; если фото нет — задай вопросы заказчику (см. AGENT_WEBSITE.md).",
        "",
    ]

    for idx, p in enumerate(places, 1):
        photos = p.get("photos") or []
        reviews = p.get("reviews") or []
        services = p.get("services") or []
        features = p.get("features") or []
        social = p.get("social_media") or []
        hours = p.get("working_hours") or []

        count, status = _photo_status_from_place(photos, p.get("has_photos"))
        sections += [
            f"## {idx}. {p.get('name') or 'Без названия'}",
            "",
            f"- **Категория:** {p.get('category') or '—'}",
            f"- **Адрес:** {p.get('address') or '—'}",
            f"- **Телефон:** {p.get('phone') or '—'}",
            f"- **Сайт:** {p.get('website') or '—'}",
            f"- **Рейтинг:** {p.get('rating') or '—'} ({p.get('reviews_count') or '0'} отзывов на картах)",
            f"- **Ссылка на карточку:** {p.get('link') or '—'}",
            f"- **Папка:** `orgs/…/photos/` → uslugi/, snaruzhi/, vnutri/, vhod/ ({count} всего)",
            f"- **Фото для палитры:** {status}",
            "",
        ]

        if p.get("description"):
            sections += ["### Описание", "", p["description"], ""]

        if services:
            sections += ["### Услуги и цены (меню)", ""]
            sections += [f"- {s}" for s in services]
            sections.append("")

        menu = p.get("menu") or []
        if menu and not services:
            sections += ["### Услуги и цены (меню)", ""]
            for m in menu[:40]:
                if not isinstance(m, dict):
                    continue
                name = m.get("name") or ""
                price = m.get("price") or ""
                cat = m.get("category") or ""
                line = f"{name} — {price}" if price else name
                if cat:
                    line = f"[{cat}] {line}"
                sections.append(f"- {line}")
            sections.append("")

        if features:
            sections += ["### Особенности", "", ", ".join(features), ""]

        if hours:
            sections += ["### Часы работы", ""]
            if isinstance(hours, list):
                sections += [f"- {h}" for h in hours]
            else:
                sections.append(str(hours))
            sections.append("")

        if social:
            sections += ["### Соцсети", "", ", ".join(social), ""]

        sections += ["### Отзывы (собранные)", "", _reviews_block(reviews if isinstance(reviews, list) else []), "", "---", ""]

    return "\n".join(sections).strip() + "\n"


def write_prompt_file(output_dir: str, query: str, places: list[dict[str, Any]]) -> str:
    path = Path(output_dir) / "PROMPT.md"
    path.write_text(build_prompt_md(query, places), encoding="utf-8")
    return str(path)
