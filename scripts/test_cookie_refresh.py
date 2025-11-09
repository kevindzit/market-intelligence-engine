#!/usr/bin/env python3
"""
Test script to diagnose cookie refresh issues
Run this to see exactly what happens during the refresh process
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
import undetected_chromedriver as uc

def test_refresh():
    """Test the cookie refresh process with detailed logging"""
    print("="*60)
    print("Cookie Refresh Diagnostic Test")
    print("="*60)

    # Load environment variables
    load_dotenv(override=True)
    email = os.getenv('TWITTER_ACCOUNT1_EMAIL')
    password = os.getenv('TWITTER_PASSWORD')
    username = os.getenv('TWITTER_ACCOUNT1_USERNAME')

    print(f"\n[CONFIG] Email: {email}")
    print(f"[CONFIG] Username: {username}")
    print(f"[CONFIG] Password: {'*' * len(password) if password else 'NOT SET'}")

    # Launch Chrome
    print("\n[STEP 1] Launching Chrome...")
    options = uc.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1024,768')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    driver = uc.Chrome(options=options, use_subprocess=True)

    try:
        # Navigate to login
        print("[STEP 2] Navigating to Twitter login...")
        driver.get("https://x.com/i/flow/login")
        time.sleep(5)

        # Check what's on the page
        print("\n[STEP 3] Analyzing page content...")

        # Look for common elements
        elements_to_check = [
            ("Username input", 'input[autocomplete="username"]'),
            ("Password input", 'input[name="password"]'),
            ("Next button", '//span[text()="Next"]'),
            ("Log in button", '//span[text()="Log in"]'),
            ("Verification text", '//*[contains(text(), "Enter your phone")]'),
            ("Unusual activity", '//*[contains(text(), "unusual login")]'),
            ("Something went wrong", '//*[contains(text(), "Something went wrong")]'),
        ]

        for name, selector in elements_to_check:
            try:
                if selector.startswith('//'):
                    # XPath
                    elements = driver.find_elements(By.XPATH, selector)
                else:
                    # CSS Selector
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)

                if elements:
                    print(f"  ✓ Found: {name} ({len(elements)} element(s))")
                else:
                    print(f"  ✗ Not found: {name}")
            except Exception as e:
                print(f"  ! Error checking {name}: {e}")

        # Get page title
        print(f"\n[PAGE] Title: {driver.title}")

        # Get any error messages
        error_messages = driver.find_elements(By.CSS_SELECTOR, '[role="alert"]')
        if error_messages:
            print(f"[ALERT] Found {len(error_messages)} alert(s):")
            for msg in error_messages:
                print(f"  - {msg.text[:100]}")

        # Try to proceed with login
        print("\n[STEP 4] Attempting login...")

        # Enter username
        username_input = None
        for selector in ['input[autocomplete="username"]', 'input[name="text"]']:
            try:
                username_input = driver.find_element(By.CSS_SELECTOR, selector)
                break
            except:
                continue

        if username_input:
            print(f"  ✓ Found username input, entering: {email}")
            username_input.clear()
            username_input.send_keys(email)
            time.sleep(2)

            # Click Next
            next_buttons = driver.find_elements(By.XPATH, '//span[text()="Next"]/ancestor::div[@role="button"]')
            if next_buttons:
                print("  ✓ Clicking Next button...")
                next_buttons[0].click()
                time.sleep(5)

                # Check what happens next
                print("\n[STEP 5] Checking next page...")

                # Look for verification challenge
                challenge_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]')
                if challenge_inputs:
                    print("  ! VERIFICATION CHALLENGE DETECTED")
                    print("  ! Page is asking for phone number or username")

                    # Check for specific text
                    page_text = driver.find_element(By.TAG_NAME, 'body').text
                    if "Enter your phone number" in page_text:
                        print("  ! Text found: 'Enter your phone number or username'")
                    if "unusual login activity" in page_text:
                        print("  ! Text found: 'unusual login activity'")

                    if username:
                        print(f"  → Entering username: {username}")
                        challenge_inputs[0].clear()
                        challenge_inputs[0].send_keys(username)
                        time.sleep(2)

                        # Try to click Next again
                        next_buttons2 = driver.find_elements(By.XPATH, '//span[text()="Next"]/ancestor::div[@role="button"]')
                        if next_buttons2:
                            print("  → Clicking Next after username...")
                            next_buttons2[0].click()
                            time.sleep(5)
                    else:
                        print("  ! No username configured for verification")
                        print("  ! Set TWITTER_ACCOUNT1_USERNAME in .env")

                # Check for password field
                password_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[name="password"]')
                if password_inputs:
                    print("  ✓ Password field found")
                    if password:
                        print("  → Entering password...")
                        password_inputs[0].clear()
                        password_inputs[0].send_keys(password)
                        time.sleep(2)

                        # Click Log in
                        login_buttons = driver.find_elements(By.XPATH, '//span[text()="Log in"]/ancestor::div[@role="button"]')
                        if login_buttons:
                            print("  → Clicking Log in...")
                            login_buttons[0].click()
                            time.sleep(8)

        else:
            print("  ✗ Could not find username input field")

        # Final check
        print("\n[STEP 6] Final status check...")
        if driver.current_url == "https://x.com/home":
            print("  ✓ Successfully logged in!")

            # Extract cookies
            cookies = driver.get_cookies()
            print(f"  ✓ Extracted {len(cookies)} cookies")

            # Check for critical cookies
            cookie_dict = {c['name']: c['value'] for c in cookies}
            critical = ['auth_token', 'ct0']
            for c in critical:
                if c in cookie_dict:
                    print(f"  ✓ Critical cookie found: {c}")
                else:
                    print(f"  ✗ Critical cookie missing: {c}")

        else:
            print(f"  ✗ Still on: {driver.current_url}")
            print("  ✗ Login may have failed or additional steps required")

        print("\n[TEST] Keeping browser open for 30 seconds for inspection...")
        print("[TEST] You can interact with the browser if needed")
        time.sleep(30)

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n[CLEANUP] Closing browser...")
        driver.quit()

    print("\n[COMPLETE] Test finished")

if __name__ == "__main__":
    test_refresh()