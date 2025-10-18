import logging
import time
import re # Import the 're' module
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

# --- Configuration ---
REUTERS_MARKETS_URL = "https://www.reuters.com/markets/"

def setup_logging():
    """Sets up basic logging to console."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    root_logger = logging.getLogger('')
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.addHandler(console)

def fetch_page_content_selenium(url):
    """Fetches HTML content from a given URL using Selenium."""
    driver = None
    try:
        options = Options()
        # options.add_argument("--headless=new") # Run headless for efficiency later
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument('--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"') # Mimic browser
        options.page_load_strategy = 'eager' # Don't wait for everything to load fully

        logging.info(f"Attempting to fetch {url} using Selenium...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.set_page_load_timeout(30) # Set timeout
        driver.get(url)
        time.sleep(5) # Give the page a moment to load dynamic content
        html_content = driver.page_source
        logging.info(f"Successfully fetched content from {url} using Selenium")
        return html_content
    except TimeoutException:
        logging.error(f"Timeout occurred while loading URL {url}")
        return None
    except WebDriverException as e:
        logging.error(f"WebDriver error fetching URL {url}: {e}")
        return None
    finally:
        if driver:
            driver.quit()
            logging.info("Selenium WebDriver closed.")

def scrape_reuters_headlines(html_content):
    """Parses HTML to extract headlines and links from Reuters Markets."""
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    articles = []
    processed_urls = set()

    logging.info("Parsing fetched HTML content...")

    # --- Refined Guess for finding articles (Adapt based on inspection) ---
    # Look for <a> tags with specific data-testid attributes or within common structure
    # Common pattern from manual inspection might be needed. Let's try finding links
    # that have a specific 'data-testid' often used in modern web design.
    # OR links within list items or article tags.

    # Example Selector (Adjust after inspecting the live page):
    # Find all 'a' tags that have a 'data-testid' containing 'Heading'
    # links = soup.find_all('a', attrs={'data-testid': re.compile(r'Heading', re.IGNORECASE)})

    # A broader approach if the above fails: find all links and filter
    all_links = soup.find_all('a', href=True)
    logging.info(f"Found {len(all_links)} total links. Filtering...")


    for link in all_links:
        href = link['href']
        headline_text = link.get_text(strip=True)

        # --- Stricter Filter for Reuters Article URLs ---
        # Needs to start with /markets/SECTION/ARTICLE-TITLE-YYYY-MM-DD/
        # Or sometimes /world/, /business/, /legal/, etc.
        is_article_link = re.match(r'^/(markets|business|world|legal|technology)/[a-z-]+/[a-z0-9-]+-\d{4}-\d{2}-\d{2}/?$', href)

        if (is_article_link and
            headline_text and len(headline_text) > 15 and # Reasonably long headlines
            href not in processed_urls):

            full_url = f"https://www.reuters.com{href}" # Construct full URL
            articles.append({
                'headline': headline_text,
                'url': full_url
            })
            processed_urls.add(href)


    logging.info(f"Extracted {len(articles)} potential articles based on URL pattern.")
    return articles


if __name__ == "__main__":
    setup_logging()
    logging.info("--- Starting Reuters Scraper (Selenium Version) ---")

    # Use Selenium to fetch content
    html = fetch_page_content_selenium(REUTERS_MARKETS_URL)

    if html:
        extracted_articles = scrape_reuters_headlines(html)
        if extracted_articles:
            logging.info("Found Articles:")
            for i, article in enumerate(extracted_articles, 1):
                print(f"{i}. Headline: {article['headline']}")
                print(f"   URL: {article['url']}")
        else:
            logging.warning("Could not extract any articles with the current selectors. The website structure might have changed or the selectors need adjustment.")
    else:
        logging.error("Failed to fetch page content using Selenium. Exiting.")

    logging.info("--- Reuters Scraper Finished ---")