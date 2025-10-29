"""
Automated Twitter Cookie Refresh using Chrome (Undetected)
Uses undetected-chromedriver to bypass Twitter's bot detection
Supports automated login for all accounts
"""

import json
import time
import sys
import os
from pathlib import Path
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# Path to cookies.json
COOKIES_PATH = Path(__file__).parent.parent / "cookies" / "cookies.json"

# Required cookies for twikit
REQUIRED_COOKIES = [
    'auth_token',
    'ct0',
    'guest_id',
    'guest_id_ads',
    'guest_id_marketing',
    'kdt',
    'lang',
    'personalization_id',
    'twid',
    'g_state',
    '__cuid',
    '__cf_bm'
]

def refresh_cookies(headless=False, account_email=None, account_password=None, account_username=None):
    """
    Launch Chrome with undetected-chromedriver, navigate to X/Twitter, extract cookies

    Args:
        headless: Run Chrome in headless mode (default: False)
        account_email: Email for automated login (optional)
        account_password: Password for automated login (optional)

    Returns:
        dict: Extracted cookies formatted for twikit
    """
    print("[Cookie Refresh] Starting Chrome (undetected mode)...")

    # Configure Chrome options
    options = uc.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1024,768')

    if headless:
        options.add_argument('--headless=new')

    # Initialize undetected Chrome driver
    driver = None
    try:
        # Use version 141 to match current Chrome installation
        driver = uc.Chrome(options=options, version_main=141, use_subprocess=True)

        # Automated login if credentials provided
        if account_email and account_password:
            print("[Cookie Refresh] Performing automated login...")
            driver.get("https://x.com/i/flow/login")
            time.sleep(4)  # Wait for page to fully load

            # Enter email/username
            try:
                print("[Cookie Refresh] Waiting for username field...")
                username_input = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"]'))
                )
                time.sleep(1)  # Human-like delay

                # Type slowly like a human
                for char in account_email:
                    username_input.send_keys(char)
                    time.sleep(0.1)

                print(f"[Cookie Refresh] Entered email: {account_email}")
                time.sleep(2)

                # Click Next
                print("[Cookie Refresh] Clicking Next...")
                next_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//span[text()="Next"]'))
                )
                next_button.click()
                time.sleep(3)

                # Check for username verification challenge (bot detection)
                if account_username:
                    try:
                        print("[Cookie Refresh] Checking for verification challenge...")
                        verification_input = driver.find_element(By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]')
                        if verification_input:
                            print("[Cookie Refresh] Verification challenge detected! Entering username...")
                            for char in account_username:
                                verification_input.send_keys(char)
                                time.sleep(0.1)
                            time.sleep(2)
                            verify_button = driver.find_element(By.XPATH, '//span[text()="Next"]')
                            verify_button.click()
                            print("[Cookie Refresh] Username verification submitted")
                            time.sleep(3)
                    except:
                        # No verification challenge, continue normally
                        pass

                # Enter password
                print("[Cookie Refresh] Waiting for password field...")
                password_input = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]'))
                )
                time.sleep(1)

                # Type password slowly
                for char in account_password:
                    password_input.send_keys(char)
                    time.sleep(0.1)

                print("[Cookie Refresh] Entered password")
                time.sleep(2)

                # Click Login
                print("[Cookie Refresh] Clicking Log in...")
                login_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//span[text()="Log in"]'))
                )
                login_button.click()
                print("[Cookie Refresh] Login submitted, waiting for redirect...")
                time.sleep(8)  # Wait for login to complete

            except Exception as e:
                print(f"[Cookie Refresh] Login automation failed: {e}")
                print("[Cookie Refresh] Waiting for manual login (30 seconds)...")
                time.sleep(30)

        else:
            # No credentials - navigate to home (user must be logged in)
            print("[Cookie Refresh] Navigating to x.com...")
            driver.get("https://x.com/home")

        # Wait for page to load (look for the X logo or home timeline)
        print("[Cookie Refresh] Waiting for page to load...")
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="SideNav_NewTweet_Button"]'))
            )
            print("[Cookie Refresh] Page loaded successfully!")
        except:
            # If specific element not found, just wait a bit longer
            print("[Cookie Refresh] Waiting additional time for page load...")
            time.sleep(5)

        # Extract cookies
        print("[Cookie Refresh] Extracting cookies...")
        selenium_cookies = driver.get_cookies()

        # Convert to twikit format
        cookie_dict = {}
        for cookie in selenium_cookies:
            name = cookie['name']
            if name in REQUIRED_COOKIES:
                cookie_dict[name] = cookie['value']

        # Check if we got the critical cookies
        if 'auth_token' not in cookie_dict:
            print("[ERROR] Critical cookie 'auth_token' not found!")
            print("[ERROR] Make sure you're logged into Twitter in Firefox")
            return None

        if 'ct0' not in cookie_dict:
            print("[ERROR] Critical cookie 'ct0' not found!")
            return None

        print(f"[Cookie Refresh] Successfully extracted {len(cookie_dict)} cookies")
        return cookie_dict

    except Exception as e:
        print(f"[ERROR] Cookie refresh failed: {e}")
        return None

    finally:
        if driver:
            print("[Cookie Refresh] Closing Chrome...")
            driver.quit()

def save_cookies(cookie_dict):
    """Save cookies to cookies.json in twikit format"""
    if not cookie_dict:
        return False

    try:
        with open(COOKIES_PATH, 'w') as f:
            json.dump(cookie_dict, f, indent=2)
        print(f"[Cookie Refresh] Cookies saved to {COOKIES_PATH}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save cookies: {e}")
        return False

def main():
    """Main function for standalone execution"""
    print("="*60)
    print("Twitter Cookie Refresh - Undetected Chrome")
    print("="*60)

    # Check if cookies.json exists (for backup)
    if COOKIES_PATH.exists():
        print("[INFO] Backing up existing cookies.json...")
        backup_path = COOKIES_PATH.parent / "cookies.json.backup"
        with open(COOKIES_PATH, 'r') as f:
            backup = f.read()
        with open(backup_path, 'w') as f:
            f.write(backup)
        print(f"[INFO] Backup saved to {backup_path}")

    # Refresh cookies
    cookies = refresh_cookies(headless=False)

    if cookies:
        success = save_cookies(cookies)
        if success:
            print("\n[SUCCESS] Cookies refreshed successfully!")
            print("[INFO] Your Twitter scrapers can now use the new cookies")
            return 0
        else:
            print("\n[FAILED] Could not save cookies")
            return 1
    else:
        print("\n[FAILED] Could not extract cookies")
        print("[INFO] Make sure you're logged into Twitter in Firefox")
        return 1

if __name__ == "__main__":
    sys.exit(main())