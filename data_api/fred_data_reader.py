import logging
import schedule
import time
import psycopg2
from fredapi import Fred

# --- Configuration ---
FRED_API_KEY = "0a463bcea9719e4351642c5dd9ce4cde"

# PostgreSQL Connection Details (same as your other scripts)
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASS = "postgres"
DB_HOST = "localhost"
DB_PORT = "54594"

# --- Key Economic Indicators to Track ---
# We can add more to this dictionary later.
INDICATORS = {
    "GDP": "Gross Domestic Product",
    "UNRATE": "Unemployment Rate",
    "DFF": "Federal Funds Effective Rate",
    "CPIAUCSL": "Consumer Price Index (Inflation)"
}

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

def fetch_and_store_fred_data():
    """Fetches latest data for specified indicators from FRED and stores them in PostgreSQL."""
    logging.info("Starting FRED data fetch...")
    fred = Fred(api_key=FRED_API_KEY)
    conn = get_db_connection()
    if not conn:
        return

    total_added_count = 0
    try:
        with conn.cursor() as cur:
            for code, name in INDICATORS.items():
                logging.info(f"Fetching latest data for {name} ({code})...")
                try:
                    # Get the most recent data point for the series
                    data = fred.get_series_latest_release(code)
                    if data.empty:
                        logging.warning(f"No data returned for {code}.")
                        continue

                    # The result is a pandas Series, get the last (most recent) value
                    latest_date = data.index[-1].date()
                    
                    # *** THIS IS THE FIX ***
                    # Convert the numpy float to a standard Python float before saving
                    latest_value = float(data.iloc[-1])

                    # Insert into the database, ignoring duplicates
                    insert_query = """
                    INSERT INTO economic_indicators (indicator_code, date, value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (indicator_code, date) DO NOTHING;
                    """
                    cur.execute(insert_query, (code, latest_date, latest_value))

                    if cur.rowcount > 0:
                        total_added_count += 1
                        logging.info(f"  > New data for {code} on {latest_date}: {latest_value}")

                except Exception as e:
                    logging.error(f"Failed to fetch or store data for {code}. Error: {e}")
                
                time.sleep(1) # Be polite to the API

        conn.commit()
    except Exception as e:
        logging.error(f"An error occurred during database operations: {e}")
        conn.rollback()
    finally:
        if conn:
            conn.close()

    logging.info(f"FRED data fetch complete. Added {total_added_count} new data points.")

if __name__ == "__main__":
    setup_logging()
    logging.info("--- Starting FRED Data Reader ---")

    # Run once immediately
    fetch_and_store_fred_data()

    # Schedule to run once a day (economic data doesn't update frequently)
    schedule.every().day.at("08:00").do(fetch_and_store_fred_data)
    logging.info("Scheduled FRED data fetching every day at 8:00 AM.")

    while True:
        schedule.run_pending()
        time.sleep(60)

