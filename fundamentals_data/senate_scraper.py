import psycopg2
import re
import time
import logging
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, NoSuchWindowException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

try:
    from scraper_utils.heartbeat import touch_heartbeat
except ImportError:
    def touch_heartbeat(_: str):
        pass

# Load environment variables
load_dotenv()

# --- DATABASE DETAILS ---
DB_NAME = os.getenv('DB_NAME', 'pjx')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASSWORD', 'postgres')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594') 

# --- CONFIGURATION ---
# Only track actual buy/sell transactions (Periodic Transaction Reports)
# Annual/Candidate/Termination reports have different table structures (holdings, not transactions)
TARGET_REPORT_TYPES = [
    "Periodic Transaction Report"
]

def setup_logging():
    """Sets up the logging configuration."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='logs/senate_scraper.log', filemode='w')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

def clean_data(transactions):
    """Cleans and formats the scraped data."""
    cleaned_transactions = []
    for t in transactions:
        try:
            filing_date_str = re.search(r'(\d{2}/\d{2}/\d{4})', t['filing_date']).group(1)
            t['filing_date'] = datetime.strptime(filing_date_str, "%m/%d/%Y").date()
            t['transaction_date'] = datetime.strptime(t['transaction_date'], "%m/%d/%Y").date()
            ticker_text = t['ticker'].split('\n')[0]
            t['ticker'] = re.sub(r'\s*\(.*\)', '', ticker_text).strip() if ticker_text else "N/A"
            clean_name = t['filer_name'].replace("The Honorable ", "").replace("Mr. ", "").replace("Ms. ", "")
            t['filer_name'] = clean_name.split('(')[0].strip()
            cleaned_transactions.append(t)
        except Exception as e:
            logging.error(f"Could not clean transaction, skipping. Error: {e}\nData: {t}")
    return cleaned_transactions

def save_to_db(transactions):
    """Saves a list of transactions to the PostgreSQL database."""
    if not transactions:
        logging.info("No new transactions to save.")
        return
    conn = None
    inserted_rows = 0
    try:
        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
        cursor = conn.cursor()
        insert_query = """
        INSERT INTO congressional_trades (source, filer_name, filing_date, transaction_date, ticker, transaction_type, amount_range, report_url)
        VALUES (%(source)s, %(filer_name)s, %(filing_date)s, %(transaction_date)s, %(ticker)s, %(transaction_type)s, %(amount_range)s, %(report_url)s)
        ON CONFLICT (filer_name, transaction_date, ticker, transaction_type, amount_range) DO NOTHING;
        """
        for t in transactions:
            cursor.execute(insert_query, t)
            if cursor.rowcount > 0:
                inserted_rows += 1
        conn.commit()
        cursor.close()
        logging.info(f"Database operation complete. Inserted {inserted_rows} new transactions.")
    except (Exception, psycopg2.Error) as error:
        logging.error(f"Database connection error: {error}")
    finally:
        if conn is not None:
            conn.close()

def scrape_senate_disclosures(days_to_search=10):
    """Main function to scrape Senate disclosures."""
    logging.info("--- Starting Senate Scraper ---")
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless=new")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    all_transactions = []
    
    try:
        url = "https://efdsearch.senate.gov/search/home/"
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "agree_statement"))).click()
        today = datetime.now()
        start_date = today - timedelta(days=days_to_search)
        WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "fromDate"))).send_keys(start_date.strftime("%m/%d/%Y"))
        WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "toDate"))).send_keys(today.strftime("%m/%d/%Y"))
        WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Search Reports')]"))).click()
        logging.info(f"Search submitted for date range: {start_date.strftime('%m/%d/%Y')} → {today.strftime('%m/%d/%Y')}")
        time.sleep(2)

        report_links = []
        logging.info("Collecting report links from all pages...")
        while True:
            try:
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//table[@id='filedReports']/tbody/tr")))
                rows = driver.find_elements(By.XPATH, "//table[@id='filedReports']/tbody/tr")
                for row in rows:
                    columns = row.find_elements(By.TAG_NAME, "td")
                    if len(columns) > 3:
                        report_type_text = columns[3].text
                        link_element = columns[3].find_element(By.TAG_NAME, "a")
                        href = link_element.get_attribute("href")
                        is_target_type = any(target in report_type_text for target in TARGET_REPORT_TYPES)
                        if is_target_type and "/paper/" not in href:
                            report_links.append(href)
                next_button = driver.find_element(By.ID, "filedReports_next")
                if "disabled" in next_button.get_attribute("class"):
                    logging.info("Last page reached.")
                    break
                else:
                    next_button.click()
                    time.sleep(2)
            except (TimeoutException, NoSuchElementException):
                logging.info("No (or no more) reports found.")
                break
        logging.info(f"Collected a total of {len(report_links)} scrapeable report links.")

        logging.info(f"Scraping details from {len(report_links)} reports...")
        for link in report_links:
            try:
                driver.get(link)
                if "/extension-notice/" in driver.current_url or "maintenance" in driver.page_source.lower():
                    continue
                
                try:
                    short_wait = WebDriverWait(driver, 3)
                    transaction_table = short_wait.until(EC.presence_of_element_located(
                        (By.XPATH, "//table[.//th[contains(text(), 'Transaction Date')] and .//th[contains(text(), 'Ticker')]]")
                    ))
                except TimeoutException:
                    logging.info(f"No transaction table found on this page, skipping: {link}")
                    continue

                filer_name_header = driver.find_element(By.TAG_NAME, "h1").text
                filing_date_element = "Filed: Unknown"
                try:
                    filing_date_element = driver.find_element(By.XPATH, "//*[contains(text(), 'Filed')]").text
                except NoSuchElementException:
                    alt_candidates = driver.find_elements(By.XPATH, "//p[contains(text(), 'Filed')]")
                    if alt_candidates:
                        filing_date_element = alt_candidates[0].text
                    else:
                        logging.warning(f"Filed date element missing for {link}, defaulting to 'Unknown'")
                
                transaction_rows = transaction_table.find_elements(By.XPATH, ".//tbody/tr")
                for row in transaction_rows:
                    columns = row.find_elements(By.TAG_NAME, "td")
                    if len(columns) >= 8:
                        all_transactions.append({
                            "source": "senate", "filer_name": filer_name_header,
                            "filing_date": filing_date_element, "transaction_date": columns[1].text,
                            "ticker": columns[3].text, "transaction_type": columns[6].text,
                            "amount_range": columns[7].text, "report_url": link
                        })
            
            except NoSuchWindowException:
                logging.error("Browser window closed unexpectedly. Halting scraper.")
                break
            except Exception as e:
                logging.error(f"Could not scrape detail page {link}. Error: {e}")
    finally:
        driver.quit()
        logging.info("--- Scraper Finished ---")
    
    return all_transactions

if __name__ == "__main__":
    setup_logging()
    raw_transactions = scrape_senate_disclosures()
    if raw_transactions:
        logging.info(f"Scraped {len(raw_transactions)} raw transactions. Cleaning data...")
        cleaned_transactions = clean_data(raw_transactions)
        logging.info(f"{len(cleaned_transactions)} transactions passed cleaning. Saving to database...")
        save_to_db(cleaned_transactions)
    else:
        logging.info("No transactions were found or scraped.")
    touch_heartbeat('Senate Scraper')
