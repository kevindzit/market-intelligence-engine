#!/usr/bin/env python3
"""
Direct cookie refresh with simplified verification handling
This version uses a more direct approach to handle the verification page
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
import undetected_chromedriver as uc

def main():
    print("="*60)
    print("Direct Twitter Cookie Refresh")
    print("="*60)

    # Load credentials
    load_dotenv(override=True)
    email = os.getenv('TWITTER_ACCOUNT1_EMAIL')
    password = os.getenv('TWITTER_PASSWORD')
    username = os.getenv('TWITTER_ACCOUNT1_USERNAME')

    print(f"\nCredentials loaded:")
    print(f"  Email: {email}")
    print(f"  Username: {username}")
    print(f"  Password: {'*' * len(password) if password else 'NOT SET'}")

    # Launch Chrome
    print("\nLaunching Chrome...")
    options = uc.ChromeOptions()
    options.add_argument('--window-size=1280,800')

    driver = uc.Chrome(options=options)

    try:
        # Go to login page
        print("Navigating to Twitter login...")
        driver.get("https://x.com/i/flow/login")
        time.sleep(5)

        # STEP 1: Enter email
        print("\n[STEP 1] Entering email...")
        email_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[autocomplete="username"]')
        if email_inputs:
            email_inputs[0].send_keys(email)
            print("  ✓ Email entered")
            time.sleep(2)

            # Press Enter or click Next
            email_inputs[0].send_keys(Keys.RETURN)
            print("  ✓ Proceeding to next step")
            time.sleep(5)
        else:
            print("  ✗ Could not find email input")
            return

        # STEP 2: Check if verification page appears
        print("\n[STEP 2] Checking for verification challenge...")

        # Wait and check what's on the page
        page_text = driver.find_element(By.TAG_NAME, 'body').text.lower()

        if "enter your phone number or username" in page_text or "unusual login" in page_text:
            print("  ✓ VERIFICATION CHALLENGE DETECTED")
            print(f"  → Will enter username: {username}")

            # Find ANY visible input field
            time.sleep(2)
            all_inputs = driver.find_elements(By.TAG_NAME, 'input')

            input_found = False
            for inp in all_inputs:
                try:
                    if inp.is_displayed() and inp.is_enabled():
                        print(f"  → Found input field (type: {inp.get_attribute('type')})")

                        # Click to focus
                        inp.click()
                        time.sleep(1)

                        # Clear and type username
                        inp.clear()
                        inp.send_keys(username)
                        print(f"  ✓ Username '{username}' entered")
                        time.sleep(2)

                        # Press Enter to proceed
                        inp.send_keys(Keys.RETURN)
                        print("  ✓ Submitted verification")
                        input_found = True
                        break
                except Exception as e:
                    print(f"  ! Error with input: {e}")
                    continue

            if not input_found:
                print("  ✗ Could not interact with verification input")
                print("\n⚠️  MANUAL INTERVENTION REQUIRED")
                print(f"Please enter username manually: {username}")
                print("You have 30 seconds...")
                time.sleep(30)

            time.sleep(5)
        else:
            print("  → No verification challenge detected")

        # STEP 3: Enter password
        print("\n[STEP 3] Entering password...")

        # Wait for password field
        password_entered = False
        for attempt in range(10):
            password_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[name="password"]')
            if password_inputs:
                password_inputs[0].send_keys(password)
                print("  ✓ Password entered")
                time.sleep(2)

                # Press Enter to login
                password_inputs[0].send_keys(Keys.RETURN)
                print("  ✓ Login submitted")
                password_entered = True
                break
            else:
                print(f"  ... Waiting for password field (attempt {attempt+1}/10)")
                time.sleep(2)

        if not password_entered:
            print("  ✗ Could not find password field")
            print("\n⚠️  MANUAL INTERVENTION REQUIRED")
            print("Please complete login manually")
            print("You have 30 seconds...")
            time.sleep(30)

        # STEP 4: Wait for login to complete
        print("\n[STEP 4] Waiting for login to complete...")
        time.sleep(10)

        # STEP 5: Extract cookies
        print("\n[STEP 5] Extracting cookies...")

        if "home" in driver.current_url.lower():
            print("  ✓ Successfully logged in!")
        else:
            print(f"  ! Current URL: {driver.current_url}")
            print("  ! May need manual completion")
            time.sleep(10)

        cookies = driver.get_cookies()
        cookie_dict = {}

        for cookie in cookies:
            cookie_dict[cookie['name']] = cookie['value']

        # Check for critical cookies
        critical = ['auth_token', 'ct0']
        has_all = True

        for c in critical:
            if c in cookie_dict:
                print(f"  ✓ Found: {c}")
            else:
                print(f"  ✗ Missing: {c}")
                has_all = False

        if has_all:
            # Save cookies
            cookie_path = Path("cookies/cookies.json")
            cookie_path.parent.mkdir(exist_ok=True)

            with open(cookie_path, 'w') as f:
                json.dump(cookie_dict, f, indent=2)

            print(f"\n✅ SUCCESS! Cookies saved to {cookie_path}")
            print(f"   Total cookies: {len(cookie_dict)}")
            return 0
        else:
            print("\n❌ FAILED: Missing critical cookies")
            print("   Try running the script again or complete login manually")
            return 1

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        print("\nPress Enter to close browser...")
        input()
        driver.quit()

if __name__ == "__main__":
    sys.exit(main())