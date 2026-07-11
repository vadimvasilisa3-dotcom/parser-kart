"""Нормализация ссылок Яндекс.Карт."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

ORG_URL_RE = re.compile(r"yandex\.(ru|com)/maps/org/", re.I)
MAPS_HOST_RE = re.compile(r"https?://(?:[a-z0-9-]*\.)?yandex\.(?:ru|com)/maps", re.I)
SHORT_MAPS_RE = re.compile(r"/maps/-/([A-Za-z0-9_-]+)", re.I)
OID_RE = re.compile(r"[?&]oid=(\d+)", re.I)
ORG_NUMERIC_RE = re.compile(r"/maps/org/(?:[^/]+/)?(\d+)", re.I)

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _canonical_maps_host(url: str) -> str:
    """maps.yandex.ru / yandex.com → yandex.ru/maps."""
    clean = url.strip()
    clean = re.sub(
        r"https?://maps\.yandex\.(?:ru|com)",
        "https://yandex.ru/maps",
        clean,
        flags=re.I,
    )
    clean = re.sub(r"https?://yandex\.com/maps", "https://yandex.ru/maps", clean, flags=re.I)
    return clean


YMAPS_BM_OID_RE = re.compile(r"ymapsbm1://org\?oid=(\d+)", re.I)
POI_OID_IN_URI_RE = re.compile(r"org\?oid=(\d+)", re.I)


def _extract_oid_from_poi(url: str) -> str:
    """oid из mode=poi и poi[uri]=ymapsbm1://org?oid=… (в т.ч. URL-encoded)."""
    if not url:
        return ""
    decoded = unquote(url)
    m = YMAPS_BM_OID_RE.search(decoded)
    if m:
        return m.group(1)
    parsed = urlparse(decoded)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    for values in qs.values():
        for value in values:
            text = unquote(value or "")
            m = YMAPS_BM_OID_RE.search(text) or POI_OID_IN_URI_RE.search(text)
            if m:
                return m.group(1)
    # fallback: oid где угодно в строке после ymapsbm
    m = POI_OID_IN_URI_RE.search(decoded)
    if m and "ymapsbm" in decoded.lower():
        return m.group(1)
    return ""


def _extract_oid(url: str) -> str:
    m = OID_RE.search(url)
    if m:
        return m.group(1)
    parsed = urlparse(url)
    for key in ("oid", "ol"):
        values = parse_qs(parsed.query).get(key) or []
        for value in values:
            if value.isdigit():
                return value
    poi_oid = _extract_oid_from_poi(url)
    if poi_oid:
        return poi_oid
    return ""


def has_numeric_org_id(url: str) -> bool:
    return bool(ORG_NUMERIC_RE.search(url or ""))


def is_maps_url(url: str) -> bool:
    return bool(url and MAPS_HOST_RE.search(url.strip()))


def is_org_url(url: str) -> bool:
    """Проверка, что ссылка похожа на карточку организации (до редиректа)."""
    if not url:
        return False
    clean = _canonical_maps_host(url.strip())
    if ORG_URL_RE.search(clean):
        return True
    if _extract_oid(clean):
        return True
    if SHORT_MAPS_RE.search(clean):
        return True
    if is_maps_url(clean) and _extract_oid_from_poi(clean):
        return True
    return False


def normalize_org_url(url: str) -> str:
    """Приводит ссылку галереи/отзывов/oid к основной странице организации."""
    if not url:
        return ""
    clean = _canonical_maps_host(url.strip())

    oid = _extract_oid(clean)
    if oid:
        return f"https://yandex.ru/maps/org/{oid}/"

    path = clean.split("?")[0].split("#")[0]
    path = path.replace("/gallery/", "/")
    path = re.sub(r"/gallery$", "/", path)
    path = re.sub(r"/reviews/?$", "/", path)

    m = re.search(r"(https?://[^/]+/maps/org/\d+)", path, re.I)
    if m:
        return m.group(1).rstrip("/") + "/"

    m = re.search(r"(https?://[^/]+/maps/org/[^/]+/\d+)", path, re.I)
    if m:
        return m.group(1).rstrip("/") + "/"

    m = re.search(r"(https?://[^/]+/maps/org/[^/]+)", path, re.I)
    if m:
        return m.group(1).rstrip("/") + "/"

    if SHORT_MAPS_RE.search(path):
        return path.rstrip("/") + "/"

    return path.rstrip("/") + "/"


def resolve_org_url(url: str, timeout: int = 20) -> str:
    """
    Нормализует ссылку и при необходимости следует HTTP-редиректам
    (короткие ссылки /maps/-/…, share-ссылки).
    """
    normalized = normalize_org_url(url)
    if has_numeric_org_id(normalized):
        return normalized

    try:
        response = requests.get(
            url.strip(),
            allow_redirects=True,
            timeout=timeout,
            headers=_HTTP_HEADERS,
        )
        resolved = normalize_org_url(response.url)
        if has_numeric_org_id(resolved):
            return resolved
    except requests.RequestException:
        pass

    return normalized


def org_key_from_url(url: str) -> str:
    if not url:
        return ""
    clean = unquote(url.split("?")[0].split("#")[0].rstrip("/"))
    m = re.search(r"/org/[^/]+/(\d+)", clean, re.I)
    if m:
        return m.group(1)
    m = re.search(r"/org/(\d+)", clean, re.I)
    if m:
        return m.group(1)
    m = re.search(r"/org/([^/]+)", clean, re.I)
    if m:
        slug = m.group(1).lower()
        if slug not in ("-", "_"):
            return slug
    path = urlparse(clean).path.strip("/")
    return path or clean
