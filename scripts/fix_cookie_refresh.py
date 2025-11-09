#!/usr/bin/env python3
"""
Enhanced cookie refresh that specifically handles the username verification page
Run this when you get stuck on the verification screen
"""

import sys
import os
from pathlib import Path
import time
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc

def handle_verification_page(driver, username):
    """
    Specifically handle the "Enter your phone number or username" page
    """
    print("\n[VERIFICATION] Handling verification challenge...")

    # Try multiple ways to find the input field
    input_selectors = [
        # The main input field visible in your screenshot
        (By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]'),
        (By.CSS_SELECTOR, 'input[name="text"]'),
        (By.CSS_SELECTOR, 'input[type="text"]'),
        (By.XPATH, '//input[@autocapitalize="none"]'),
        (By.XPATH, '//input[@dir="ltr"]'),
        # Try by placeholder text
        (By.XPATH, '//input[contains(@placeholder, "Phone")]'),
        (By.XPATH, '//input[contains(@placeholder, "username")]'),
    ]

    input_field = None
    for selector_type, selector in input_selectors:
        try:
            elements = driver.find_elements(selector_type, selector)
            if elements:
                # Find the visible one
                for elem in elements:
                    if elem.is_displayed() and elem.is_enabled():
                        input_field = elem
                        print(f"  ✓ Found input field using: {selector}")
                        break
                if input_field:
                    break
        except Exception as e:
            continue

    if not input_field:
        # Last resort: find all inputs and use the first visible one
        all_inputs = driver.find_elements(By.TAG_NAME, 'input')
        for inp in all_inputs:
            if inp.is_displayed() and inp.is_enabled():
                input_field = inp
                print("  ✓ Found input field using generic search")
                break

    if input_field:
        try:
            # Clear and type the username
            print(f"  → Clearing input field...")
            input_field.clear()
            time.sleep(1)

            print(f"  → Typing username: {username}")
            # Type slowly to mimic human behavior
            for char in username:
                input_field.send_keys(char)
                time.sleep(0.1)

            time.sleep(2)
            print("  ✓ Username entered")

            # Find and click the Next button
            next_button = None
            button_selectors = [
                (By.XPATH, '//div[@role="button"][.//span[text()="Next"]]'),
                (By.XPATH, '//button[.//span[text()="Next"]]'),
                (By.CSS_SELECTOR, '[role="button"]'),
                (By.XPATH, '//div[@data-testid="ocfEnterTextNextButton"]'),
            ]

            for selector_type, selector in button_selectors:
                try:
                    buttons = driver.find_elements(selector_type, selector)
                    for btn in buttons:
                        if btn.is_displayed() and btn.is_enabled():
                            # Check if it contains "Next" text
                            if "next" in btn.text.lower() or btn.get_attribute('data-testid') == 'ocfEnterTextNextButton':
                                next_button = btn
                                print(f"  ✓ Found Next button")
                                break
                    if next_button:
                        break
                except:
                    continue

            if next_button:
                print("  → Clicking Next button...")
                next_button.click()
                print("  ✓ Next button clicked")
                time.sleep(5)
                return True
            else:
                # Try pressing Enter instead
                print("  → Next button not found, pressing Enter...")
                input_field.send_keys(Keys.RETURN)
                time.sleep(5)
                return True

        except Exception as e:
            print(f"  ✗ Error entering username: {e}")
            return False
    else:
        print("  ✗ Could not find input field")
        return False

def automated_login():
    """
    Perform automated login with better verification handling
    """
    print("="*60)
    print("Enhanced Twitter Cookie Refresh")
    print("="*60)

    # Load credentials
    load_dotenv(override=True)
    email = os.getenv('TWITTER_ACCOUNT1_EMAIL')
    password = os.getenv('TWITTER_PASSWORD')
    username = os.getenv('TWITTER_ACCOUNT1_USERNAME')

    if not all([email, password, username]):
        print("[ERROR] Missing credentials in .env file")
        return None

    print(f"\n[CONFIG] Email: {email}")
    print(f"[CONFIG] Username: {username}")

    # Launch Chrome
    print("\n[BROWSER] Launching Chrome...")
    options = uc.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1280,800')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    driver = uc.Chrome(options=options, use_subprocess=True)

    try:
        # Navigate to login
        print("[LOGIN] Navigating to Twitter login...")
        driver.get("https://x.com/i/flow/login")
        time.sleep(5)

        # Enter email
        print("[LOGIN] Looking for email input...")
        email_input = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"]'))
        )
        print("[LOGIN] Entering email...")
        email_input.clear()
        email_input.send_keys(email)
        time.sleep(2)

        # Click Next
        print("[LOGIN] Clicking Next...")
        next_buttons = driver.find_elements(By.XPATH, '//div[@role="button"][.//span[text()="Next"]]')
        if next_buttons:
            next_buttons[0].click()
        else:
            # Fallback: press Enter
            email_input.send_keys(Keys.RETURN)

        time.sleep(5)

        # Check for verification challenge
        print("\n[CHECK] Checking page state...")

        # Look for the verification text
        verification_texts = [
            "Enter your phone number or username",
            "There was unusual login activity",
            "Help us keep your account safe",
            "Verify it's you"
        ]

        on_verification_page = False
        for text in verification_texts:
            if text.lower() in driver.page_source.lower():
                print(f"[VERIFICATION] Detected: '{text}'")
                on_verification_page = True
                break

        # Also check for the specific input field
        if not on_verification_page:
            verification_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]')
            if verification_inputs:
                print("[VERIFICATION] Detected verification input field")
                on_verification_page = True

        if on_verification_page:
            success = handle_verification_page(driver, username)
            if not success:
                print("\n[MANUAL] Please complete verification manually")
                print("[MANUAL] You have 30 seconds...")
                time.sleep(30)

        # Now look for password field
        print("\n[LOGIN] Looking for password field...")
        password_input = None

        # Wait for password field to appear
        for _ in range(10):
            password_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[name="password"]')
            if password_inputs:
                password_input = password_inputs[0]
                break
            time.sleep(1)

        if password_input:
            print("[LOGIN] Entering password...")
            password_input.clear()
            password_input.send_keys(password)
            time.sleep(2)

            # Click Log in
            print("[LOGIN] Clicking Log in...")
            login_buttons = driver.find_elements(By.XPATH, '//div[@role="button"][.//span[text()="Log in"]]')
            if login_buttons:
                login_buttons[0].click()
            else:
                password_input.send_keys(Keys.RETURN)

            print("[LOGIN] Waiting for login to complete...")
            time.sleep(10)
        else:
            print("[ERROR] Could not find password field")
            print("[MANUAL] Please complete login manually")
            time.sleep(30)

        # Check if logged in
        if "home" in driver.current_url.lower():
            print("\n[SUCCESS] Logged in successfully!")

            # Extract cookies
            cookies = driver.get_cookies()
            cookie_dict = {}

            required_cookies = ['auth_token', 'ct0', 'guest_id', 'kdt', 'twid']
            for cookie in cookies:
                if cookie['name'] in required_cookies:
                    cookie_dict[cookie['name']] = cookie['value']

            if 'auth_token' in cookie_dict and 'ct0' in cookie_dict:
                print(f"[SUCCESS] Extracted {len(cookie_dict)} cookies")

                # Save cookies
                cookie_path = Path("cookies/cookies.json")
                with open(cookie_path, 'w') as f:
                    json.dump(cookie_dict, f, indent=2)
                print(f"[SUCCESS] Cookies saved to {cookie_path}")

                return cookie_dict
            else:
                print("[ERROR] Missing critical cookies")
                return None
        else:
            print(f"[ERROR] Login failed - still on: {driver.current_url}")
            print("[MANUAL] Please complete login manually (30 seconds)")
            time.sleep(30)

            # Try to extract cookies anyway
            cookies = driver.get_cookies()
            if cookies:
                cookie_dict = {c['name']: c['value'] for c in cookies}
                if 'auth_token' in cookie_dict:
                    print("[SUCCESS] Got cookies after manual login")
                    cookie_path = Path("cookies/cookies.json")
                    with open(cookie_path, 'w') as f:
                        json.dump(cookie_dict, f, indent=2)
                    return cookie_dict

            return None

    except Exception as e:
        print(f"\n[ERROR] Login failed: {e}")
        import traceback
        traceback.print_exc()
        print("\n[MANUAL] Please complete login manually (30 seconds)")
        time.sleep(30)
        return None

    finally:
        print("\n[CLEANUP] Closing browser...")
        driver.quit()

if __name__ == "__main__":
    cookies = automated_login()
    if cookies:
        print("\n✅ Cookie refresh successful!")
        sys.exit(0)
    else:
        print("\n❌ Cookie refresh failed")
        sys.exit(1)