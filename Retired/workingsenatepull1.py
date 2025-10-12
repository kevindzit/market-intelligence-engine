from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import time

def main():
    url = "https://efdsearch.senate.gov/search/home/"
    options = webdriver.ChromeOptions()
    # Uncomment below line if you want headless mode:
    # options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 25)

    try:
        driver.get(url)

        # --- 1) Accept agreement ---
        checkbox = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='checkbox']")))
        checkbox.click()

        # --- 2) Wait for redirect to /search/ page ---
        wait.until(EC.url_contains("/search/"))

        # --- 3) Compute date range (3 days ago → today) ---
        today = datetime.now()
        three_days_ago = today - timedelta(days=3)
        today_str = today.strftime("%m/%d/%Y")
        three_days_ago_str = three_days_ago.strftime("%m/%d/%Y")

        # --- 4) Fill in the 'From' and 'To' date fields ---
        from_date = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[contains(@id,'fromDate')]")))
        to_date = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[contains(@id,'toDate')]")))

        from_date.clear()
        from_date.send_keys(three_days_ago_str)
        to_date.clear()
        to_date.send_keys(today_str)

        # --- 5) Click 'Search Reports' button ---
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Search Reports')]")))
        search_button.click()

        print(f"✅ Date range entered: {three_days_ago_str} → {today_str}")

        # --- 6) Wait for the results table to appear ---
        results_table = wait.until(EC.presence_of_element_located((By.ID, "filedReports")))

        # --- 7) Click the first 'Periodic Transaction Report' link ---
        first_report_link = wait.until(EC.element_to_be_clickable((
            By.XPATH, "//a[contains(text(), 'Periodic Transaction Report')]"
        )))
        first_report_link.click()

        print("✅ Clicked the first 'Periodic Transaction Report' link successfully.")
        print("👉 Browser will stay open for 10 seconds so you can verify.")
        time.sleep(10)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
