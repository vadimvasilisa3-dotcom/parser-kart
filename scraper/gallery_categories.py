"""Разделы галереи Яндекс.Карт для сбора фото."""
from __future__ import annotations

GALLERY_SECTIONS: list[dict[str, object]] = [
    {
        "slug": "uslugi",
        "title": "Услуги",
        "labels": ("услуги", "услуга", "services", "работы", "портфолио", "мастера"),
    },
    {
        "slug": "snaruzhi",
        "title": "Снаружи",
        "labels": ("снаружи", "фасад", "экстерьер", "outside", "exterior", "здание"),
    },
    {
        "slug": "vnutri",
        "title": "Внутри",
        "labels": ("внутри", "интерьер", "inside", "interior", "зал"),
    },
    {
        "slug": "vhod",
        "title": "Вход",
        "labels": ("вход", "entrance", "входная", "дверь", "вывеска"),
    },
]

GALLERY_SECTION_SLUGS: tuple[str, ...] = tuple(s["slug"] for s in GALLERY_SECTIONS)

GALLERY_CATEGORY_SELECTORS: tuple[str, ...] = (
    ".business-photos-view__category",
    ".orgpage-photos-view__category",
    ".business-photos-view__categories-item",
    ".orgpage-photos-view__categories-item",
    ".business-gallery-category-view__item",
    ".gallery-categories__item",
    ".gallery-category-view__item",
    "[class*='photos-view'][class*='category']",
    ".tabs-view__tab",
    "button[class*='category']",
)


def match_category_slug(label: str) -> str | None:
    text = (label or "").strip().lower().replace("ё", "е")
    if not text:
        return None
    for section in GALLERY_SECTIONS:
        for needle in section["labels"]:  # type: ignore[union-attr]
            n = str(needle).lower().replace("ё", "е")
            if n == text or n in text or text in n:
                return str(section["slug"])
    return None


def section_title(slug: str) -> str:
    for section in GALLERY_SECTIONS:
        if section["slug"] == slug:
            return str(section["title"])
    return slug
