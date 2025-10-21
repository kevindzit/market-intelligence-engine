import requests
import logging
import schedule
import time
import os
import chromadb
from datetime import datetime, timezone

# --- Configuration ---
# Your FMP API Key
FMP_API_KEY = "Scqx3sMK3VClLLA3iaxar0tYwZOeX30y" # Use the key you provided

# *** CHANGE: Use the Market News endpoint (likely free) ***
FMP_NEWS_ENDPOINT = f"https://financialmodelingprep.com/api/v3/market-news?limit=50&apikey={FMP_API_KEY}"

# ChromaDB Setup (Same as the NewsAPI reader)
CHROMA_PATH = "chroma_db_news" # Folder where ChromaDB will store data
COLLECTION_NAME = "news_articles"
os.makedirs(CHROMA_PATH, exist_ok=True) # Ensure path exists
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

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

def parse_fmp_datetime(date_string):
    """Safely parses FMP date strings, which are often in 'YYYY-MM-DD HH:MM:SS' format (UTC)."""
    if not date_string:
        return datetime.now(timezone.utc)
    try:
        # FMP dates are typically UTC
        dt = datetime.strptime(date_string, '%Y-m-d %H:%M:%S')
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        logging.warning(f"Could not parse FMP timestamp: {date_string}. Using current time.")
        return datetime.now(timezone.utc)

def fetch_and_store_fmp_news():
    """Fetches news from FMP and stores new articles in ChromaDB."""
    logging.info("Attempting to fetch news from FMP API (Market News endpoint)...")

    try:
        response = requests.get(FMP_NEWS_ENDPOINT, timeout=20)
        response.raise_for_status()
        articles = response.json() # FMP returns a list of articles

        if not isinstance(articles, list):
            # Handle potential error message from API if key is wrong etc.
            if isinstance(articles, dict) and 'Error Message' in articles:
                 logging.error(f"FMP API Error: {articles['Error Message']}")
                 # Potentially stop scheduling if the key is definitively invalid
                 # return schedule.CancelJob
                 return
            logging.error(f"FMP API did not return a list. Response: {articles}")
            return

        logging.info(f"Fetched {len(articles)} articles from FMP Market News.")
        added_count = 0

        for article in articles:
            # *** CHANGE: FMP Market News might use 'url' or 'link' - check both ***
            url = article.get("url") or article.get("link")
            headline = article.get("title")
            content = article.get("text") or headline # FMP provides 'text' which is the snippet
            published_at_str = article.get("publishedDate")
            source_site = article.get("site", "FMP") # FMP provides 'site'

            if not url or not headline:
                logging.warning(f"Skipping article with missing URL or headline: {article.get('title')}")
                continue

            # Check if this article is already in ChromaDB using its URL as the ID
            try:
                existing = collection.get(ids=[url])
                if existing and existing['ids']:
                    logging.debug(f"Article already exists in DB: {url}")
                    continue # Skip adding if already present
            except Exception as e:
                # This might happen if the ID format is unexpected or DB is busy. Log and continue.
                logging.warning(f"Could not check existence for ID {url} in ChromaDB: {e}. Attempting to add anyway.")


            published_dt = parse_fmp_datetime(published_at_str)
            scraped_at = datetime.now(timezone.utc)

            metadata = {
                "source": source_site,
                "headline": headline,
                "url": url,
                "timestamp": published_dt.isoformat(), # Store timestamp as ISO string
                "scraped_at": scraped_at.isoformat(),
                 # *** CHANGE: Market news endpoint might not have 'symbol', handle if missing ***
                "ticker_mentioned": article.get("symbol", "N/A")
            }

            try:
                # Add to ChromaDB using URL as the unique ID
                collection.add(
                    documents=[content if content else headline], # Use headline if text snippet is empty
                    metadatas=[metadata],
                    ids=[url]
                )
                added_count += 1
                logging.debug(f"Added article: {headline}")
            except Exception as e:
                logging.error(f"Error adding article to ChromaDB (ID: {url}): {e}")

        logging.info(f"Added {added_count} new articles to ChromaDB from FMP.")

    except requests.exceptions.HTTPError as e:
        # Check specifically for 403 again, could still be key typo or other issue
        if e.response.status_code == 403:
             logging.error(f"FMP API request failed (403 Forbidden). Double-check your API key is correct and active on the FMP dashboard.")
        elif e.response.status_code == 401:
             logging.error(f"FMP API request failed (401 Unauthorized). Your API key seems invalid or deactivated.")
        else:
             logging.error(f"HTTP error fetching data from FMP API ({e.response.status_code}): {e}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching data from FMP API: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    setup_logging()
    logging.info("--- Starting FMP News Reader ---")

    # Double-check the key isn't the placeholder
    if FMP_API_KEY == "YOUR_FMP_API_KEY_HERE" or len(FMP_API_KEY) < 10: # Basic check
        logging.error("Please replace 'YOUR_FMP_API_KEY_HERE' with your actual FMP API key in the script.")
    else:
        # Run once immediately to fetch news
        fetch_and_store_fmp_news()

        # Schedule the job to run every 20 minutes
        schedule.every(20).minutes.do(fetch_and_store_fmp_news)
        logging.info("Scheduled FMP news fetching every 20 minutes.")

        while True:
            schedule.run_pending()
            time.sleep(60) # Check every minute