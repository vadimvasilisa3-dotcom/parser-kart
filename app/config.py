import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"
DB_PATH = DATA_DIR / "parser_kart.db"
STATIC_DIR = ROOT / "static"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
MAX_PHOTOS_DEFAULT = int(os.getenv("MAX_PHOTOS", "10"))
MAX_PHOTOS_PER_CATEGORY_DEFAULT = int(os.getenv("MAX_PHOTOS_PER_CATEGORY", "10"))
MAX_REVIEWS_DEFAULT = int(os.getenv("MAX_REVIEWS", "15"))
MAX_MENU_ITEMS_DEFAULT = int(os.getenv("MAX_MENU_ITEMS", "100"))
SCRAPE_REVIEWS = os.getenv("SCRAPE_REVIEWS", "true").lower() == "true"
SCRAPE_PHOTOS = os.getenv("SCRAPE_PHOTOS", "true").lower() == "true"
SCRAPE_MENU = os.getenv("SCRAPE_MENU", "true").lower() == "true"
AUTO_CLEANUP_AFTER_ZIP = os.getenv("AUTO_CLEANUP_AFTER_ZIP", "true").lower() == "true"

for path in (DATA_DIR, OUTPUT_DIR):
    path.mkdir(parents=True, exist_ok=True)
