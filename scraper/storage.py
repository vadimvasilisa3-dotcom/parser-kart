import os
import json
import csv
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from .decorators import log_execution, logger

class DataManager:
    """
    Manages data storage and export.
    Session layout:
      {session}/
        places_data.xlsx, places_data.json, PROMPT.md
        orgs/
          001_Salon_Name/
            profile.json
            photos/
            reviews/  (reviews.json + 01_author.txt …)
            menu/     (menu.json + menu.txt)
    """

    PLACE_SUBDIRS = ("photos", "reviews", "menu")
    PHOTO_CATEGORY_DIRS = ("uslugi", "snaruzhi", "vnutri", "vhod")
    
    def __init__(self, base_dir: str = "data/output"):
        self.base_dir = base_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_session_dir = ""

    @log_execution
    def setup_session_directory(self, query: str) -> str:
        """Creates a dedicated directory for the current scraping session."""
        safe_query = "".join(c for c in query if c.isalnum() or c in (' ', '-', '_')).strip()
        folder_name = f"{self.timestamp}_{safe_query}"
        self.current_session_dir = os.path.join(self.base_dir, folder_name)
        
        os.makedirs(self.current_session_dir, exist_ok=True)
        self.write_session_readme()
        return self.current_session_dir

    def write_session_readme(self) -> None:
        if not self.current_session_dir:
            return
        text = """# Структура выгрузки парсера карт

places_data.xlsx / places_data.json — сводная таблица
PROMPT.md — данные по организациям (факты, услуги, отзывы)
AGENT_WEBSITE.md — системный промпт для агента-сайтбилдера (палитра по фото!)

orgs/
  001_Название_салона/
    profile.json   — карточка: адрес, телефон, рейтинг, ссылка
    photos/        — по разделам: uslugi/, snaruzhi/, vnutri/, vhod/ (5–10 фото каждый)
    reviews/       — reviews.json + отдельные .txt по каждому отзыву
    menu/          — menu.json + menu.txt (услуги и цены)
  002_…/
"""
        try:
            with open(os.path.join(self.current_session_dir, "README.txt"), "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            logger.debug(f"README write failed: {e}")

    @log_execution
    def create_place_folder(self, place_name: str, index: int) -> str:
        """Creates org folder with photos/, reviews/, menu/ subdirs."""
        if not self.current_session_dir:
            raise ValueError("Session directory not set. Call setup_session_directory first.")

        safe_name = "".join(c for c in place_name if c.isalnum() or c in (" ", "-", "_")).strip()[:50]
        safe_name = safe_name.replace(" ", "_") or "place"
        folder_name = f"{index:03d}_{safe_name}"
        place_path = os.path.join(self.current_session_dir, "orgs", folder_name)

        for sub in self.PLACE_SUBDIRS:
            os.makedirs(os.path.join(place_path, sub), exist_ok=True)
        for cat in self.PHOTO_CATEGORY_DIRS:
            os.makedirs(os.path.join(place_path, "photos", cat), exist_ok=True)

        return place_path

    @staticmethod
    def _safe_filename_part(text: str, max_len: int = 30) -> str:
        part = "".join(c for c in text if c.isalnum() or c in ("-", "_")).strip()
        return (part or "item")[:max_len]

    @log_execution
    def save_place_bundle(self, place_path: str, data: Dict[str, Any]) -> None:
        """Saves profile, reviews and menu into org subfolders."""
        if not place_path:
            return

        profile = {k: v for k, v in data.items() if k not in ("photos", "reviews", "menu")}
        profile["photos_dir"] = "photos"
        profile["photos_by_category"] = data.get("photos_by_category") or {}
        profile["reviews_dir"] = "reviews"
        profile["menu_dir"] = "menu"
        try:
            with open(os.path.join(place_path, "profile.json"), "w", encoding="utf-8") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save profile.json: {e}")

        reviews = data.get("reviews") or []
        if isinstance(reviews, list) and reviews:
            reviews_dir = os.path.join(place_path, "reviews")
            try:
                with open(os.path.join(reviews_dir, "reviews.json"), "w", encoding="utf-8") as f:
                    json.dump(reviews, f, ensure_ascii=False, indent=2)
                for i, r in enumerate(reviews, 1):
                    if not isinstance(r, dict):
                        continue
                    author = r.get("author") or "anon"
                    rating = r.get("rating") or "—"
                    date = r.get("date") or ""
                    text = (r.get("text") or "").strip()
                    fname = f"{i:02d}_{self._safe_filename_part(author)}.txt"
                    body = f"Автор: {author}\nРейтинг: {rating}\nДата: {date}\n\n{text}\n"
                    with open(os.path.join(reviews_dir, fname), "w", encoding="utf-8") as f:
                        f.write(body)
            except Exception as e:
                logger.error(f"Failed to save reviews: {e}")

        menu = data.get("menu") or []
        if isinstance(menu, list) and menu:
            menu_dir = os.path.join(place_path, "menu")
            try:
                with open(os.path.join(menu_dir, "menu.json"), "w", encoding="utf-8") as f:
                    json.dump(menu, f, ensure_ascii=False, indent=2)
                lines = []
                for m in menu:
                    if not isinstance(m, dict):
                        continue
                    cat = m.get("category") or ""
                    name = m.get("name") or ""
                    price = m.get("price") or ""
                    line = f"[{cat}] {name} — {price}" if cat else f"{name} — {price}"
                    lines.append(line.strip(" —"))
                with open(os.path.join(menu_dir, "menu.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + ("\n" if lines else ""))
            except Exception as e:
                logger.error(f"Failed to save menu: {e}")

    @log_execution
    def save_json(self, data: List[Dict[str, Any]], filename: str = "places_data.json") -> str:
        """Saves the extracted data list to a JSON file."""
        if not self.current_session_dir:
            return ""
            
        filepath = os.path.join(self.current_session_dir, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 JSON saved: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save JSON: {e}")
            return ""

    @log_execution
    def export_to_csv(self, data: List[Dict[str, Any]], filename: str = "places_data.csv") -> str:
        """
        Exports flat data to CSV.
        Handles nested structures by converting them to string representations or flattening.
        """
        if not self.current_session_dir or not data:
            return ""

        filepath = os.path.join(self.current_session_dir, filename)
        
        try:
            # Flattening basic nested dicts for better CSV readability
            flat_data = []
            for item in data:
                flat_item = item.copy()
                
                # Flatten features
                if 'features' in flat_item and isinstance(flat_item['features'], dict):
                    for k, v in flat_item['features'].items():
                        # Create a safe column name
                        safe_key = "feat_" + "".join(c for c in k if c.isalnum() or c == '_')
                        flat_item[safe_key] = v
                    del flat_item['features'] # Remove the original dict

                # Convert complex lists/dicts to string for CSV
                if 'photos' in flat_item:
                    flat_item['photos_count'] = len(flat_item['photos'])
                    # Keep the first photo path if available
                    if flat_item['photos']:
                        flat_item['primary_photo'] = flat_item['photos'][0]
                    del flat_item['photos'] # Don't dump huge photo arrays to CSV
                
                if 'reviews' in flat_item:
                    flat_item['reviews_count'] = len(flat_item['reviews'])
                    # Keep top review snippet
                    if flat_item['reviews']:
                        flat_item['top_review'] = flat_item['reviews'][0].get('text', '')[:200]
                    del flat_item['reviews']
                
                # Join lists like working_hours
                if 'working_hours' in flat_item and isinstance(flat_item['working_hours'], list):
                    flat_item['working_hours'] = "; ".join(flat_item['working_hours'])

                # Join social_media
                if 'social_media' in flat_item and isinstance(flat_item['social_media'], list):
                    flat_item['social_media'] = "; ".join(flat_item['social_media'])
                    
                flat_data.append(flat_item)

            df = pd.DataFrame(flat_data)
            df.to_csv(filepath, index=False, encoding='utf-8-sig') # utf-8-sig for Excel compatibility
            logger.info(f"📊 CSV exported: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            return ""

    @log_execution
    def export_to_excel(self, data: List[Dict[str, Any]], filename: str = "places_data.xlsx") -> str:
        """
        Exports flat data to Excel (.xlsx).
        """
        if not self.current_session_dir or not data:
            return ""

        filepath = os.path.join(self.current_session_dir, filename)
        
        try:
            # Reuse logic from export_to_csv to flatten data
            # We can refactor the flattening logic into a helper if we want to be clean,
            # but for now I'll duplicate the flattening or (better) create a DataFrame and use it.
            
            # Let's create a temporary CSV first? No, just create DF directly.
            
            flat_data = []
            for item in data:
                flat_item = item.copy()
                
                if 'features' in flat_item and isinstance(flat_item['features'], dict):
                    for k, v in flat_item['features'].items():
                        safe_key = "feat_" + "".join(c for c in k if c.isalnum() or c == '_')
                        flat_item[safe_key] = v
                    del flat_item['features']

                if 'photos' in flat_item:
                    flat_item['photos_count'] = len(flat_item['photos'])
                    if flat_item['photos']:
                        flat_item['primary_photo'] = flat_item['photos'][0]
                    del flat_item['photos']
                
                if 'reviews' in flat_item:
                    flat_item['reviews_count'] = len(flat_item['reviews'])
                    if flat_item['reviews']:
                        flat_item['top_review'] = flat_item['reviews'][0].get('text', '')[:200]
                    del flat_item['reviews']
                
                if 'working_hours' in flat_item and isinstance(flat_item['working_hours'], list):
                    flat_item['working_hours'] = "; ".join(flat_item['working_hours'])

                if 'social_media' in flat_item and isinstance(flat_item['social_media'], list):
                    flat_item['social_media'] = "; ".join(flat_item['social_media'])
                    
                flat_data.append(flat_item)

            df = pd.DataFrame(flat_data)
            df.to_excel(filepath, index=False) 
            logger.info(f"📊 Excel exported: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to export Excel: {e}")
            return ""

    @log_execution
    def save_to_sqlite(self, data: List[Dict[str, Any]], filename: str = "places_data.db") -> str:
        """Saves flattened data to a SQLite database."""
        if not self.current_session_dir or not data:
            return ""

        filepath = os.path.join(self.current_session_dir, filename)
        
        try:
            import sqlite3
            
            # Prepare flat data similar to CSV export
            flat_data = []
            for item in data:
                flat_item = item.copy()
                
                # Flatten features (store as JSON string or text for SQLite?)
                # For simplicity, let's keep them somewhat structured or just stringify the complex ones
                # But to make it compatible with common tools, flattening/stringifying is safer
                
                if 'features' in flat_item and isinstance(flat_item['features'], dict):
                     flat_item['features'] = json.dumps(flat_item['features'], ensure_ascii=False)

                if 'photos' in flat_item:
                    flat_item['photos_count'] = len(flat_item['photos'])
                    if flat_item['photos']:
                        flat_item['primary_photo'] = flat_item['photos'][0]
                    # store full list as json string
                    flat_item['photos'] = json.dumps(flat_item['photos'], ensure_ascii=False)
                
                if 'reviews' in flat_item:
                    flat_item['reviews_count'] = len(flat_item['reviews'])
                    if flat_item['reviews']:
                        flat_item['top_review'] = flat_item['reviews'][0].get('text', '')[:200]
                    # store full reviews as json string
                    flat_item['reviews'] = json.dumps(flat_item['reviews'], ensure_ascii=False)
                
                if 'working_hours' in flat_item and isinstance(flat_item['working_hours'], list):
                    flat_item['working_hours'] = "; ".join(flat_item['working_hours'])

                if 'social_media' in flat_item and isinstance(flat_item['social_media'], list):
                    flat_item['social_media'] = "; ".join(flat_item['social_media'])
                    
                flat_data.append(flat_item)

            df = pd.DataFrame(flat_data)
            
            with sqlite3.connect(filepath) as conn:
                df.to_sql('places', conn, if_exists='replace', index=False)
                
            logger.info(f"🗄️ SQLite saved: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save SQLite: {e}")
            return ""


