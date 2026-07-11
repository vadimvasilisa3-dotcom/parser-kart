"""Дедупликация организаций между запусками сбора."""
from __future__ import annotations

from scraper.url_utils import org_key_from_url


def build_scope_key(category: str | None, city: str | None, custom_query: str | None) -> str:
    parts = [p.strip().lower() for p in (category, city, custom_query) if p and str(p).strip()]
    return "|".join(parts) if parts else "all"


__all__ = ["build_scope_key", "org_key_from_url"]
