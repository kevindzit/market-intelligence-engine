"""
Automated Twitter Cookie Refresh using Firefox
Uses your actual Firefox profile where you're already logged in
Simple and reliable - no need to re-login
"""

import json
import time
import sys
import os
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.firefox import GeckoDriverManager

# Path to cookies.json
COOKIES_PATH = Path(__file__).parent.parent / "cookies.json"

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

def get_firefox_profile_path():
    """Find the default Firefox profile path where user is logged in"""
    if sys.platform == "win32":
        # Windows path
        firefox_profiles = Path(os.environ['APPDATA']) / "Mozilla" / "Firefox" / "Profiles"
    else:
        # Linux/Mac
        firefox_profiles = Path.home() / ".mozilla" / "firefox"

    if firefox_profiles.exists():
        # Look for default profile (usually ends with .default-release)
        for profile_dir in firefox_profiles.glob("*.default-release"):
            return str(profile_dir)
        # Fallback to any profile
        for profile_dir in firefox_profiles.glob("*.default"):
            return str(profile_dir)
    return None

def refresh_cookies(headless=False, use_existing_profile=True):
    """
    Launch Firefox, navigate to X/Twitter, extract cookies

    Args:
        headless: Run Firefox in headless mode (default: False)
        use_existing_profile: Use your logged-in Firefox profile (default: True)

    Returns:
        dict: Extracted cookies formatted for twikit
    """
    print("[Cookie Refresh] Starting Firefox...")

    # Configure Firefox options
    options = Options()

    if headless:
        options.add_argument('--headless')

    # Use existing Firefox profile where you're logged in
    if use_existing_profile:
        profile_path = get_firefox_profile_path()
        if profile_path:
            print(f"[Cookie Refresh] Using Firefox profile: {Path(profile_path).name}")
            options.add_argument('-profile')
            options.add_argument(profile_path)
        else:
            print("[WARN] Could not find Firefox profile, using fresh profile")

    # Initialize Firefox driver
    driver = None
    try:
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
        driver.set_window_size(1024, 768)

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
            print("[Cookie Refresh] Closing Firefox...")
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
    print("Twitter Cookie Refresh - Firefox Edition")
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