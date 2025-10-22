import feedparser
import chromadb
import schedule
import time
import logging
from datetime import datetime, timezone

# --- Configuration ---
CHROMA_PATH = "chroma_db_news"
COLLECTION_NAME = "news_articles"

# RSS Feed Sources (All Free & Unlimited)
RSS_FEEDS = {
    "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    "MarketWatch_Markets": "https://www.marketwatch.com/rss/marketpulse",
    "CNBC_Top": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CNBC_Markets": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "Reuters_Business": "https://www.reuters.com/arc/outboundfeeds/v3/category/business/?outputType=xml",
    "Reuters_Markets": "https://www.reuters.com/arc/outboundfeeds/v3/category/markets/?outputType=xml",
    "Benzinga": "https://www.benzinga.com/feed",
    "Nasdaq": "https://www.nasdaq.com/feed/rssoutbound?category=Stocks",
    "Investing_Latest": "https://www.investing.com/rss/news.rss",
    "Investing_Markets": "https://www.investing.com/rss/news_285.rss",  # Stock market news
}

def setup_logging():
    """Sets up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename='../logs/rss_aggregator.log',
        filemode='a'  # Append mode
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

def get_chroma_collection():
    """Initializes and returns the ChromaDB collection."""
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_or_create_collection(name=COLLECTION_NAME)
        return collection
    except Exception as e:
        logging.error(f"ChromaDB initialization error: {e}")
        return None

def fetch_rss_feed(feed_name, feed_url):
    """Fetches and parses a single RSS feed."""
    try:
        logging.info(f"Fetching {feed_name}...")
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            logging.warning(f"{feed_name}: Feed parsing warning - {feed.bozo_exception}")

        articles = []
        for entry in feed.entries:
            # Extract article details
            title = entry.get('title', 'No Title')
            url = entry.get('link', 'No URL')

            # Get description/summary
            description = entry.get('summary', entry.get('description', 'No description available'))

            # Get published date
            published = entry.get('published', entry.get('updated', None))
            if published:
                try:
                    # Try to parse the date
                    published_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    published = published_dt.isoformat()
                except:
                    pass  # Keep original string if parsing fails

            articles.append({
                'title': title,
                'url': url,
                'description': description,
                'published': published,
                'source': feed_name
            })

        logging.info(f"{feed_name}: Found {len(articles)} articles")
        return articles

    except Exception as e:
        logging.error(f"{feed_name}: Error fetching feed - {e}")
        return []

def store_in_chromadb(collection, articles):
    """Stores articles in ChromaDB with deduplication."""
    if not collection or not articles:
        return 0

    new_articles = 0
    skipped = 0

    for article in articles:
        try:
            url = article['url']

            # Check if article already exists (URL is the unique ID)
            existing = collection.get(ids=[url])
            if existing['ids']:
                skipped += 1
                continue

            # Add new article
            collection.add(
                ids=[url],
                documents=[article['description']],
                metadatas=[{
                    'headline': article['title'],
                    'url': url,
                    'source': article['source'],
                    'timestamp': article.get('published', 'Unknown'),
                    'scraped_at': datetime.now(timezone.utc).isoformat()
                }]
            )
            new_articles += 1

        except Exception as e:
            logging.error(f"Error storing article: {e}")
            continue

    logging.info(f"Stored {new_articles} new articles, skipped {skipped} duplicates")
    return new_articles

def run_aggregator():
    """Main function to fetch all RSS feeds and store articles."""
    logging.info("=== Starting RSS Aggregator Run ===")

    collection = get_chroma_collection()
    if not collection:
        logging.error("Failed to initialize ChromaDB. Exiting.")
        return

    total_fetched = 0
    total_stored = 0

    # Fetch from all RSS feeds
    for feed_name, feed_url in RSS_FEEDS.items():
        articles = fetch_rss_feed(feed_name, feed_url)
        total_fetched += len(articles)

        if articles:
            stored = store_in_chromadb(collection, articles)
            total_stored += stored

        # Be polite - small delay between feeds
        time.sleep(1)

    logging.info(f"=== Run Complete: Fetched {total_fetched} articles, stored {total_stored} new ===")
    logging.info(f"Total articles in database: {collection.count()}")

if __name__ == "__main__":
    setup_logging()
    logging.info("--- RSS News Aggregator Started ---")

    # Run once immediately
    run_aggregator()

    # Schedule to run every 15 minutes (same as NewsAPI)
    schedule.every(15).minutes.do(run_aggregator)
    logging.info("Scheduled to run every 15 minutes")

    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(60)
