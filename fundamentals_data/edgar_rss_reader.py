import feedparser
import logging
import schedule
import time
import psycopg2
import re
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import requests  # Import the requests library

try:
    from scraper_utils.heartbeat import touch_heartbeat
except ImportError:
    def touch_heartbeat(_: str):
        pass

# Load environment variables
load_dotenv()

# --- Configuration ---
# SEC RSS feed for the 100 latest corporate filings (exclude insider-only stream)
SEC_RSS_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&owner=exclude&count=100&output=atom"

# *** THIS IS THE FIX ***
# The SEC requires a custom User-Agent in the format: "Sample Company Name AdminContact@example.com"
# Replace with your own info.
REQUEST_HEADERS = {
    'User-Agent': 'Kevin Personal Project kevin@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

# PostgreSQL Connection Details
DB_NAME = os.getenv('DB_NAME', 'pjx')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASSWORD', 'postgres')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')

# --- Optional: Filter for specific form types ---
# Leave the env var blank to capture ALL form types.
DEFAULT_FORM_TYPE_FILTER = ["8-K", "10-Q", "4", "10-K"]
form_filter_raw = os.getenv("SEC_FORM_TYPES")
if form_filter_raw is None:
    form_filter_raw = ",".join(DEFAULT_FORM_TYPE_FILTER)
FORM_TYPE_FILTER = [
    form.strip().upper()
    for form in form_filter_raw.split(",")
    if form.strip()
]

# Polling cadence (minutes)
POLL_INTERVAL_MINUTES = max(int(os.getenv("SEC_POLL_INTERVAL_MINUTES", "5")), 1)

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

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
        )
        return conn
    except psycopg2.OperationalError as e:
        logging.error(f"Database connection failed: {e}")
        return None

def parse_filing_title(title):
    """Parses the title of an SEC filing to extract form type, company name, and CIK."""
    # Example Title: "8-K - TESLA, INC. (0001318605) (Filer)"
    match = re.match(r'^(?P<form_type>[\w\s/-]+)\s-\s(?P<company_name>.+?)\s\((?P<cik>\d+)\)', title)
    if match:
        return match.groupdict()
    return None


def determine_form_type(entry, parsed_title):
    """Prefer the feed's category/tag for form type, fallback to parsed title."""
    tag_term = None
    tags = getattr(entry, 'tags', None)
    if tags:
        for tag in tags:
            term = tag.get('term') or tag.get('label')
            if term:
                tag_term = term
                break

    category = getattr(entry, 'category', None)
    if category and not tag_term:
        if isinstance(category, dict):
            tag_term = category.get('term') or category.get('label')
        else:
            tag_term = getattr(category, 'term', None) or getattr(category, 'label', None) or str(category)

    raw_form = tag_term or (parsed_title['form_type'] if parsed_title else None)
    return raw_form.strip().upper() if raw_form else None

def fetch_and_store_sec_filings():
    """Fetches latest SEC filings from RSS feed and stores them in PostgreSQL."""
    logging.info("Starting SEC EDGAR RSS feed fetch...")
    feed_content = None

    # --- Use requests library to fetch content first ---
    for attempt in range(3): # Try up to 3 times
        try:
            response = requests.get(SEC_RSS_URL, headers=REQUEST_HEADERS, timeout=20)
            response.raise_for_status()
            feed_content = response.content
            break # Success, exit loop
        except requests.exceptions.RequestException as e:
            logging.warning(f"Attempt {attempt + 1}/3: Failed to fetch feed. Error: {e}. Retrying in 5 seconds...")
            time.sleep(5)

    if not feed_content:
        logging.error("Could not fetch RSS feed after multiple attempts.")
        return

    # Now parse the content we successfully fetched
    feed = feedparser.parse(feed_content)

    if feed.bozo:
        logging.error(f"Error parsing RSS feed content: {feed.bozo_exception}")
        return

    conn = get_db_connection()
    if not conn:
        return

    added_count = 0
    try:
        with conn.cursor() as cur:
            for entry in reversed(feed.entries): # Process oldest first
                parsed_title = parse_filing_title(entry.title)
                if not parsed_title:
                    logging.warning(f"Could not parse title: {entry.title}")
                    continue

                form_type = determine_form_type(entry, parsed_title)
                if not form_type:
                    logging.warning(f"Could not determine form type for entry: {entry.title}")
                    continue

                # Apply the form type filter if it's not empty
                if FORM_TYPE_FILTER and form_type.upper() not in FORM_TYPE_FILTER:
                    continue

                filing_url = entry.link
                filing_date_parsed = entry.get("updated_parsed")

                if filing_date_parsed:
                    filing_date = datetime.fromtimestamp(time.mktime(filing_date_parsed), tz=timezone.utc)
                else:
                    filing_date = datetime.now(timezone.utc)

                insert_query = """
                INSERT INTO sec_filings (cik, company_name, form_type, filing_date, filing_url)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (filing_url) DO NOTHING;
                """

                try:
                    cur.execute(insert_query, (
                        parsed_title['cik'],
                        parsed_title['company_name'],
                        form_type,
                        filing_date,
                        filing_url
                    ))
                    if cur.rowcount > 0:
                        added_count += 1
                        logging.info(f"  > New Filing: {parsed_title['form_type']} for {parsed_title['company_name']}")
                except Exception as e:
                    logging.error(f"Database insert failed for URL {filing_url}. Error: {e}")
                    conn.rollback() # Rollback this specific failed transaction

        conn.commit()
    except Exception as e:
        logging.error(f"An error occurred during database operations: {e}")
        conn.rollback()
    finally:
        if conn:
            conn.close()

    logging.info(f"SEC filing fetch complete. Added {added_count} new filings.")
    touch_heartbeat('SEC EDGAR Reader')


if __name__ == "__main__":
    setup_logging()
    logging.info("--- Starting EDGAR RSS Reader ---")

    # Run once immediately
    fetch_and_store_sec_filings()

    # Schedule based on configurable interval
    schedule.every(POLL_INTERVAL_MINUTES).minutes.do(fetch_and_store_sec_filings)
    logging.info(f"Scheduled EDGAR filing checks every {POLL_INTERVAL_MINUTES} minutes.")

    while True:
        schedule.run_pending()
        time.sleep(60)

