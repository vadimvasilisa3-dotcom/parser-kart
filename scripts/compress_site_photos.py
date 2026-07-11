# -*- coding: utf-8 -*-
"""Compress site photos: resize to max 1600px long side, fit size budgets.

Usage: py scripts/compress_site_photos.py sites/only-ya/assets/photos
Hero-listed files get a 250KB budget, the rest 150KB.
"""
import io
import sys
from pathlib import Path

from PIL import Image, ImageOps

HERO_FILES = {"photo_13.jpg", "photo_5.jpg", "photo_9.jpg", "photo_17.jpg", "photo_1.jpg"}
MAX_SIDE = 1600


def compress(path: Path, budget_kb: int) -> None:
    original_kb = path.stat().st_size // 1024
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)

    for quality in (85, 80, 75, 70, 65, 60):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= budget_kb * 1024:
            break

    new_kb = buf.tell() // 1024
    if new_kb < original_kb:
        path.write_bytes(buf.getvalue())
        print(f"{path.name}: {original_kb} KB -> {new_kb} KB (q={quality})")
    else:
        print(f"{path.name}: {original_kb} KB kept (already optimal)")


def main() -> None:
    folder = Path(sys.argv[1])
    for f in sorted(folder.glob("*.jpg")):
        budget = 250 if f.name in HERO_FILES else 150
        compress(f, budget)


if __name__ == "__main__":
    main()
