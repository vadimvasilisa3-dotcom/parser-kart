#!/usr/bin/env python3
"""Копирует фото из orgs/NNN_Название/photos/ в sites/<slug>/assets/photos/."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sync(org_folder: str, site_slug: str) -> int:
    src = ROOT / org_folder.replace("\\", "/").lstrip("/")
    if not src.is_dir():
        src = ROOT / "orgs" / Path(org_folder).name
    photos_src = src / "photos"
    if not photos_src.is_dir():
        raise FileNotFoundError(f"Нет папки с фото: {photos_src}")

    dest = ROOT / "sites" / site_slug / "assets" / "photos"
    dest.mkdir(parents=True, exist_ok=True)

    count = 0
    for path in sorted(photos_src.rglob("*.jpg")):
        rel = path.relative_to(photos_src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
    for path in sorted(photos_src.rglob("*.jpeg")):
        rel = path.relative_to(photos_src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
    return count


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--org", default="orgs/001_Только_Я", help="Папка организации")
    p.add_argument("--site", default="only-ya", help="Slug в sites/")
    args = p.parse_args()
    try:
        n = sync(args.org, args.site)
        print(f"Скопировано {n} фото → sites/{args.site}/assets/photos/")
    except FileNotFoundError as e:
        print(f"Ошибка: {e}")
        print("Сначала скачайте ZIP из парсера (с включёнными фото) и распакуйте orgs/.")


if __name__ == "__main__":
    main()
