import requests
import logging
import schedule
import time
import os
import chromadb
from datetime import datetime, timezone

# --- Configuration ---
# IMPORTANT: Replace "YOUR_NEWSAPI_KEY_HERE" with your actual NewsAPI key.
# For better security in a real application, use environment variables
# or a secrets management tool instead of hardcoding the key.
NEWSAPI_KEY = "9a86365177184e979c4c5f2f36eb207f"
# Check key again here: 9a86365177184e979c4c5f2f36eb207f
NEWSAPI_ENDPOINT = f"https://newsapi.org/v2/top-headlines?country=us&category=business&apiKey={NEWSAPI_KEY}"

# ChromaDB Setup (Assumes default local setup)
CHROMA_PATH = "chroma_db_news" # Folder where ChromaDB will store data
COLLECTION_NAME = "news_articles"
# Ensure ChromaDB path exists
os.makedirs(CHROMA_PATH, exist_ok=True)
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

# Keep track of recently processed URLs in this run to avoid immediate duplicates
processed_urls_this_run = set()

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

def parse_iso_datetime(date_string):
    """Safely parses ISO date strings, handling potential None values or format issues."""
    if not date_string:
        return datetime.now(timezone.utc) # Default to now if no date provided
    try:
        # Handle timezone info ('Z' for UTC)
        if date_string.endswith('Z'):
            date_string = date_string[:-1] + '+00:00'
        return datetime.fromisoformat(date_string)
    except (ValueError, TypeError):
        logging.warning(f"Could not parse timestamp: {date_string}. Using current time.")
        return datetime.now(timezone.utc) # Default to now if parsing fails

def fetch_and_store_news():
    """Fetches news from NewsAPI and stores new articles in ChromaDB."""
    global processed_urls_this_run
    logging.info("Attempting to fetch news from NewsAPI...")
    processed_urls_this_run.clear() # Clear for this new fetch cycle

    try:
        response = requests.get(NEWSAPI_ENDPOINT, timeout=20)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "ok":
            logging.error(f"NewsAPI request failed: {data.get('message', 'Unknown error')}")
            return

        articles = data.get("articles", [])
        logging.info(f"Fetched {len(articles)} articles from NewsAPI.")
        added_count = 0

        for article in articles:
            url = article.get("url")
            headline = article.get("title")
            published_at_str = article.get("publishedAt")
            content = article.get("description") or article.get("content") or headline # Fallback content

            if not url or not headline:
                logging.warning(f"Skipping article with missing URL or headline: {article}")
                continue

            # Basic duplicate check using URL as ID
            # ChromaDB handles persistent duplicates if the ID exists.
            # This set handles duplicates within the same API response.
            if url in processed_urls_this_run:
                continue
                
            # Check if already in ChromaDB - More robust check
            try:
                existing = collection.get(ids=[url])
                if existing and existing['ids']:
                    logging.debug(f"Article already exists in DB: {url}")
                    processed_urls_this_run.add(url) # Add to set even if found in DB
                    continue # Skip adding if already present
            except Exception as e:
                # Handle cases where ChromaDB might raise an error for non-existent IDs depending on version
                # Or other potential DB query issues
                logging.warning(f"Could not check existence for ID {url} in ChromaDB: {e}. Attempting to add anyway.")


            published_dt = parse_iso_datetime(published_at_str)
            scraped_at = datetime.now(timezone.utc)

            metadata = {
                "source": article.get("source", {}).get("name", "newsapi"), # Get source name if available
                "headline": headline,
                "url": url,
                "timestamp": published_dt.isoformat(), # Store timestamp as ISO string
                "scraped_at": scraped_at.isoformat()
            }

            try:
                # Add to ChromaDB using URL as the unique ID
                collection.add(
                    documents=[content if content else headline], # Use headline if description/content is empty
                    metadatas=[metadata],
                    ids=[url]
                )
                added_count += 1
                processed_urls_this_run.add(url)
                logging.debug(f"Added article: {headline}")
            except Exception as e:
                logging.error(f"Error adding article to ChromaDB (ID: {url}): {e}")

        logging.info(f"Added {added_count} new articles to ChromaDB.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data from NewsAPI: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    setup_logging()
    logging.info("--- Starting NewsAPI Reader ---")

    # IMPORTANT: Replace "YOUR_NEWSAPI_KEY_HERE" with your actual key above!
    if NEWSAPI_KEY == "YOUR_NEWSAPI_KEY_HERE":
        logging.error("Please replace 'YOUR_NEWSAPI_KEY_HERE' with your actual NewsAPI key in the script.")
    else:
        # Run once immediately
        fetch_and_store_news()

        # Schedule the job to run every 15 minutes (adjust as needed)
        schedule.every(15).minutes.do(fetch_and_store_news)
        logging.info("Scheduled news fetching every 15 minutes.")

        while True:
            schedule.run_pending()
            time.sleep(60) # Check every minute if a scheduled job is due