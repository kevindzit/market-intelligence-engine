import re
import time
import logging
from datetime import datetime, timedelta

import psycopg2
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- DB CONFIG (keep your values) ----------------
DB_NAME = "your_db_name"
DB_USER = "your_db_user"
DB_PASS = "your_db_password"
DB_HOST = "localhost"
DB_PORT = "54594"   # same external port you used

# ---------------- SETTINGS ----------------
TARGET_REPORT_TYPES = [
    "Periodic Transaction Report",
    "Annual Report",
    "Candidate Report",
    "Termination Report",
]
DAYS_TO_SEARCH = 10
HEADLESS = False  # set True if you want maximum speed

# ---------------- LOGGING ----------------
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

# ---------------- DATA CLEAN ----------------
def clean_data(rows):
    out = []
    for t in rows:
        try:
            m = re.search(r"(\d{2}/\d{2}/\d{4})", t["filing_date"])
            if m:
                t["filing_date"] = datetime.strptime(m.group(1), "%m/%d/%Y").date()
            t["transaction_date"] = datetime.strptime(t["transaction_date"], "%m/%d/%Y").date()
            tick = (t["ticker"] or "").split("\n")[0]
            t["ticker"] = re.sub(r"\s*\(.*\)", "", tick).strip() if tick else "N/A"
            t["filer_name"] = t["filer_name"].replace("The Honorable ", "").split("(")[0].strip()
            out.append(t)
        except Exception as e:
            logging.error(f"clean skip: {e} | {t}")
    return out

# ---------------- SAVE ----------------
def save_to_db(rows):
    if not rows:
        logging.info("No new transactions to save.")
        return
    conn = None
    inserted = 0
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
        )
        cur = conn.cursor()
        sql = """
        INSERT INTO congressional_trades
        (source, filer_name, filing_date, transaction_date, ticker, transaction_type, amount_range, report_url)
        VALUES (%(source)s, %(filer_name)s, %(filing_date)s, %(transaction_date)s, %(ticker)s, %(transaction_type)s, %(amount_range)s, %(report_url)s)
        ON CONFLICT (filer_name, transaction_date, ticker, transaction_type, amount_range) DO NOTHING;
        """
        for t in rows:
            cur.execute(sql, t)
            if cur.rowcount > 0:
                inserted += 1
        conn.commit()
        cur.close()
        logging.info(f"Inserted {inserted} rows.")
    except Exception as e:
        logging.error(f"DB error: {e}")
    finally:
        if conn:
            conn.close()

# ---------------- SELENIUM HELPERS ----------------
def build_driver():
    opts = webdriver.ChromeOptions()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.page_load_strategy = "eager"
    # small speed-ups
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)
    drv = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    drv.set_page_load_timeout(30)
    return drv

def collect_report_links(driver, wait):
    links = []
    logging.info("Collecting report links from all pages...")
    while True:
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//table[@id='filedReports']/tbody/tr")))
            rows = driver.find_elements(By.XPATH, "//table[@id='filedReports']/tbody/tr")
            for r in rows:
                tds = r.find_elements(By.TAG_NAME, "td")
                if len(tds) > 3:
                    txt = tds[3].text
                    a = tds[3].find_element(By.TAG_NAME, "a")
                    href = a.get_attribute("href")
                    if any(t in txt for t in TARGET_REPORT_TYPES) and "/paper/" not in href:
                        links.append(href)
            next_btn = driver.find_element(By.ID, "filedReports_next")
            if "disabled" in next_btn.get_attribute("class"):
                logging.info("Last page reached.")
                break
            next_btn.click()
            time.sleep(1.0)
        except (TimeoutException, NoSuchElementException):
            break
    logging.info(f"Collected {len(links)} links.")
    return links

def get_table_on_page(driver, wait):
    # normal view by headers
    header_xpath = ("(//table[.//th[contains(.,'Transaction Date')] "
                    "and .//th[contains(.,'Owner')] "
                    "and .//th[contains(.,'Amount')]])[1]")
    try:
        return wait.until(EC.presence_of_element_located((By.XPATH, header_xpath)))
    except TimeoutException:
        # some long forms (Part 4)
        try:
            return wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[starts-with(@id,'part4')]//table[.//th]")))
        except TimeoutException:
            return None

def get_table_via_print(driver, wait):
    try:
        parent = driver.current_window_handle
        before = set(driver.window_handles)
        pr = driver.find_element(By.XPATH, "//a[contains(.,'Print Report')] | //button[contains(.,'Print Report')]")
        pr.click()
        time.sleep(0.8)
        after = set(driver.window_handles)
        opened = list(after - before)
        if opened:
            driver.switch_to.window(opened[-1])
        tbl = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//table[.//th[contains(.,'Transaction Date')]]"))
        )
        # filer / date from print page (reliable)
        try:
            filer_name = driver.find_element(By.XPATH, "(//h1)[1]").text.strip()
        except Exception:
            filer_name = "Unknown"
        page_text = driver.find_element(By.TAG_NAME, "body").text
        m = re.search(r"Filed\s+(\d{2}/\d{2}/\d{4})", page_text)
        filing_date_text = f"Filed {m.group(1)}" if m else "Filed N/A"

        # close print tab if we opened one
        if opened:
            driver.close()
            driver.switch_to.window(parent)

        return tbl, filer_name, filing_date_text
    except Exception:
        return None, None, None

# ---------------- SCRAPE ----------------
def scrape_senate_disclosures(days_to_search=DAYS_TO_SEARCH):
    logging.info("--- Starting Senate Scraper ---")
    driver = build_driver()
    wait = WebDriverWait(driver, 15)
    all_tx = []

    try:
        driver.get("https://efdsearch.senate.gov/search/home/")
        wait.until(EC.element_to_be_clickable((By.ID, "agree_statement"))).click()

        today = datetime.now()
        start = today - timedelta(days=days_to_search)
        wait.until(EC.element_to_be_clickable((By.ID, "fromDate"))).send_keys(start.strftime("%m/%d/%Y"))
        wait.until(EC.element_to_be_clickable((By.ID, "toDate"))).send_keys(today.strftime("%m/%d/%Y"))
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Search Reports')]"))).click()
        logging.info(f"Search submitted for date range: {start:%m/%d/%Y} → {today:%m/%d/%Y}")
        time.sleep(1.2)

        links = collect_report_links(driver, wait)
        logging.info(f"Scraping details from {len(links)} reports...")

        for link in links:
            try:
                driver.get(link)

                # ensure page rendered something
                wait.until(EC.presence_of_element_located((
                    By.XPATH, "//h1 | //a[contains(.,'Print Report')] | //button[contains(.,'Print Report')]"
                )))

                # filer name + filing date from live view (best-effort)
                try:
                    filer_name = driver.find_element(By.XPATH, "(//h1)[1]").text.strip()
                except NoSuchElementException:
                    filer_name = "Unknown"
                body_text = driver.find_element(By.TAG_NAME, "body").text
                m = re.search(r"Filed\s+(\d{2}/\d{2}/\d{4})", body_text)
                filing_date_text = f"Filed {m.group(1)}" if m else "Filed N/A"

                table = get_table_on_page(driver, wait)
                if table is None:
                    table, pn, pd = get_table_via_print(driver, wait)
                    if table is None:
                        logging.warning(f"timeout on {link}")
                        continue
                    if pn:
                        filer_name = pn
                    if pd:
                        filing_date_text = pd

                rows = table.find_elements(By.XPATH, ".//tbody/tr[td]")
                for r in rows:
                    tds = r.find_elements(By.TAG_NAME, "td")
                    if len(tds) >= 8:
                        all_tx.append({
                            "source": "senate",
                            "filer_name": filer_name,
                            "filing_date": filing_date_text,
                            "transaction_date": tds[1].text.strip(),
                            "ticker": tds[3].text.strip(),
                            "transaction_type": tds[6].text.strip(),
                            "amount_range": tds[7].text.strip(),
                            "report_url": link
                        })

            except TimeoutException:
                logging.warning(f"timeout on {link}")
            except Exception as e:
                logging.error(f"detail error on {link}: {e}")

    finally:
        driver.quit()
        logging.info("--- Scraper Finished ---")

    return all_tx

# ---------------- MAIN ----------------
if __name__ == "__main__":
    setup_logging()
    raw = scrape_senate_disclosures()
    if raw:
        logging.info(f"Scraped {len(raw)} raw transactions. Cleaning...")
        cleaned = clean_data(raw)
        logging.info(f"{len(cleaned)} passed cleaning. Saving to DB...")
        save_to_db(cleaned)
    else:
        logging.info("No transactions found.")
