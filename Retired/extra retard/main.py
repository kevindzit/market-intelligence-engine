from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
import time

def scrape_senate_disclosures(days_to_search=3):
    print("--- Starting Senate Scraper ---")
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless=new")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)
    all_transactions = []

    try:
        # --- This is your successful navigation and search logic, unchanged ---
        url = "https://efdsearch.senate.gov/search/home/"
        driver.get(url)
        checkbox = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='checkbox']")))
        checkbox.click()
        wait.until(EC.url_contains("/search/"))
        
        today = datetime.now()
        start_date = today - timedelta(days=days_to_search)
        today_str = today.strftime("%m/%d/%Y")
        start_date_str = start_date.strftime("%m/%d/%Y")
        
        from_date = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[contains(@id,'fromDate')]")))
        to_date = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[contains(@id,'toDate')]")))
        from_date.clear()
        from_date.send_keys(start_date_str)
        to_date.clear()
        to_date.send_keys(today_str)
        
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Search Reports')]")))
        search_button.click()
        print(f"✅ Search submitted for date range: {start_date_str} → {today_str}")

        # STAGE 1: Collect all the report links from the results page
        report_links = []
        try:
            results_table = wait.until(EC.presence_of_element_located((By.ID, "filedReports")))
            links = results_table.find_elements(By.XPATH, ".//a[contains(text(), 'Periodic Transaction Report')]")
            for link in links:
                report_links.append(link.get_attribute("href"))
            print(f"✅ Found {len(report_links)} periodic transaction reports.")
        except Exception:
            print("No periodic transaction reports found for this date range.")
            return []

        # STAGE 2: Loop through each link and scrape the detail page
        print(f"Scraping details from {len(report_links)} reports...")
        for link in report_links:
            driver.get(link)
            
            # --- ADDED RELIABILITY: Wait for the detail table to load ---
            wait.until(EC.presence_of_element_located((By.ID, "transaction-data")))
            
            filer_name_header = driver.find_element(By.TAG_NAME, "h1").text
            transaction_rows = driver.find_elements(By.XPATH, "//div[@id='transaction-data']/table/tbody/tr")

            for transaction in transaction_rows:
                columns = transaction.find_elements(By.TAG_NAME, "td")

                # --- THIS IS THE FIX: The table has 9 columns ---
                if len(columns) == 9:
                    all_transactions.append({
                        "source": "senate",
                        "filer_name": filer_name_header.replace("The Honorable ", "").strip(),
                        "filing_date": None,
                        "transaction_date": columns[1].text,
                        "ticker": columns[3].text,
                        "transaction_type": columns[6].text,
                        "amount_range": columns[7].text,
                        "report_url": link
                    })
    finally:
        driver.quit()
        print("\n--- Scraper Finished ---")
    
    return all_transactions

if __name__ == "__main__":
    scraped_data = scrape_senate_disclosures(days_to_search=3)
    
    if scraped_data:
        print(f"\n>>> SUCCESS! Scraped a total of {len(scraped_data)} individual transactions. <<<")
        for transaction in scraped_data:
            print(transaction)
    else:
        print("\n>>> No transactions were found or scraped. <<<")