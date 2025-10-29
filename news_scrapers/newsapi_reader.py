"""
NewsAPI Reader - PostgreSQL Version
Fetches business news and stores in PostgreSQL (replaces ChromaDB)
Simple and matches style of other scrapers
"""

import requests
import logging
import schedule
import time
import os
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration (same as before)
NEWSAPI_KEY = os.getenv('NEWS_API_KEY')
NEWSAPI_ENDPOINT = f"https://newsapi.org/v2/top-headlines?country=us&category=business&apiKey={NEWSAPI_KEY}"

# PostgreSQL config (same as your Twitter scrapers)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

def setup_logging():
    """Sets up basic logging to console."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db_connection():
    """Get PostgreSQL connection (same as twitter scrapers)"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return None

def parse_iso_datetime(date_string):
    """Safely parses ISO date strings."""
    if not date_string:
        return datetime.now(timezone.utc)
    try:
        if date_string.endswith('Z'):
            date_string = date_string[:-1] + '+00:00'
        return datetime.fromisoformat(date_string)
    except (ValueError, TypeError):
        logging.warning(f"Could not parse timestamp: {date_string}. Using current time.")
        return datetime.now(timezone.utc)

def fetch_and_store_news():
    """Fetches news from NewsAPI and stores in PostgreSQL."""
    logging.info("Fetching news from NewsAPI...")

    # Get database connection
    conn = get_db_connection()
    if not conn:
        logging.error("No database connection available")
        return

    cursor = conn.cursor()

    try:
        # Fetch news from API
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
            title = article.get("title")
            published_at = parse_iso_datetime(article.get("publishedAt"))
            content = article.get("description") or article.get("content") or title
            source = article.get("source", {}).get("name", "NewsAPI")

            if not url or not title:
                logging.warning(f"Skipping article with missing URL or title")
                continue

            try:
                # Insert into PostgreSQL (ON CONFLICT prevents duplicates just like ChromaDB)
                cursor.execute("""
                    INSERT INTO news_articles (title, content, url, source, published_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                """, (title, content, url, source, published_at))

                if cursor.rowcount > 0:
                    added_count += 1
                    logging.debug(f"Added article: {title[:50]}...")

            except Exception as e:
                logging.error(f"Error adding article to database: {e}")

        # Commit all inserts
        conn.commit()
        logging.info(f"Added {added_count} new articles to PostgreSQL.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data from NewsAPI: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    setup_logging()
    logging.info("--- Starting NewsAPI Reader (PostgreSQL) ---")

    if not NEWSAPI_KEY or NEWSAPI_KEY == "YOUR_NEWSAPI_KEY_HERE":
        logging.error("Please set NEWS_API_KEY in your .env file")
    else:
        # Run once immediately
        fetch_and_store_news()

        # Schedule every 15 minutes (same as before)
        schedule.every(15).minutes.do(fetch_and_store_news)
        logging.info("Scheduled news fetching every 15 minutes.")

        while True:
            schedule.run_pending()
            time.sleep(60)