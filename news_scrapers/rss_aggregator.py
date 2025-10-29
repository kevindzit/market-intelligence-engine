"""
RSS Aggregator - PostgreSQL Version
Fetches RSS feeds and stores in PostgreSQL (replaces ChromaDB)
"""

import feedparser
import psycopg2
import schedule
import time
import logging
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL config
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# RSS Feeds (same as before)
RSS_FEEDS = {
    "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    "MarketWatch_Markets": "https://www.marketwatch.com/rss/marketpulse",
    "CNBC_Top": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CNBC_Markets": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "Benzinga": "https://www.benzinga.com/feed",
    "Investing_Stocks": "https://www.investing.com/rss/news_25.rss",
    "Investing_Economy": "https://www.investing.com/rss/news_14.rss",
    "Investing_Crypto": "https://www.investing.com/rss/news_301.rss",
    "Reuters_via_Google": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&ceid=US:en&hl=en-US&gl=US",
}

def setup_logging():
    """Sets up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def get_db_connection():
    """Get PostgreSQL connection"""
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

def fetch_rss_feed(feed_name, feed_url):
    """Fetches and parses a single RSS feed."""
    try:
        logging.info(f"Fetching {feed_name}...")

        feed = feedparser.parse(
            feed_url,
            agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            request_headers={'Connection': 'close'}
        )

        if feed.bozo:
            logging.warning(f"{feed_name}: Feed parsing warning - {feed.bozo_exception}")

        articles = []
        for entry in feed.entries:
            title = entry.get('title', 'No Title')
            url = entry.get('link', '')
            description = entry.get('summary', entry.get('description', 'No description'))

            # Parse published date
            published = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except:
                    pass

            if url:  # Only add if URL exists
                articles.append({
                    'title': title,
                    'url': url,
                    'content': description,
                    'published_at': published,
                    'source': feed_name
                })

        logging.info(f"{feed_name}: Found {len(articles)} articles")
        return articles

    except Exception as e:
        logging.error(f"{feed_name}: Error fetching feed - {e}")
        return []

def store_articles(articles):
    """Store articles in PostgreSQL"""
    if not articles:
        return 0

    conn = get_db_connection()
    if not conn:
        return 0

    cursor = conn.cursor()
    added_count = 0

    try:
        for article in articles:
            try:
                cursor.execute("""
                    INSERT INTO news_articles (title, content, url, source, published_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                """, (
                    article['title'],
                    article['content'],
                    article['url'],
                    article['source'],
                    article['published_at']
                ))

                if cursor.rowcount > 0:
                    added_count += 1

            except Exception as e:
                logging.error(f"Error inserting article: {e}")

        conn.commit()

    except Exception as e:
        logging.error(f"Database error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return added_count

def fetch_all_feeds():
    """Fetch all RSS feeds and store in PostgreSQL"""
    logging.info("Starting RSS aggregation cycle...")
    total_added = 0

    for feed_name, feed_url in RSS_FEEDS.items():
        articles = fetch_rss_feed(feed_name, feed_url)
        added = store_articles(articles)
        total_added += added

    logging.info(f"Aggregation complete. Added {total_added} new articles total.")

if __name__ == "__main__":
    setup_logging()
    logging.info("--- Starting RSS Aggregator (PostgreSQL) ---")

    # Run once immediately
    fetch_all_feeds()

    # Schedule every 30 minutes
    schedule.every(30).minutes.do(fetch_all_feeds)
    logging.info("Scheduled RSS fetching every 30 minutes.")

    while True:
        schedule.run_pending()
        time.sleep(60)