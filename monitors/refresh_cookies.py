"""
Twitter Cookie Refresh with Cloudflare Handling
Uses undetected-chromedriver to bypass detection
Handles "Something went wrong" error pages
Types character-by-character like a human
"""

import json
import time
import sys
import os
from pathlib import Path
from random import uniform
import traceback

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

# Path to cookies
COOKIES_PATH = Path(__file__).parent.parent / "cookies" / "cookies.json"


def refresh_cookies(headless=False, account_email=None, account_password=None, account_username=None):
    """
    Main cookie refresh function using undetected-chromedriver

    Args:
        headless: Whether to run in headless mode (not recommended for Cloudflare)
        account_email: Twitter account email
        account_password: Twitter account password
        account_username: Twitter username (for verification challenges)
    """

    # Check for lock file to prevent multiple instances
    lock_file = Path(__file__).parent / ".refresh_cookies.lock"
    if lock_file.exists():
        # Check if lock is stale (older than 5 minutes)
        try:
            lock_age = time.time() - lock_file.stat().st_mtime
            if lock_age < 300:  # 5 minutes
                print("[Cookie Refresh] Another instance is already running. Exiting.")
                return None
            else:
                print("[Cookie Refresh] Removing stale lock file...")
                lock_file.unlink()
        except:
            pass

    # Create lock file
    try:
        lock_file.touch()
    except:
        pass

    if not account_email or not account_password:
        print("[Cookie Refresh] ERROR: Email and password required for automated refresh")
        # Clean up lock file
        try:
            lock_file.unlink()
        except:
            pass
        return None

    print("[Cookie Refresh] Starting cookie refresh...")
    print(f"[Cookie Refresh] Account: {account_email}")
    print(f"[Cookie Refresh] Username: {account_username or 'Not provided'}")

    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        print("[Cookie Refresh] Using undetected-chromedriver")

        # Configure Chrome options
        options = uc.ChromeOptions()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--window-size=1280,800')

        # Add stealth arguments
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--disable-accelerated-2d-canvas')
        options.add_argument('--disable-gpu')

        if headless:
            options.add_argument('--headless=new')
            print("[Cookie Refresh] Running in headless mode (may fail on Cloudflare)")

        # Create driver
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=None)

        # Add stealth scripts
        stealth_js = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = {runtime: {}};
        Object.defineProperty(navigator, 'permissions', {
            get: () => ({
                query: () => Promise.resolve({state: 'granted'})
            })
        });
        """
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': stealth_js})

        print("[Cookie Refresh] Navigating to Twitter login...")
        driver.get("https://x.com/i/flow/login")

        # Wait for page load
        time.sleep(5)

        # Handle "Something went wrong" error page with Retry button
        retry_count = 0
        max_retries = 5
        while retry_count < max_retries:
            time.sleep(3)
            page_text = driver.page_source.lower()

            if "something went wrong" in page_text and "try reloading" in page_text:
                print(f"[Cookie Refresh] Error page detected, clicking Retry button (attempt {retry_count + 1}/{max_retries})")

                # Try multiple ways to find and click the Retry button
                retry_clicked = False

                # Method 1: By button text
                try:
                    retry_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Retry') or contains(text(), 'retry') or contains(text(), 'Try again') or contains(text(), 'Reload')]")
                    driver.execute_script("arguments[0].click();", retry_button)
                    retry_clicked = True
                    print("[Cookie Refresh] Clicked Retry button using text search")
                except:
                    pass

                # Method 2: By role and specific selectors
                if not retry_clicked:
                    try:
                        retry_button = driver.find_element(By.CSS_SELECTOR, "button[role='button'], div[role='button']")
                        if "retry" in retry_button.text.lower() or "reload" in retry_button.text.lower() or "try" in retry_button.text.lower():
                            driver.execute_script("arguments[0].click();", retry_button)
                            retry_clicked = True
                            print("[Cookie Refresh] Clicked Retry button using role selector")
                    except:
                        pass

                # Method 3: Find any clickable element with retry-related text
                if not retry_clicked:
                    try:
                        elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Retry') or contains(text(), 'retry') or contains(text(), 'Try again') or contains(text(), 'Reload')]")
                        for elem in elements:
                            if elem.is_displayed() and elem.is_enabled():
                                driver.execute_script("arguments[0].click();", elem)
                                retry_clicked = True
                                print("[Cookie Refresh] Clicked Retry element")
                                break
                    except:
                        pass

                if retry_clicked:
                    print("[Cookie Refresh] Waiting for page to reload...")
                    time.sleep(5)
                else:
                    print("[Cookie Refresh] Could not find Retry button, waiting...")
                    time.sleep(5)

                retry_count += 1
            else:
                # No error page, continue
                break

        if retry_count >= max_retries:
            print(f"[Cookie Refresh] ERROR: Failed to get past error page after {max_retries} attempts")

        # Check if Cloudflare is blocking
        page_text = driver.page_source.lower()
        if "verify you are human" in page_text or "cloudflare" in page_text:
            print("[Cookie Refresh] Cloudflare detected, waiting for it to resolve...")

            # Sometimes Cloudflare auto-solves after a delay
            for i in range(6):
                time.sleep(5)
                page_text = driver.page_source.lower()
                if "verify you are human" not in page_text and "cloudflare" not in page_text:
                    print("[Cookie Refresh] Cloudflare appears to have cleared")
                    break
                print(f"[Cookie Refresh] Waiting for Cloudflare... ({(i+1)*5}s)")
            else:
                print("[Cookie Refresh] WARNING: Cloudflare still blocking after 30s")
                print("[Cookie Refresh] You may need to solve it manually in the browser window")

        # Proceed with login attempt
        print("[Cookie Refresh] Attempting login...")

        # Enter email
        try:
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"], input[name="text"]'))
            )
            username_field.clear()
            username_field.click()  # Click to focus
            time.sleep(0.5)
            # Type character by character like a human with variable speed
            for char in account_email:
                username_field.send_keys(char)
                time.sleep(uniform(0.05, 0.15))  # Random delay 50-150ms for more human-like typing
            print(f"[Cookie Refresh] Entered email: {account_email}")
            time.sleep(2)

            # Click Next
            next_button = driver.find_element(By.XPATH, "//span[text()='Next']/ancestor::button")
            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(3)

            # Check for "Could not log you in now" error
            time.sleep(2)
            page_text = driver.page_source.lower()
            if "could not log you in now" in page_text or "please try again later" in page_text:
                print("[Cookie Refresh] Twitter rate limit detected - 'Could not log you in now'")
                print("[Cookie Refresh] This usually means:")
                print("[Cookie Refresh] 1. Too many login attempts from this IP")
                print("[Cookie Refresh] 2. Need to wait 30-60 minutes before retrying")
                print("[Cookie Refresh] 3. Or try a different account/IP address")
                driver.quit()
                # Clean up lock file
                try:
                    lock_file.unlink()
                except:
                    pass
                return None

        except Exception as e:
            print(f"[Cookie Refresh] Email entry failed: {e}")

        # Handle verification if needed
        if account_username:
            try:
                verification_field = driver.find_element(By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]')
                if verification_field.is_displayed():
                    verification_field.clear()
                    verification_field.click()  # Click to focus
                    time.sleep(0.5)
                    # Type character by character like a human with variable speed
                    for char in account_username:
                        verification_field.send_keys(char)
                        time.sleep(uniform(0.05, 0.15))  # Random delay for more human-like typing
                    print(f"[Cookie Refresh] Entered username verification: {account_username}")
                    time.sleep(2)
                    next_button = driver.find_element(By.XPATH, "//span[text()='Next']/ancestor::button")
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3)
            except:
                pass

        # Enter password
        try:
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"], input[type="password"]'))
            )
            password_field.clear()
            password_field.click()  # Click to focus
            time.sleep(0.5)
            # Type character by character like a human with variable speed
            for char in account_password:
                password_field.send_keys(char)
                time.sleep(uniform(0.05, 0.15))  # Random delay for more human-like typing
            print("[Cookie Refresh] Entered password")
            time.sleep(2)

            # Click Log in
            login_button = driver.find_element(By.XPATH, "//span[text()='Log in']/ancestor::button")
            driver.execute_script("arguments[0].click();", login_button)
            time.sleep(5)
        except Exception as e:
            if "invalid session id" in str(e).lower():
                print("[Cookie Refresh] Browser window was closed")
                try:
                    driver.quit()
                except:
                    pass
                # Clean up lock file
                try:
                    lock_file.unlink()
                except:
                    pass
                return None
            print(f"[Cookie Refresh] Password entry failed: {e}")

        # Check if login successful
        print("[Cookie Refresh] Checking login status...")
        time.sleep(5)

        # Navigate to home to ensure we get all cookies
        driver.get("https://x.com/home")
        time.sleep(3)

        # Extract cookies
        print("[Cookie Refresh] Extracting cookies...")
        selenium_cookies = driver.get_cookies()
        print(f"[Cookie Refresh] Found {len(selenium_cookies)} total cookies")

        # Convert to twikit format
        cookie_dict = {}
        for cookie in selenium_cookies:
            name = cookie['name']
            if name in REQUIRED_COOKIES:
                cookie_dict[name] = cookie['value']

        driver.quit()

        if 'auth_token' in cookie_dict and 'ct0' in cookie_dict:
            print(f"[Cookie Refresh] [OK] Successfully extracted {len(cookie_dict)} cookies")
            # Clean up lock file on success
            try:
                lock_file.unlink()
            except:
                pass
            return cookie_dict
        else:
            print("[Cookie Refresh] Missing critical cookies")
            # Clean up lock file on failure
            try:
                lock_file.unlink()
            except:
                pass
            return None

    except ImportError:
        print("[Cookie Refresh] ERROR: undetected-chromedriver not installed")
        print("[Cookie Refresh] Install with: C:\\venvs\\pjxvenv\\Scripts\\pip.exe install undetected-chromedriver")
        # Clean up lock file
        try:
            lock_file.unlink()
        except:
            pass
        return None
    except Exception as e:
        print(f"[Cookie Refresh] Error: {e}")
        traceback.print_exc()
        # Clean up lock file
        try:
            lock_file.unlink()
        except:
            pass
        return None


def save_cookies(cookie_dict, cookies_path=None):
    """Save cookies to file"""
    if not cookie_dict:
        return False

    if cookies_path is None:
        cookies_path = COOKIES_PATH

    # Ensure directory exists
    cookies_path.parent.mkdir(parents=True, exist_ok=True)

    # Save cookies
    with open(cookies_path, 'w') as f:
        json.dump(cookie_dict, f, indent=2)

    print(f"[Cookie Refresh] Cookies saved to {cookies_path}")
    return True


def main():
    """Main function for command-line usage"""
    import argparse

    parser = argparse.ArgumentParser(description='Refresh Twitter cookies with Cloudflare bypass')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (not recommended)')
    parser.add_argument('--account', type=int, default=1, help='Account number (1-4)')
    parser.add_argument('--test', action='store_true', help='Test mode - use default account')

    args = parser.parse_args()

    # Load account credentials
    if args.test or args.account == 1:
        # Default account
        account_email = os.getenv('TWITTER_EMAIL', 'kevindzit+crypto1@gmail.com')
        account_password = os.getenv('TWITTER_PASSWORD', 'Gokqh1x!a#d')
        account_username = os.getenv('TWITTER_USERNAME', 'lungjuice001')
    else:
        # Multi-account support
        account_email = os.getenv(f'TWITTER_EMAIL_{args.account}')
        account_password = os.getenv(f'TWITTER_PASSWORD_{args.account}')
        account_username = os.getenv(f'TWITTER_USERNAME_{args.account}')

    print("=" * 60)
    print("Twitter Cookie Refresh")
    print("With Cloudflare and Error Page Handling")
    print("=" * 60)
    print(f"[INFO] Email: {account_email}")
    print(f"[INFO] Username: {account_username}")

    # Backup existing cookies
    if COOKIES_PATH.exists():
        backup_path = COOKIES_PATH.with_suffix('.json.backup')
        try:
            import shutil
            shutil.copy2(COOKIES_PATH, backup_path)
            print(f"[INFO] Backup saved to {backup_path}")
        except:
            pass

    # Refresh cookies
    cookies = refresh_cookies(
        headless=args.headless,
        account_email=account_email,
        account_password=account_password,
        account_username=account_username
    )

    if cookies:
        save_cookies(cookies)
        print("\n[SUCCESS] Cookies refreshed successfully!")
        print("[INFO] Your Twitter scrapers can now use the new cookies")
        return 0
    else:
        print("\n[ERROR] Cookie refresh failed")
        print("[INFO] Check the error messages above")
        return 1


if __name__ == "__main__":
    sys.exit(main())