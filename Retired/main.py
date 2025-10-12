from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

def scrape_senate_disclosures(start_date: str, end_date: str):
    """
    Scrape U.S. Senate financial disclosures between two dates.

    Args:
        start_date (str): Format "MM/DD/YYYY"
        end_date (str): Format "MM/DD/YYYY"

    Returns:
        list[dict]: List of filings with:
            first_name, last_name, report_type, date_filed, report_link
    """
    url = "https://efdsearch.senate.gov/search/home/"
    results = []

    # --- Setup Chrome driver ---
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)

    try:
        # --- Step 1: Navigate to page ---
        driver.get(url)

        # --- Step 2: Accept consent ---
        checkbox = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='checkbox']")))
        checkbox.click()
        enter_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Enter Site')]")))
        enter_btn.click()

        # --- Step 3: Wait for search form + switch into iframe ---
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "ifrmFileHere")))

        # --- Step 4: Fill out first and last name fields ---
        first_name_field = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//input[contains(@placeholder, 'First name') or contains(@aria-label, 'First name')]")
        ))
        last_name_field = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//input[contains(@placeholder, 'Last name') or contains(@aria-label, 'Last name')]")
        ))

        # Example: fill for “Nancy Pelosi” (you can change these)
        first_name_field.clear()
        first_name_field.send_keys("Nancy")
        last_name_field.clear()
        last_name_field.send_keys("Pelosi")

        # --- Step 5: Click “Periodic Transactions” ---
        periodic_box = wait.until(EC.element_to_be_clickable((
            By.XPATH, "//input[@type='checkbox' and (contains(@id,'periodic') or contains(@name,'periodic'))]"
        )))
        if not periodic_box.is_selected():
            periodic_box.click()

        # --- Step 6: Enter date range ---
        from_field = wait.until(EC.element_to_be_clickable((By.ID, "filedFromDate")))
        to_field = wait.until(EC.element_to_be_clickable((By.ID, "filedToDate")))

        from_field.clear()
        from_field.send_keys(start_date)
        to_field.clear()
        to_field.send_keys(end_date)

        # --- Step 7: Click “Search Reports” ---
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Search Reports')]")))
        search_button.click()

        # --- Step 8: Wait for results table ---
        table = wait.until(EC.presence_of_element_located((By.ID, "filedReports")))

        # --- Step 9: Scrape table rows ---
        rows = table.find_elements(By.XPATH, ".//tbody/tr")
        for row in rows:
            try:
                first_name_elem = row.find_element(By.XPATH, ".//td[1]/a")
                last_name_elem = row.find_element(By.XPATH, ".//td[2]")
                report_type_elem = row.find_element(By.XPATH, ".//td[3]")
                date_filed_elem = row.find_element(By.XPATH, ".//td[4]")

                first_name = first_name_elem.text.strip()
                last_name = last_name_elem.text.strip()
                report_type = report_type_elem.text.strip()
                date_filed = date_filed_elem.text.strip()
                report_link = first_name_elem.get_attribute("href")

                results.append({
                    "first_name": first_name,
                    "last_name": last_name,
                    "report_type": report_type,
                    "date_filed": date_filed,
                    "report_link": report_link
                })
            except Exception:
                continue

    finally:
        driver.quit()

    return results


# Example run
if __name__ == "__main__":
    data = scrape_senate_disclosures("09/01/2024", "09/30/2024")
    for record in data[:5]:
        print(record)
