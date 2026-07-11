import re
import time
import os
import sys
import requests
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

from .decorators import log_execution, handle_errors, logger
from .gallery_categories import (
    GALLERY_CATEGORY_SELECTORS,
    GALLERY_SECTIONS,
    GALLERY_SECTION_SLUGS,
    match_category_slug,
    section_title,
)
from .menu import CATEGORY_SELECTOR, ITEM_SELECTOR, MENU_CONTAINER_SELECTORS, MENU_TAB_KEYWORDS, with_tab
from .storage import DataManager
from .url_utils import org_key_from_url

class YandexMapsScraper:
    """
    Main class for scraping Yandex Maps.
    """

    def __init__(self, headless: bool = False, max_results: int = 10, scrape_photos: bool = True, scrape_reviews: bool = True, scrape_menu: bool = True, photo_format: str = "jpg", max_photos: int = 5, max_reviews: int = 10, max_menu_items: int = 100, browser_type: str = "chrome"):
        self.headless = headless
        self.max_results = max_results
        self.scrape_photos = scrape_photos
        self.scrape_reviews = scrape_reviews
        self.scrape_menu = scrape_menu
        self.photo_format = photo_format.lower()
        self.max_photos = max_photos
        self.max_reviews = max_reviews
        self.max_menu_items = max_menu_items
        self.browser_type = browser_type.lower()
        self.driver: Optional[webdriver.Chrome] = None
        self.on_progress = None # Callback function for progress updates
        self.wait: Optional[WebDriverWait] = None
        self.data_manager = DataManager()
        self.session = requests.Session()
        
        # Configure requests session
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    @log_execution
    def setup_driver(self):
        """Initializes the WebDriver based on the selected browser."""
        if self.browser_type == "chrome":
            options = webdriver.ChromeOptions()
            if self.headless:
                options.add_argument("--headless")
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--start-maximized")
            
            # Mac OS specific: Check common Chrome binary locations
            if sys.platform == "darwin":
                binary_locations = [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Chromium.app/Contents/MacOS/Chromium",
                    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
                    "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
                    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                    os.path.expanduser("~/Applications/Chromium.app/Contents/MacOS/Chromium")
                ]
                chrome_found = False
                for loc in binary_locations:
                    if os.path.exists(loc):
                        options.binary_location = loc
                        logger.info(f"Found Chrome at: {loc}")
                        chrome_found = True
                        break
                
                if not chrome_found:
                    logger.warning("Chrome binary not found in standard locations. Checked:")
                    for loc in binary_locations:
                        logger.warning(f"  - {loc}")
                    logger.warning("Please ensure Google Chrome is installed, or the scraper may fail.")
            
            import tempfile
            options.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
            
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            
        elif self.browser_type == "firefox":
            from webdriver_manager.firefox import GeckoDriverManager
            options = webdriver.FirefoxOptions()
            if self.headless:
                options.add_argument("--headless")
            
            options.add_argument("--width=1920")
            options.add_argument("--height=1080")
            
            service = Service(GeckoDriverManager().install())
            self.driver = webdriver.Firefox(service=service, options=options)
            
        elif self.browser_type == "edge":
            from webdriver_manager.microsoft import EdgeChromiumDriverManager
            options = webdriver.EdgeOptions()
            if self.headless:
                options.add_argument("--headless")
            options.add_argument("--start-maximized")
            
            service = Service(EdgeChromiumDriverManager().install())
            self.driver = webdriver.Edge(service=service, options=options)
            
        elif self.browser_type == "safari":
            if sys.platform != "darwin":
                raise RuntimeError("Safari is only available on macOS.")
            
            options = webdriver.SafariOptions()
            # Safari doesn't support headless mode in the same way via options generally
            # But we can try to minimize interference
            self.driver = webdriver.Safari(options=options)
            if self.headless:
                logger.warning("Headless mode not fully supported for Safari. Running visible.")
            self.driver.maximize_window()
            
        else:
            raise ValueError(f"Unsupported browser: {self.browser_type}")

        self.wait = WebDriverWait(self.driver, 10)
        logger.info(f"🖥️  {self.browser_type.title()} WebDriver initialized")

    @log_execution
    def run(self, query: str):
        """Main execution flow."""
        try:
            self.setup_driver()
            self.data_manager.setup_session_directory(query)
            
            self.driver.get("https://yandex.ru/maps")
            logger.info(f"🔍 Searching for: {query}")
            
            self._perform_search(query)
            
            # Scroll and collect links to all places first
            if self.on_progress:
                self.on_progress(0, self.max_results, "Scrolling and collecting links...")
                
            place_links = self._scroll_and_collect_results()
            total_links = len(place_links)
            logger.info(f"📍 Found {total_links} places to process")
            
            extracted_data = []
            
            for i, link in enumerate(place_links):
                msg = f"Processing place {i+1}/{total_links}"
                logger.info(f"🏢 {msg}...")
                
                if self.on_progress:
                    self.on_progress(i, total_links, msg)
                
                try:
                    # Normalize URL to ensure we start at the main view
                    main_url = link
                    if "/gallery/" in main_url:
                        main_url = main_url.replace("/gallery/", "/")
                    if "tab=gallery" in main_url:
                        import re
                        main_url = re.sub(r'tab=gallery&?', '', main_url)
                    
                    self.driver.get(main_url)
                    time.sleep(3) # Wait for page load
                    
                    place_data = self._extract_details(i + 1, query)
                    if place_data:
                        extracted_data.append(place_data)
                        
                except Exception as e:
                    logger.error(f"Error processing place {i+1}: {e}")
                    continue
            
            # Save final results
            if self.on_progress:
                self.on_progress(total_links, total_links, "Saving data...")

            # Add metadata to each record
            for item in extracted_data:
                item['search_query'] = query
                
            self.data_manager.save_json(extracted_data)
            self.data_manager.export_to_csv(extracted_data)
            self.data_manager.save_to_sqlite(extracted_data)
            self.data_manager.export_to_excel(extracted_data)
            
        except Exception as e:
            logger.critical(f"Critical failure: {e}")
        finally:
            if self.driver:
                self.driver.quit()

    def _perform_search(self, query: str):
        """Enters the query into the search box."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Wait a bit for page to fully load (especially for Safari)
                time.sleep(1)
                
                # Try multiple selectors for the search input
                search_input = self.wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "input.input__control, input[type='text']"
                )))
                
                # Retry logic for stale elements
                try:
                    search_input.clear()
                    search_input.send_keys(query)
                    search_input.send_keys(Keys.RETURN)
                except StaleElementReferenceException:
                    if attempt < max_retries - 1:
                        logger.debug(f"Stale element when typing query, retry {attempt + 1}/{max_retries}")
                        time.sleep(1)
                        continue
                    else:
                        raise
                
                # Wait for results container
                # Added robust check for StaleElementReferenceException which happens often in Safari
                try:
                    self.wait.until(EC.presence_of_element_located((
                        By.CSS_SELECTOR, ".search-list-view, .search-snippet-view"
                    )))
                except StaleElementReferenceException:
                    logger.debug("Stale element in search wait, retrying...")
                    time.sleep(1)
                    self.wait.until(EC.presence_of_element_located((
                        By.CSS_SELECTOR, ".search-list-view, .search-snippet-view"
                    )))
                    
                time.sleep(2)
                break  # Success, exit retry loop
                
            except TimeoutException:
                if attempt < max_retries - 1:
                    logger.warning(f"Search timeout, retry {attempt + 1}/{max_retries}")
                    time.sleep(2)
                else:
                    logger.error("Search box not found or results didn't load after retries.")
                    raise

    def _scroll_and_collect_results(
        self,
        skip_keys: set[str] | None = None,
        target: int | None = None,
    ) -> List[str]:
        """
        Scrolls the results list until enough NEW place links are loaded.
        skip_keys: org IDs already collected for this scope (dedupe).
        target: how many new links to return (defaults to max_results).
        """
        skip_keys = skip_keys or set()
        target = target or self.max_results
        logger.info(f"📜 Scrolling to load results (нужно новых: {target}, уже в базе: {len(skip_keys)})…")

        last_count = 0
        attempts = 0
        max_attempts = max(8, min(60, target // 5 + 10))

        ordered: list[str] = []
        seen_local: set[str] = set()

        def _fresh_count() -> int:
            return sum(1 for href in ordered if org_key_from_url(href) not in skip_keys)

        while True:
            elements = self.driver.find_elements(By.CSS_SELECTOR, ".search-snippet-view")
            current_count = len(elements)

            for el in elements:
                try:
                    href = None
                    for sel in (
                        ".search-snippet-view__link-overlay",
                        ".search-snippet-view__title-link",
                        "a.search-snippet-view__link-overlay",
                        ".search-snippet-view__body a",
                    ):
                        try:
                            link_el = el.find_element(By.CSS_SELECTOR, sel)
                            href = link_el.get_attribute("href")
                            if href:
                                break
                        except Exception:
                            continue
                    if not href:
                        continue
                    key = org_key_from_url(href)
                    if key in seen_local:
                        continue
                    seen_local.add(key)
                    ordered.append(href)
                except Exception:
                    continue

            fresh = _fresh_count()
            if fresh >= target:
                result = []
                for href in ordered:
                    if org_key_from_url(href) in skip_keys:
                        continue
                    result.append(href)
                    if len(result) >= target:
                        break
                logger.info(f"✅ Собрано {len(result)} новых ссылок (цель: {target})")
                return result

            if current_count == last_count:
                attempts += 1
                if attempts >= max_attempts:
                    result = [h for h in ordered if org_key_from_url(h) not in skip_keys][:target]
                    logger.warning(
                        f"⚠️ Выдача закончилась: {len(result)} новых из {target} "
                        f"(всего в списке: {len(ordered)})"
                    )
                    return result
            else:
                attempts = 0

            last_count = current_count
            logger.info(
                f"   Сниппетов: {current_count}, уникальных ссылок: {len(ordered)}, новых: {fresh}…"
            )

            try:
                if elements:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", elements[-1])
                    time.sleep(1.8)
                else:
                    break
            except Exception:
                break

        return [h for h in ordered if org_key_from_url(h) not in skip_keys][:target]

    def _dismiss_overlays(self) -> None:
        """Закрывает cookie-баннер и прочие перекрытия."""
        selectors = (
            "button[class*='cookie']",
            ".gdpr-popup-v2__button",
            ".button_view_cookie",
            "[data-testid='cookie-accept']",
            ".modal__close",
        )
        for sel in selectors:
            try:
                for btn in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    text = (btn.text or btn.get_attribute("textContent") or "").lower()
                    if not text or any(w in text for w in ("принять", "accept", "ok", "понятно", "согласен")):
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
            except Exception:
                continue

    def _wait_for_org_page(self, timeout: int = 15) -> bool:
        """Ждёт загрузки карточки организации (полная страница или боковая панель)."""
        if not self.wait:
            return False
        selectors = (
            ".orgpage-header-view__title",
            ".card-title-view__title",
            ".business-card-title-view__title",
            ".business-card-view",
            "meta[itemprop='name']",
            "h1",
        )
        combined = ", ".join(selectors)
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, combined)))
            return True
        except TimeoutException:
            return False

    def _scroll_gallery(self) -> None:
        """Прокрутка галереи для подгрузки lazy-load фото."""
        try:
            for _ in range(12):
                self.driver.execute_script("window.scrollBy(0, 900);")
                time.sleep(0.6)
            for sel in (
                ".scroll__container",
                ".media-gallery",
                ".business-photos-view",
                ".orgpage-photos-view",
                ".gallery-page",
            ):
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    try:
                        self.driver.execute_script(
                            "arguments[0].scrollTop = arguments[0].scrollHeight;", el
                        )
                        time.sleep(0.8)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Gallery scroll: {e}")

    @handle_errors(default_return=None)
    def _extract_details(self, index: int, query: str) -> Dict[str, Any]:
        """Extracts comprehensive details from the currently opened place panel."""
        
        # Wait for the header to be visible (confirmation that details loaded)
        if not self._wait_for_org_page(timeout=12):
            logger.warning("Details panel didn't load in time — trying partial extraction.")

        on_gallery = "/gallery/" in (self.driver.current_url or "")

        # На gallery-ссылке не переключаемся на «Обзор» до сбора фото
        if not on_gallery:
            self._switch_to_overview()
            self.driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(1)
            self.driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(1)

        # STEP 1: Get the name first (needed for folder creation)
        name = self._get_text([
            ".orgpage-header-view__title", 
            ".card-title-view__title", 
            "h1",
            ".business-card-title-view__title"
        ])
        if not name:
            name = self._get_attribute(["meta[itemprop='name']"], "content")
        if not name:
            logger.warning("Organization name not found on page.")
            return None

        # STEP 2: Extract category and description BEFORE navigating away
        # Category - look for links with /category/ in href
        category = ""
        try:
            category_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/category/']")
            categories = []
            for link in category_links:
                text = link.text.strip()
                if text and text not in categories:
                    categories.append(text)
            if categories:
                category = ", ".join(categories[:3])  # Limit to first 3 categories
        except Exception:
            pass
        
        # Fallback to other selectors
        if not category:
            category = self._get_text([
                ".orgpage-header-view__categories a",
                ".business-categories-view__category",
                ".business-card-title-view__category",
                ".card-title-view__category"
            ])

        # Description - visible in the header area
        description = self._get_text([
            ".orgpage-header-view__description",
            ".business-card-title-view__description",
            ".card-title-view__description",
            ".business-card-title-view__subtitle",
            ".orgpage-header-view__subtitle"
        ])

        # STEP 3: Create folder; detect photos on card before optional download
        place_folder = self.data_manager.create_place_folder(name or f"Place_{index}", index)
        has_photos = self._card_has_photos()

        photos = []
        photos_by_category: dict[str, list[str]] = {}
        if self.scrape_photos:
            if on_gallery:
                logger.info("Already on gallery page — collecting photos…")
                self._scroll_gallery()
            else:
                # STEP 4: Navigate to gallery for photos
                try:
                    photo_gallery_buttons = self.driver.find_elements(By.CSS_SELECTOR, ".business-photos-view__more, .business-card-title-view__photo, .business-photos-view")
                    if photo_gallery_buttons:
                        logger.info("Opening photo gallery...")
                        self.driver.execute_script("arguments[0].click();", photo_gallery_buttons[0])
                        time.sleep(3.5)
                except Exception as e:
                    logger.debug(f"Failed to open photo gallery: {e}")

                # Try navigating to /gallery/ URL if images not found
                if not self.driver.find_elements(By.CSS_SELECTOR, ".media-wrapper__media"):
                    current_url = self.driver.current_url
                    if "/gallery/" not in current_url:
                        try:
                            if "?" in current_url:
                                base, qry = current_url.split("?", 1)
                                gallery_url = f"{base}gallery/?{qry}"
                            else:
                                gallery_url = f"{current_url.rstrip('/')}/gallery/"
                            
                            logger.info(f"Navigating to gallery URL: {gallery_url}")
                            self.driver.get(gallery_url)
                            time.sleep(3.5)
                        except Exception as e:
                            logger.debug(f"Failed to navigate to gallery URL: {e}")

                self._scroll_gallery()

            # STEP 4: Download photos by gallery sections
            photos, photos_by_category = self._extract_photos_by_categories(place_folder)
            if photos:
                has_photos = True

            # STEP 6: Go back to overview for text extraction
            if "/gallery/" in self.driver.current_url:
                main_url = self.driver.current_url.replace("/gallery/", "/")
                self.driver.get(main_url)
                time.sleep(2)
                self._switch_to_overview()
                self.driver.execute_script("window.scrollBy(0, 1000);")
                time.sleep(1)
        elif on_gallery:
            main_url = self.driver.current_url.replace("/gallery/", "/")
            self.driver.get(main_url)
            time.sleep(2)
            self._switch_to_overview()

        # STEP 7: Extract remaining text data (address, phone, etc.)
        # Features
        features = {}
        try:
            bool_features = self.driver.find_elements(By.CSS_SELECTOR, ".business-features-view__bool-text")
            for bf in bool_features:
                text = bf.text.strip()
                if text:
                    features[text] = True
            
            valued_features = self.driver.find_elements(By.CSS_SELECTOR, ".business-features-view__valued")
            for vf in valued_features:
                try:
                    title = vf.find_element(By.CSS_SELECTOR, ".business-features-view__valued-title").text.strip().rstrip(":")
                    value = vf.find_element(By.CSS_SELECTOR, ".business-features-view__valued-value").text.strip()
                    if title and value:
                        features[title] = value
                except:
                    continue
        except Exception as e:
            logger.debug(f"Features extraction error: {e}")
        
        # Address
        address = self._get_attribute(["meta[itemprop='address']"], "content")
        if not address:
            address = self._get_text([
                ".business-contacts-view__address-link",
                ".business-contacts-view__address",
                "[data-id='address']"
            ])

        # Website
        website = self._get_attribute([".business-urls-view__link", "a[itemprop='url']"], "href")
        if not website:
            website = self._get_text([".business-urls-view__text"])

        # Phone
        phone = self._get_text([
            "span[itemprop='telephone']",
            ".card-phones-view__number",
            ".business-phone-view__number"
        ])

        # Working Hours
        working_hours = self._get_all_attributes("meta[itemprop='openingHours']", "content")
        if not working_hours:
            working_hours_text = self._get_text([".business-working-status-view__text"])
            if working_hours_text:
                working_hours = [working_hours_text]

        # Social media
        social_media = self._extract_social_links()

        main_link = self.driver.current_url
        if "/gallery/" in main_link:
            main_link = main_link.replace("/gallery/", "/")

        menu_items: List[Dict[str, Any]] = []
        reviews_count = self._extract_reviews_count()
        has_reviews = self._has_reviews(reviews_count)
        if self.scrape_menu:
            menu_items = self._extract_menu_services(main_link)
            has_menu = len(menu_items) > 0
        else:
            has_menu = self._card_has_menu(main_link)

        # STEP 7: Build data dict
        data = {
            "id": index,
            "name": name,
            "category": category,
            "description": description,
            "features": features,
            "address": address,
            "website": website,
            "phone": phone,
            "rating": self._extract_rating(),
            "reviews_count": reviews_count,
            "has_reviews": has_reviews,
            "has_photos": has_photos,
            "has_menu": has_menu,
            "working_hours": working_hours,
            "folder_path": place_folder,
            "link": main_link,
            "social_media": social_media,
            "photos": photos,
            "photos_by_category": photos_by_category if self.scrape_photos else {},
            "menu": menu_items,
        }
        
        # STEP 8: Extract reviews (requires tab switch)
        if self.scrape_reviews:
            data["reviews"] = self._extract_reviews()
        else:
            data["reviews"] = []

        self.data_manager.save_place_bundle(place_folder, data)

        return data

    def _switch_to_tab_by_keywords(self, keywords: tuple[str, ...]) -> bool:
        try:
            tabs = self.driver.find_elements(
                By.XPATH,
                "//div[contains(@class, 'tabs-view__tab')] | //button[contains(@class, 'tabs-view__tab')]",
            )
            for tab in tabs:
                text = (tab.text or tab.get_attribute("textContent") or "").strip().lower()
                if any(kw in text for kw in keywords):
                    if "_selected" not in (tab.get_attribute("class") or ""):
                        self.driver.execute_script("arguments[0].click();", tab)
                        time.sleep(2)
                    return True
        except Exception as e:
            logger.debug(f"Tab switch failed: {e}")
        return False

    def _wait_for_menu_container(self) -> bool:
        combined = ", ".join(MENU_CONTAINER_SELECTORS)
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, combined)))
            return True
        except TimeoutException:
            return False

    def _expand_menu_categories(self) -> None:
        try:
            prev_count = -1
            for _ in range(15):
                categories = self.driver.find_elements(By.CSS_SELECTOR, CATEGORY_SELECTOR)
                count = len(categories)
                if count == 0:
                    break
                if count == prev_count:
                    for cat in categories:
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cat)
                            self.driver.execute_script("arguments[0].click();", cat)
                            time.sleep(0.4)
                        except Exception:
                            continue
                    break
                prev_count = count
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'end'});", categories[-1])
                    self.driver.execute_script("arguments[0].click();", categories[-1])
                except Exception:
                    break
                time.sleep(1)
        except Exception as e:
            logger.debug(f"Expand menu categories: {e}")

    def _parse_menu_item_element(self, item_el, category: str) -> Dict[str, Any] | None:
        title = ""
        for sel in (
            ".related-item-photo-view__title",
            ".related-product-view__title",
            ".business-prices-view__title",
            ".catalog-item-view__title",
            "[class*='title']",
        ):
            try:
                el = item_el.find_element(By.CSS_SELECTOR, sel)
                title = (el.text or el.get_attribute("textContent") or "").strip()
                if title:
                    break
            except NoSuchElementException:
                continue
        if not title:
            title = (item_el.text or "").strip().split("\n")[0].strip()
        if not title or len(title) > 200:
            return None

        price = ""
        for sel in (
            ".related-product-view__price",
            ".business-prices-view__price",
            ".related-item-photo-view__price",
            "[class*='price']",
        ):
            try:
                el = item_el.find_element(By.CSS_SELECTOR, sel)
                price = (el.text or el.get_attribute("textContent") or "").strip()
                if price and re.search(r"\d", price):
                    break
            except NoSuchElementException:
                continue

        description = ""
        for sel in (".related-item-photo-view__description", ".related-product-view__description"):
            try:
                el = item_el.find_element(By.CSS_SELECTOR, sel)
                description = (el.text or "").strip()
                if description:
                    break
            except NoSuchElementException:
                continue

        return {"category": category, "name": title, "price": price, "description": description}

    def _collect_menu_from_dom(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen: set[str] = set()

        categories = self.driver.find_elements(By.CSS_SELECTOR, CATEGORY_SELECTOR)
        if categories:
            for cat in categories:
                cat_name = ""
                try:
                    title_el = cat.find_element(By.CSS_SELECTOR, ".business-full-items-grouped-view__title")
                    cat_name = (title_el.text or "").strip()
                except NoSuchElementException:
                    cat_name = (cat.text or "").split("\n")[0].strip()
                for item_el in cat.find_elements(By.CSS_SELECTOR, ITEM_SELECTOR):
                    parsed = self._parse_menu_item_element(item_el, cat_name)
                    if not parsed:
                        continue
                    key = f"{parsed['category']}|{parsed['name']}|{parsed['price']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(parsed)
                    if len(items) >= self.max_menu_items:
                        return items

        if items:
            return items

        for sel in (
            ".business-full-items-grouped-view__item",
            ".related-product-view",
            ".business-prices-view__item",
            ".catalog-item-view",
        ):
            for item_el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                parsed = self._parse_menu_item_element(item_el, "")
                if not parsed:
                    continue
                key = f"{parsed['name']}|{parsed['price']}"
                if key in seen:
                    continue
                seen.add(key)
                items.append(parsed)
                if len(items) >= self.max_menu_items:
                    return items
            if items:
                break
        return items

    @handle_errors(default_return=[])
    def _extract_menu_services(self, main_url: str) -> List[Dict[str, Any]]:
        """Opens menu/prices tab and extracts services with prices."""
        logger.info("Opening menu/prices tab…")
        saved_url = self.driver.current_url

        for tab_name in ("prices", "menu"):
            menu_url = with_tab(main_url, tab_name)
            self.driver.get(menu_url)
            time.sleep(2.5)
            if self._wait_for_menu_container():
                break
            self._switch_to_tab_by_keywords(MENU_TAB_KEYWORDS)
            time.sleep(1.5)
            if self._wait_for_menu_container():
                break
        else:
            self._switch_to_tab_by_keywords(MENU_TAB_KEYWORDS)
            time.sleep(2)
            if not self._wait_for_menu_container():
                logger.debug("Menu tab not found for this place")
                if saved_url and saved_url != self.driver.current_url:
                    self.driver.get(saved_url)
                    time.sleep(1.5)
                return []

        self.driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(1)
        self._expand_menu_categories()
        self.driver.execute_script("window.scrollBy(0, 1200);")
        time.sleep(1)

        items = self._collect_menu_from_dom()
        logger.info(f"Menu: collected {len(items)} items")

        if main_url and self.driver.current_url != main_url:
            self.driver.get(main_url)
            time.sleep(1.5)
            self._switch_to_overview()

        return items

    def _card_has_photos(self) -> bool:
        try:
            selectors = (
                ".business-photos-view__photo img",
                ".business-photos-view img",
                ".business-card-title-view__photo img",
                ".orgpage-photos-view__photo img",
                "img.media-wrapper__media",
            )
            for sel in selectors:
                if self.driver.find_elements(By.CSS_SELECTOR, sel):
                    return True
        except Exception:
            pass
        return False

    def _has_reviews(self, reviews_count: str) -> bool:
        import re

        m = re.search(r"\d+", str(reviews_count or ""))
        return bool(m and int(m.group()) > 0)

    def _card_has_menu(self, main_url: str) -> bool:
        saved_url = self.driver.current_url
        try:
            for tab_name in ("prices", "menu"):
                self.driver.get(with_tab(main_url, tab_name))
                time.sleep(1.5)
                if self._wait_for_menu_container():
                    if self.driver.find_elements(By.CSS_SELECTOR, ITEM_SELECTOR):
                        return True
            return False
        except Exception:
            return False
        finally:
            try:
                if main_url and self.driver.current_url != main_url:
                    self.driver.get(main_url)
                    time.sleep(1)
                    self._switch_to_overview()
                elif saved_url and self.driver.current_url != saved_url:
                    self.driver.get(saved_url)
                    time.sleep(1)
            except Exception:
                pass

    def _switch_to_overview(self):
        """Switches to the Overview/About tab if not already active."""
        try:
            tabs = self.driver.find_elements(By.XPATH, 
                "//div[contains(@class, 'tabs-view__tab')] | //div[contains(text(), 'Обзор')] | //div[contains(text(), 'Overview')] | //div[contains(@class, '_name_overview')]")
            
            for tab in tabs:
                text = tab.text.lower()
                if "обзор" in text or "overview" in text or "about" in text:
                    if "_selected" not in tab.get_attribute("class"):
                        try:
                            self.driver.execute_script("arguments[0].click();", tab)
                            time.sleep(1.5)
                        except:
                            pass
                    break
        except Exception:
            pass

    def _get_text(self, selectors: List[str]) -> str:
        """Helper to try multiple selectors and return the first match's text."""
        for selector in selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                # Try getting visible text first
                text = el.text.strip()
                if text:
                    return text
                # Fallback to textContent (hidden text)
                text = el.get_attribute("textContent").strip()
                if text:
                    return text
            except NoSuchElementException:
                continue
        return ""

    def _get_text_list(self, selectors: List[str]) -> List[str]:
        """Helper to get text from all matching elements."""
        results = []
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    text = el.text.strip()
                    if not text:
                        text = el.get_attribute("textContent").strip()
                    if text and text not in results:
                        results.append(text)
                if results: # If we found something with this selector, stop
                    break
            except Exception:
                continue
        return results

    def _get_attribute(self, selectors: List[str], attribute: str) -> str:
        """Helper to get an attribute from the first matching selector."""
        for selector in selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                val = el.get_attribute(attribute)
                if val:
                    return val.strip()
            except NoSuchElementException:
                continue
        return ""

    def _get_all_attributes(self, selector: str, attribute: str) -> List[str]:
        """Helper to get an attribute from all matching elements."""
        results = []
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                val = el.get_attribute(attribute)
                if val:
                    results.append(val.strip())
        except Exception:
            pass
        return results

    def _extract_rating(self) -> str:
        """Extract rating as a clean number."""
        rating_text = self._get_text([
            ".business-rating-view__rating",
            ".business-rating-badge-view__rating"
        ])
        if rating_text:
            # Extract number from text like "Rating 4.9" or just "4.9"
            import re
            match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
            if match:
                return match.group(1)
        return ""

    def _extract_reviews_count(self) -> str:
        """Extract reviews count as a clean number."""
        count_text = self._get_text([
            ".business-header-rating-view__text",
            ".business-rating-view__count",
            ".business-rating-badge-view__count",
            ".business-header-rating-view__count",
            "span.business-rating-amount-view",
            ".orgpage-header-view__rating-label"
        ])
        if count_text:
            # Extract number from text like "1611 ratings" or "123 reviews" or just "123"
            import re
            match = re.search(r'(\d+)', count_text)
            if match:
                return match.group(1)
        return ""

    def _extract_social_links(self) -> List[str]:
        """Extracts social media links."""
        links = []
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, ".business-contacts-view__social-button a")
            for el in elements:
                href = el.get_attribute("href")
                if href:
                    links.append(href)
        except Exception:
            pass
        return links

    def _sync_photo_session_cookies(self) -> None:
        for cookie in self.driver.get_cookies():
            self.session.cookies.set(cookie["name"], cookie["value"])

    def _normalize_image_src(self, img) -> str | None:
        src = img.get_attribute("src")
        srcset = img.get_attribute("srcset")
        if srcset:
            try:
                src = srcset.split(",")[-1].strip().split(" ")[0]
            except Exception:
                pass
        if not src:
            return None
        url_path = src.split("?")[0].split("/")[-1] if "/" in src else src
        if any(x in url_path.lower() for x in ("icon", "logo", "svg")):
            return None
        if "S_height" in src or "XXS" in src or "XS_height" in src:
            src = src.replace("S_height", "XL").replace("XXS_height", "XL").replace("XS_height", "XL")
        src = src.replace("M_height", "XL").replace("L_height", "XL")
        src = src.replace("200x200", "orig").replace("400x400", "orig").replace("600x600", "orig")
        src = src.replace("priority-headline-background", "XL")
        return src

    def _collect_gallery_images(self) -> list:
        imgs = self.driver.find_elements(
            By.CSS_SELECTOR,
            "img.media-wrapper__media, "
            ".media-wrapper__media[src], "
            ".media-gallery img, "
            ".business-photos-view__photo-image img, "
            ".orgpage-photos-view__photo img, "
            ".photo-slider__image, "
            ".business-images-view__image",
        )
        seen_src: set[str] = set()
        unique = []
        for img in imgs:
            src = self._normalize_image_src(img)
            if src and src not in seen_src:
                seen_src.add(src)
                unique.append((img, src))
        return unique

    def _download_image_src(self, src: str, path: str) -> bool:
        try:
            resp = self.session.get(
                src,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://yandex.com/maps",
                },
            )
            if resp.status_code != 200 or len(resp.content) <= 1000:
                return False
            if self.photo_format in ("webp", "png") and self.photo_format != "jpg":
                try:
                    from io import BytesIO

                    from PIL import Image

                    image = Image.open(BytesIO(resp.content))
                    image.save(path, format=self.photo_format.upper())
                    return True
                except Exception:
                    pass
            with open(path, "wb") as f:
                f.write(resp.content)
            return True
        except Exception as exc:
            logger.debug(f"Download failed {path}: {exc}")
            return False

    def _discover_gallery_categories(self) -> dict[str, tuple[str, object]]:
        """slug -> (label, element)"""
        found: dict[str, tuple[str, object]] = {}
        for sel in GALLERY_CATEGORY_SELECTORS:
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    label = (el.text or el.get_attribute("textContent") or "").strip()
                    if not label or len(label) > 50:
                        continue
                    slug = match_category_slug(label)
                    if slug and slug not in found:
                        found[slug] = (label, el)
            except Exception:
                continue

        if len(found) < len(GALLERY_SECTION_SLUGS):
            for section in GALLERY_SECTIONS:
                slug = str(section["slug"])
                if slug in found:
                    continue
                for needle in section["labels"]:  # type: ignore[union-attr]
                    try:
                        xpath = (
                            "//*[contains(@class,'category') or contains(@class,'tab') or "
                            "contains(@class,'photos')][contains(translate(normalize-space(.), "
                            "'Ёё', 'Ее'), "
                            f"'{str(needle).capitalize()}') or contains(translate(normalize-space(.), "
                            "'Ёё', 'Ее'), "
                            f"'{str(needle)}')]"
                        )
                        for el in self.driver.find_elements(By.XPATH, xpath):
                            label = (el.text or el.get_attribute("textContent") or "").strip()
                            if label:
                                found[slug] = (label, el)
                                break
                        if slug in found:
                            break
                    except Exception:
                        continue
        return found

    def _click_gallery_category(self, slug: str, discovered: dict[str, tuple[str, object]]) -> bool:
        if slug in discovered:
            _label, el = discovered[slug]
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.3)
                self.driver.execute_script("arguments[0].click();", el)
                time.sleep(2)
                return True
            except Exception as exc:
                logger.debug(f"Click category {slug}: {exc}")
        section = next((s for s in GALLERY_SECTIONS if s["slug"] == slug), None)
        if not section:
            return False
        for needle in section["labels"]:  # type: ignore[union-attr]
            try:
                el = self.driver.find_element(
                    By.XPATH,
                    f"//*[self::button or self::div][contains(translate(., 'Ёё', 'Ее'), '{needle}')]",
                )
                self.driver.execute_script("arguments[0].click();", el)
                time.sleep(2)
                return True
            except Exception:
                continue
        return False

    def _download_from_current_gallery(
        self,
        target_dir: str,
        seen_urls: set[str],
        limit: int,
        file_prefix: str,
    ) -> list[str]:
        os.makedirs(target_dir, exist_ok=True)
        downloaded: list[str] = []
        for i, (_img, src) in enumerate(self._collect_gallery_images()):
            if len(downloaded) >= limit:
                break
            if src in seen_urls:
                continue
            filename = f"{file_prefix}_{len(downloaded) + 1:02d}.jpg"
            path = os.path.join(target_dir, filename)
            if self._download_image_src(src, path):
                seen_urls.add(src)
                downloaded.append(path)
                logger.info(f"📷 [{file_prefix}] {filename}")
        return downloaded

    def _extract_photos_by_categories(self, folder: str) -> tuple[list[str], dict[str, list[str]]]:
        """Скачивает до max_photos снимков из каждого раздела галереи."""
        per_section = max(1, min(self.max_photos, 10))
        by_category: dict[str, list[str]] = {}
        seen_urls: set[str] = set()
        all_paths: list[str] = []

        try:
            self._sync_photo_session_cookies()
            discovered = self._discover_gallery_categories()
            logger.info(f"Gallery categories on page: {list(discovered.keys()) or 'none'}")

            if discovered:
                for slug in GALLERY_SECTION_SLUGS:
                    title = section_title(slug)
                    if not self._click_gallery_category(slug, discovered):
                        logger.info(f"Раздел «{title}» не найден в галерее — пропуск")
                        continue
                    self._scroll_gallery()
                    cat_dir = os.path.join(folder, "photos", slug)
                    paths = self._download_from_current_gallery(cat_dir, seen_urls, per_section, slug)
                    by_category[slug] = paths
                    all_paths.extend(paths)
                    logger.info(f"Раздел «{title}»: {len(paths)} фото")
            else:
                logger.warning("Фильтры галереи не найдены — общая выдача в photos/_all/")
                flat_dir = os.path.join(folder, "photos", "_all")
                paths = self._download_from_current_gallery(flat_dir, seen_urls, per_section * 2, "all")
                by_category["_all"] = paths
                all_paths.extend(paths)

        except Exception as e:
            logger.warning(f"Photo extraction error: {e}")

        return all_paths, by_category

    def _extract_photos(self, folder: str) -> List[str]:
        """Обратная совместимость: только плоский список путей."""
        paths, _ = self._extract_photos_by_categories(folder)
        return paths

    def _extract_reviews(self) -> List[Dict[str, str]]:
        """Extracts top reviews."""
        reviews = []
        try:
            # Switch to reviews tab
            # Try finding the tab button using updated selectors
            tabs = self.driver.find_elements(By.XPATH, 
                "//div[contains(@class, 'tabs-view__tab')] | //div[contains(text(), 'Отзывы')] | //div[contains(text(), 'Reviews')] | //div[contains(@class, '_name_reviews')]")
            
            for tab in tabs:
                if "отзывы" in tab.text.lower() or "reviews" in tab.text.lower():
                    # Check if already selected
                    if "_selected" not in tab.get_attribute("class"):
                        self.driver.execute_script("arguments[0].click();", tab)
                        time.sleep(2)
                    break
            
            # Collect review items
            review_items = self.driver.find_elements(By.CSS_SELECTOR, ".business-review-view")
            
            # If no items found, maybe we need to scroll the reviews container?
            if not review_items:
                # Try scrolling the page a bit
                self.driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
                review_items = self.driver.find_elements(By.CSS_SELECTOR, ".business-review-view")

            for item in review_items[: self.max_reviews]:
                try:
                    # Rating extraction logic update: rating text might be hidden or in aria-label
                    rating_text = ""
                    try:
                        # Try finding the rating text first
                        rating_el = item.find_element(By.CSS_SELECTOR, ".business-rating-badge-view__rating-text")
                        rating_text = rating_el.text.strip()
                    except:
                        pass
                    
                    if not rating_text:
                        # Try aria-label on stars container
                        try:
                            stars_el = item.find_element(By.CSS_SELECTOR, ".business-rating-badge-view__stars")
                            aria_label = stars_el.get_attribute("aria-label")
                            if aria_label:
                                # Extract number from "Rating 5 Out of 5"
                                import re
                                match = re.search(r"(\d+(\.\d+)?)", aria_label)
                                if match:
                                    rating_text = match.group(1)
                        except:
                            pass
                    
                    # Author extraction
                    author_text = self._get_text_from_element(item, ".business-review-view__author-name span[itemprop='name']")
                    if not author_text:
                         author_text = self._get_text_from_element(item, ".business-review-view__author-name")

                    # Text extraction
                    review_body = self._get_text_from_element(item, ".business-review-view__body .spoiler-view__text")
                    if not review_body:
                        # Fallback for short reviews without spoiler
                        review_body = self._get_text_from_element(item, ".business-review-view__body")

                    r = {
                        "author": author_text,
                        "text": review_body,
                        "rating": rating_text,
                        "date": self._get_text_from_element(item, ".business-review-view__date")
                    }
                    # Only add if we have at least some content
                    if (r["text"] or r["author"]) and r["rating"]:
                        reviews.append(r)
                except Exception as e:
                    logger.debug(f"Failed to parse individual review: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Review extraction error: {e}")
        
        return reviews

    def _get_text_from_element(self, parent, selector):
        try:
            return parent.find_element(By.CSS_SELECTOR, selector).text.strip()
        except:
            return ""