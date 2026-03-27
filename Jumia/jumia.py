import json
import hashlib
import logging
import os
import time
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TARGET_URL = "https://www.jumia.com.eg/womens-fashion/"
TARGET_CATEGORY = "Women's Fashion"
OUTPUT_FILE = "jumia_products.json"
METADATA_FILE = "metadata.json"
MAX_PAGES = 3
DEBUG_SCREENSHOT_DIR = "debug_screenshots"


def build_driver() -> webdriver.Chrome:
    """Create and configure a Chrome WebDriver instance for stable headless scraping."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f"--user-agent={USER_AGENT}")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver


def load_page_with_retry(driver: webdriver.Chrome, url: str, retries: int = 2) -> bool:
    """Load a page with retry logic to tolerate transient network/browser timeouts."""
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            return True
        except (TimeoutException, WebDriverException) as exc:
            logging.warning("Page load failed (attempt %s/%s): %s", attempt, retries, exc)
            try:
                driver.execute_script("window.stop();")
            except WebDriverException:
                pass
    return False


def scroll_for_lazy_loading(driver: webdriver.Chrome) -> None:
    """
    Scroll down in stages to trigger lazy-loaded assets.

    Product images on e-commerce pages are often loaded only after cards enter viewport.
    Staged scrolling helps ensure image URLs are available before extraction.
    """
    for fraction in (0.4, 0.7, 1.0):
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight * arguments[0]);", fraction
        )
        WebDriverWait(driver, 8).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )


def save_debug_screenshot(driver: webdriver.Chrome, page_number: int) -> Optional[str]:
    """Save a screenshot before scraping to verify what headless browser rendered."""
    try:
        os.makedirs(DEBUG_SCREENSHOT_DIR, exist_ok=True)
        path = os.path.join(DEBUG_SCREENSHOT_DIR, f"page_{page_number}.png")
        if driver.save_screenshot(path):
            return path
        return None
    except WebDriverException as exc:
        logging.warning("Failed to save debug screenshot for page %s: %s", page_number, exc)
        return None


def safe_text(parent: WebElement, selector: str) -> str:
    """Return stripped text from a CSS selector, or empty string if missing."""
    elements = parent.find_elements(By.CSS_SELECTOR, selector)
    return elements[0].text.strip() if elements else ""


def safe_first_text(parent: WebElement, selectors: List[str]) -> str:
    """Return first non-empty text from a list of candidate CSS selectors."""
    for selector in selectors:
        text_value = safe_text(parent, selector)
        if text_value:
            return text_value
    return ""


def safe_image_url(parent: WebElement) -> str:
    """Extract image URL using resilient attribute fallbacks for lazy-loaded cards."""
    images = parent.find_elements(By.CSS_SELECTOR, "img")
    for image in images:
        for attr in ("data-src", "data-srcset", "src", "srcset"):
            raw = (image.get_attribute(attr) or "").strip()
            if not raw:
                continue

            # srcset may contain comma-separated image candidates; first URL is enough here.
            candidate = raw.split(",")[0].strip().split(" ")[0]
            if candidate.startswith(("http://", "https://")):
                return candidate
    return ""


def get_product_cards(driver: webdriver.Chrome) -> List[WebElement]:
    """Locate product cards with fallback selectors to survive minor DOM changes."""
    selectors = [
        "article.prd",
        "div.prd",
        "a.core",
        "main article[class*='prd']",
    ]
    for selector in selectors:
        cards = driver.find_elements(By.CSS_SELECTOR, selector)
        if cards:
            return cards
    return []


def validate_item_schema(item: Dict[str, str]) -> bool:
    """Validate that each item strictly follows the required graduation-project schema."""
    required_keys = ["title", "price", "rating", "images", "category"]
    if sorted(item.keys()) != sorted(required_keys):
        return False

    if any(not isinstance(item[key], str) for key in required_keys):
        return False

    # Images must be a URL per requested schema.
    if item["images"] and not item["images"].startswith(("http://", "https://")):
        return False

    return True


def product_hash(title: str, image_url: str) -> str:
    """Build a stable hash fingerprint for deduplication using title + image URL."""
    normalized = f"{title.strip().lower()}|{image_url.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_product_card(card: WebElement, category_name: str) -> Optional[Dict[str, str]]:
    """Parse one product card safely; return None when mandatory fields are missing."""
    try:
        item = {
            "title": safe_first_text(card, [".name", "h3.name", "[data-name]", "h2", "h3"]),
            "price": safe_first_text(card, [".prc", ".price", "[class*='prc']", "[class*='price']"]),
            "rating": safe_first_text(card, [".rev", ".stars._s", "[class*='rating']"]),
            "images": safe_image_url(card),
            "category": category_name,
        }

        if not item["title"] or not item["price"]:
            return None
        if not validate_item_schema(item):
            return None

        return item
    except WebDriverException as exc:
        logging.warning("Product parse error: %s", exc)
        return None


def find_next_button(driver: webdriver.Chrome) -> Optional[WebElement]:
    """Find a usable next-page control using multiple resilient selectors."""
    selectors = [
        "a[rel='next']",
        "a[aria-label*='Next']",
        "a.pg[aria-label*='next']",
        "a[aria-label*='التالي']",
        "a[title*='Next']",
        "a[title*='next']",
        "a[title*='التالي']",
        "a.pg",
    ]
    for selector in selectors:
        for button in driver.find_elements(By.CSS_SELECTOR, selector):
            text = (button.text or "").strip().lower()
            classes = (button.get_attribute("class") or "").lower()
            looks_like_next = any(token in text for token in ("next", "التالي", ">"))
            if button.is_displayed() and button.is_enabled() and "dis" not in classes and (
                looks_like_next or selector != "a.pg"
            ):
                return button

    # XPath fallback covers cases where pagination has only icon/text markers.
    xpath = (
        "//a[contains(translate(normalize-space(.), 'NEXT', 'next'), 'next') "
        "or contains(normalize-space(.), 'التالي') "
        "or @rel='next']"
    )
    for button in driver.find_elements(By.XPATH, xpath):
        classes = (button.get_attribute("class") or "").lower()
        if button.is_displayed() and button.is_enabled() and "dis" not in classes:
            return button
    return None


def scrape_jumia_category(
    driver: webdriver.Chrome,
    url: str,
    category_name: str,
    max_pages: int = 3,
) -> tuple[List[Dict[str, str]], Dict[str, float]]:
    """
    Scrape multiple result pages from a Jumia category.

    Engineering choices:
    - Explicit waits replace fixed sleeps for faster, deterministic synchronization.
    - Item-level try/except prevents one broken card from terminating the job.
    - Pagination loop is bounded (`max_pages`) for predictable runtime.
    """
    wait = WebDriverWait(driver, 15)
    start_time = time.perf_counter()
    scraped_data: List[Dict[str, str]] = []
    seen_product_hashes = set()
    current_url = url
    report: Dict[str, float] = {
        "total_pages_visited": 0,
        "total_cards_identified": 0,
        "valid_cards_saved": 0,
        "rejected_cards_count": 0,
        "execution_time_seconds": 0.0,
    }

    for page_number in range(1, max_pages + 1):
        logging.info("Scraping page %s: %s", page_number, current_url)
        if not load_page_with_retry(driver, current_url):
            logging.error("Skipping page due to repeated load failures: %s", current_url)
            continue

        report["total_pages_visited"] += 1

        try:
            wait.until(
                lambda d: len(get_product_cards(d)) > 0
            )
        except TimeoutException:
            logging.error("Timed out waiting for product grid on page %s", page_number)
            continue

        scroll_for_lazy_loading(driver)
        screenshot_path = save_debug_screenshot(driver, page_number)
        if screenshot_path:
            logging.info("Saved debug screenshot: %s", screenshot_path)

        cards = get_product_cards(driver)
        report["total_cards_identified"] += len(cards)

        for index, card in enumerate(cards, start=1):
            try:
                item = parse_product_card(card, category_name)
                if not item:
                    report["rejected_cards_count"] += 1
                    continue

                dedup_key = product_hash(item["title"], item["images"])
                if dedup_key in seen_product_hashes:
                    report["rejected_cards_count"] += 1
                    continue

                seen_product_hashes.add(dedup_key)
                scraped_data.append(item)
                report["valid_cards_saved"] += 1
            except Exception as exc:
                logging.warning("Card %s failed on page %s: %s", index, page_number, exc)
                report["rejected_cards_count"] += 1

        logging.info("Collected %s items so far.", len(scraped_data))

        if page_number >= max_pages:
            break

        first_card = cards[0] if cards else None
        next_button = find_next_button(driver)
        if not next_button:
            logging.info("No next page button found; stopping pagination.")
            break

        try:
            next_href = next_button.get_attribute("href")
            driver.execute_script("arguments[0].click();", next_button)

            if first_card:
                wait.until(EC.staleness_of(first_card))
            wait.until(lambda d: len(get_product_cards(d)) > 0)

            current_url = next_href or driver.current_url
        except (TimeoutException, WebDriverException) as exc:
            logging.error("Pagination click failed on page %s: %s", page_number, exc)
            break

    report["execution_time_seconds"] = round(time.perf_counter() - start_time, 2)
    return scraped_data, report


def log_professional_summary(report: Dict[str, float], output_file: str, metadata_file: str) -> None:
    """Print a professional end-of-run scraping summary to terminal logs."""
    logging.info("=" * 70)
    logging.info("SCRAPING RUN SUMMARY")
    logging.info("Total pages visited    : %s", int(report["total_pages_visited"]))
    logging.info("Total cards identified : %s", int(report["total_cards_identified"]))
    logging.info("Valid cards saved      : %s", int(report["valid_cards_saved"]))
    logging.info("Rejected cards count   : %s", int(report["rejected_cards_count"]))
    logging.info("Execution time (sec)   : %s", report["execution_time_seconds"])
    logging.info("Data output file       : %s", output_file)
    logging.info("Metadata file          : %s", metadata_file)
    logging.info("=" * 70)


def main() -> None:
    """Entrypoint for scraping Jumia category pages and exporting validated JSON."""
    driver = build_driver()
    try:
        results, report = scrape_jumia_category(
            driver=driver,
            url=TARGET_URL,
            category_name=TARGET_CATEGORY,
            max_pages=MAX_PAGES,
        )

        with open(OUTPUT_FILE, "w", encoding="utf-8") as output_file:
            json.dump(results, output_file, ensure_ascii=False, indent=4)

        with open(METADATA_FILE, "w", encoding="utf-8") as metadata_output:
            json.dump(report, metadata_output, ensure_ascii=False, indent=4)

        logging.info("Successfully exported %s records to %s", len(results), OUTPUT_FILE)
        log_professional_summary(report, OUTPUT_FILE, METADATA_FILE)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()