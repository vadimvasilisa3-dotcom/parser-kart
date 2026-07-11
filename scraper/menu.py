"""Парсинг услуг и цен с вкладки «Меню/Цены» Яндекс.Карт."""
from __future__ import annotations

import re
from typing import Any

MENU_TAB_KEYWORDS = (
    "меню",
    "цены",
    "товары",
    "услуги",
    "прайс",
    "price",
    "menu",
    "services",
)

MENU_CONTAINER_SELECTORS = (
    ".business-full-items-grouped-view__content",
    ".business-prices-view",
    ".related-product-list-view",
    ".business-card-view__main",
)

CATEGORY_SELECTOR = ".business-full-items-grouped-view__category"
ITEM_SELECTOR = ".business-full-items-grouped-view__item"


def with_tab(url: str, tab: str) -> str:
    if "/gallery/" in url:
        url = url.replace("/gallery/", "/")
    if "tab=" in url:
        return re.sub(r"tab=[^&]+", f"tab={tab}", url)
    if "?" in url:
        return f"{url}&tab={tab}"
    return f"{url.rstrip('/')}/?tab={tab}"


def format_menu_line(item: dict[str, Any]) -> str:
    name = (item.get("name") or "").strip()
    price = (item.get("price") or "").strip()
    category = (item.get("category") or "").strip()
    if not name:
        return ""
    line = f"{name} — {price}" if price else name
    return f"[{category}] {line}" if category else line


def menu_to_services(menu: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    services: list[str] = []
    prices: list[str] = []
    for item in menu:
        line = format_menu_line(item)
        if line:
            services.append(line)
        price = (item.get("price") or "").strip()
        if price:
            prices.append(price)
    return services, prices
