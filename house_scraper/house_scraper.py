import requests
import zipfile
import io
import os
import logging
import re
import time
from datetime import datetime
import psycopg2
from xml.etree import ElementTree as ET
import pdfplumber
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- DATABASE DETAILS ---
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASS = "postgres"
DB_HOST = "localhost"
DB_PORT = "54594"

# --- CONFIGURATION ---
DATA_DIR = "house_data"
PROCESSED_DOCS_FILE = os.path.join(DATA_DIR, "processed_docs.txt")

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='logs/house_scraper.log', filemode='w')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

def get_processed_docs():
    if not os.path.exists(PROCESSED_DOCS_FILE): return set()
    with open(PROCESSED_DOCS_FILE, 'r') as f: return set(line.strip() for line in f)

def log_processed_doc(doc_id):
    with open(PROCESSED_DOCS_FILE, 'a') as f: f.write(f"{doc_id}\n")

def clean_data(transactions):
    cleaned = []
    for t in transactions:
        try:
            # --- Filing Date ---
            filing_date_str = str(t.get('filing_date', ''))
            filing_date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', filing_date_str)
            if filing_date_match:
                t['filing_date'] = datetime.strptime(filing_date_match.group(1), "%m/%d/%Y").date()
            elif not isinstance(t.get('filing_date'), datetime.date):
                raise ValueError("Filing date format is invalid")

            # --- Transaction Date ---
            transaction_date_str = str(t.get('transaction_date', ''))
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', transaction_date_str)
            if not date_match:
                amount_str = str(t.get('amount_range', ''))
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', amount_str)
            if not date_match:
                raise ValueError("Transaction date could not be found or parsed")
            t['transaction_date'] = datetime.strptime(date_match.group(1), "%m/%d/%Y").date()

            # --- Ticker ---
            ticker_text = str(t.get('ticker', 'N/A'))
            # Remove any strange characters and newlines
            ticker_text = re.sub(r'[\x00-\x1f\s]+', ' ', ticker_text).strip()
            # Extract anything that looks like a stock symbol (e.g., in parentheses)
            symbol_match = re.search(r'\(([A-Z]{1,5})\)', ticker_text)
            if symbol_match:
                t['ticker'] = symbol_match.group(1)
            else:
                # If no symbol, take the first part of the text but limit its length
                clean_ticker = re.sub(r'\s*\[.*\]', '', ticker_text).strip()
                t['ticker'] = (clean_ticker[:48] + '..') if len(clean_ticker) > 50 else clean_ticker or "N/A"

            # --- Filer Name ---
            filer_name = t.get('filer_name')
            if filer_name and isinstance(filer_name, str):
                t['filer_name'] = filer_name.replace("Hon. ", "").replace("Mr. ", "").replace("Ms. ", "").split('(')[0].strip()

            cleaned.append(t)
        except Exception as e:
            logging.error(f"Could not clean transaction, skipping. Error: {e}\nData: {t}")
    return cleaned

def save_to_db(transactions):
    if not transactions:
        logging.info("No new transactions to save.")
        return
    conn = None
    try:
        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
        cursor = conn.cursor()
        insert_query = """
        INSERT INTO congressional_trades (source, filer_name, filing_date, transaction_date, ticker, transaction_type, amount_range, report_url)
        VALUES (%(source)s, %(filer_name)s, %(filing_date)s, %(transaction_date)s, %(ticker)s, %(transaction_type)s, %(amount_range)s, %(report_url)s)
        ON CONFLICT (filer_name, transaction_date, ticker, transaction_type, amount_range) DO NOTHING;
        """
        inserted_rows = 0
        for t in transactions:
            cursor.execute(insert_query, t)
            if cursor.rowcount > 0: inserted_rows += 1
        conn.commit()
        cursor.close()
        logging.info(f"Database operation complete. Inserted {inserted_rows} new transactions.")
    except (Exception, psycopg2.Error) as error:
        logging.error(f"Database connection error: {error}")
    finally:
        if conn: conn.close()

def scrape_house_disclosures():
    logging.info("--- Starting House Scraper ---")
    if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

    processed_docs = get_processed_docs()
    all_transactions = []

    year = datetime.now().year
    zip_url = f"https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
    logging.info(f"Downloading index file: {zip_url}")

    try:
        response = requests.get(zip_url, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download index file. Error: {e}")
        return []

    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        with z.open(f'{year}FD.xml') as xml_file:
            root = ET.parse(xml_file).getroot()
            new_filings = [m for m in root.findall('Member') if m.find('FilingType').text == 'P' and m.find('DocID').text not in processed_docs]

    if not new_filings:
        logging.info("No new periodic transaction reports found.")
        return []

    logging.info(f"Found {len(new_filings)} new PTRs to process.")

    driver = None # Initialize driver to None

    for member in new_filings:
        doc_id = member.find('DocID').text
        filer_name = f"{member.find('First').text} {member.find('Last').text}"
        filing_date = member.find('FilingDate').text

        pdf_url = f"https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
        pdf_response = requests.get(pdf_url, timeout=30)

        try:
            if pdf_response.ok:
                logging.info(f"Processing PDF for {filer_name} ({doc_id})")
                with pdfplumber.open(io.BytesIO(pdf_response.content)) as pdf:
                    for page in pdf.pages:
                        tables = page.extract_tables()
                        for table in tables:
                            if table and len(table[0]) > 5 and 'Owner' in table[0] and 'Asset' in table[0]:
                                for row in table[1:]:
                                    all_transactions.append({
                                        "source": "house", "filer_name": filer_name, "filing_date": filing_date,
                                        "transaction_date": row[3], "ticker": row[2], "transaction_type": "Unknown",
                                        "amount_range": row[5], "report_url": pdf_url
                                    })
                log_processed_doc(doc_id)
            else:
                if not driver:
                    options = webdriver.ChromeOptions()
                    # options.add_argument("--headless=new")
                    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

                page_url = f"https://disclosures-clerk.house.gov/FinancialDisclosure/ViewPTR.aspx?did={doc_id}"
                logging.info(f"PDF not found for {doc_id}. Trying webpage: {page_url}")
                driver.get(page_url)

                short_wait = WebDriverWait(driver, 5)
                table = short_wait.until(EC.presence_of_element_located((By.XPATH, "//table")))
                rows = table.find_elements(By.XPATH, ".//tbody/tr")
                for row in rows:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) >= 8:
                        all_transactions.append({
                            "source": "house", "filer_name": filer_name, "filing_date": filing_date,
                            "transaction_date": cols[3].text, "ticker": cols[2].text, "transaction_type": cols[5].text,
                            "amount_range": cols[6].text, "report_url": page_url
                        })
                log_processed_doc(doc_id)

            time.sleep(1)
        except Exception as e:
            logging.error(f"Failed to process DocID {doc_id} for {filer_name}. Error: {e}")

    if driver:
        driver.quit()

    logging.info("--- House Scraper Finished ---")
    return all_transactions

if __name__ == "__main__":
    setup_logging()
    raw_transactions = scrape_house_disclosures()

    if raw_transactions:
        logging.info(f"Scraped {len(raw_transactions)} new raw transactions. Cleaning...")
        cleaned_transactions = clean_data(raw_transactions)
        logging.info(f"{len(cleaned_transactions)} passed cleaning. Saving to DB...")
        save_to_db(cleaned_transactions)
    else:
        logging.info("Finished run. No new transactions were found.")