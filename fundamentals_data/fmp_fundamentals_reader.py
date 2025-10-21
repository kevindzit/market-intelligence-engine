import requests
import logging
import schedule
import time
import psycopg2
from datetime import datetime, timezone

# --- Configuration ---
FMP_API_KEY = "Scqx3sMK3VClLLA3iaxar0tYwZOeX30y"

# PostgreSQL Connection Details
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASS = "postgres"
DB_HOST = "localhost"
DB_PORT = "54594"

# --- List of Tickers to Monitor ---
# A diverse list of major companies and key ETFs.
TICKERS_TO_MONITOR = [
    # Big Tech / Growth
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # Financials
    "JPM", "BAC", "V",
    # Healthcare
    "UNH", "JNJ", "LLY",
    # Energy
    "XOM", "CVX",
    # Consumer
    "WMT", "PG", "KO", "HD",
    # Industrials
    "CAT", "BA",
    # Market Index ETFs
    "SPY", "QQQ"
]

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

def fetch_and_store_fundamentals():
    """Fetches company profiles from FMP and stores/updates them in PostgreSQL."""
    logging.info("Starting company fundamentals fetch from FMP...")
    conn = get_db_connection()
    if not conn:
        return

    updated_count = 0
    
    try:
        with conn.cursor() as cur:
            for ticker in TICKERS_TO_MONITOR:
                logging.info(f"Fetching profile for {ticker}...")
                try:
                    url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={FMP_API_KEY}"
                    response = requests.get(url, timeout=20)
                    response.raise_for_status()
                    data = response.json()

                    if not data:
                        logging.warning(f"No data returned for {ticker}.")
                        continue
                    
                    # FMP returns a list, even for a single ticker
                    profile = data[0]

                    # SQL to insert a new company or update an existing one
                    upsert_query = """
                    INSERT INTO company_profiles (
                        symbol, company_name, exchange, industry, sector,
                        market_cap, beta, pe_ratio, eps, website, last_updated
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        company_name = EXCLUDED.company_name,
                        exchange = EXCLUDED.exchange,
                        industry = EXCLUDED.industry,
                        sector = EXCLUDED.sector,
                        market_cap = EXCLUDED.market_cap,
                        beta = EXCLUDED.beta,
                        pe_ratio = EXCLUDED.pe_ratio,
                        eps = EXCLUDED.eps,
                        website = EXCLUDED.website,
                        last_updated = EXCLUDED.last_updated;
                    """

                    cur.execute(upsert_query, (
                        profile.get('symbol'),
                        profile.get('companyName'),
                        profile.get('exchangeShortName'),
                        profile.get('industry'),
                        profile.get('sector'),
                        profile.get('mktCap'),
                        profile.get('beta'),
                        profile.get('price') / profile.get('eps') if profile.get('eps') and profile.get('price') else None, # Calculate P/E
                        profile.get('eps'),
                        profile.get('website'),
                        datetime.now(timezone.utc)
                    ))
                    updated_count += 1
                    logging.info(f"  > Successfully upserted data for {ticker}.")

                except requests.exceptions.HTTPError as e:
                    logging.error(f"HTTP error for {ticker}. Maybe a free tier limit or invalid symbol? Error: {e}")
                except Exception as e:
                    logging.error(f"Failed to fetch or store data for {ticker}. Error: {e}")

                time.sleep(1) # Be polite to the API to avoid rate limiting

        conn.commit()
    except Exception as e:
        logging.error(f"An error occurred during database operations: {e}")
        conn.rollback()
    finally:
        if conn:
            conn.close()

    logging.info(f"Fundamentals fetch complete. Upserted data for {updated_count} companies.")


if __name__ == "__main__":
    setup_logging()
    logging.info("--- Starting FMP Fundamentals Reader ---")

    # Run once immediately
    fetch_and_store_fundamentals()

    # Schedule to run once per day
    schedule.every().day.at("07:00").do(fetch_and_store_fundamentals)
    logging.info("Scheduled fundamentals fetching every day at 7:00 AM.")

    while True:
        schedule.run_pending()
        time.sleep(60)
