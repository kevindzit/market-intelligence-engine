"""
Twitter Cookie Refresh using nodriver
Uses nodriver (successor to undetected-chromedriver) for better Cloudflare bypass
Features: cf_verify() for Cloudflare, device fingerprint rotation, async-native
"""

import json
import time
import sys
import os
import asyncio
from pathlib import Path
from random import uniform, choice
import traceback

# Device profiles for fingerprint rotation - helps avoid detection
DEVICE_PROFILES = [
    {'width': 1920, 'height': 1080, 'name': 'Desktop 1080p'},
    {'width': 1366, 'height': 768, 'name': 'Laptop'},
    {'width': 1440, 'height': 900, 'name': 'MacBook'},
    {'width': 1536, 'height': 864, 'name': 'Desktop Scaled'},
    {'width': 1280, 'height': 800, 'name': 'Small Desktop'},
]

# Required cookies for twikit
REQUIRED_COOKIES = [
    'auth_token', 'ct0', 'guest_id', 'guest_id_ads', 'guest_id_marketing',
    'kdt', 'lang', 'personalization_id', 'twid', 'g_state', '__cuid', '__cf_bm'
]

COOKIES_PATH = Path(__file__).parent.parent / "cookies" / "cookies.json"


async def _refresh_cookies_async(headless=False, account_email=None, account_password=None, account_username=None):
    """
    Async cookie refresh using nodriver with Cloudflare bypass
    """
    import nodriver as uc

    if not account_email or not account_password:
        print("[Cookie Refresh] ERROR: Email and password required")
        return None

    # Pick random device profile for fingerprint variation
    device = choice(DEVICE_PROFILES)
    print(f"[Cookie Refresh] Device: {device['name']} ({device['width']}x{device['height']})")
    print(f"[Cookie Refresh] Account: {account_email}")

    browser = None
    try:
        # Start browser with device-specific settings
        browser = await uc.start(
            headless=headless,
            browser_args=[
                f'--window-size={device["width"]},{device["height"]}',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )

        print("[Cookie Refresh] Navigating to Twitter login...")
        page = await browser.get("https://x.com/i/flow/login")
        await asyncio.sleep(3)

        # Check for and handle Cloudflare challenge
        for cf_attempt in range(3):
            page_text = await page.get_content()
            page_lower = page_text.lower() if page_text else ""

            if "verify you are human" in page_lower or "cloudflare" in page_lower or "just a moment" in page_lower:
                print(f"[Cookie Refresh] Cloudflare detected - attempting cf_verify ({cf_attempt + 1}/3)")
                try:
                    await page.cf_verify()
                    print("[Cookie Refresh] cf_verify completed")
                    await asyncio.sleep(3)
                except Exception as cf_err:
                    print(f"[Cookie Refresh] cf_verify failed: {cf_err}")
                    await asyncio.sleep(5)
            else:
                break

        # Handle "Something went wrong" retry pages
        for retry in range(5):
            await asyncio.sleep(2)
            page_text = await page.get_content()
            page_lower = page_text.lower() if page_text else ""

            if "something went wrong" in page_lower and "try reloading" in page_lower:
                print(f"[Cookie Refresh] Error page - looking for retry ({retry + 1}/5)")
                try:
                    retry_btn = await page.find("Retry", timeout=5)
                    if retry_btn:
                        await retry_btn.click()
                        await asyncio.sleep(3)
                except:
                    try:
                        retry_btn = await page.find("Try again", timeout=3)
                        if retry_btn:
                            await retry_btn.click()
                            await asyncio.sleep(3)
                    except:
                        await asyncio.sleep(3)
            else:
                break

        # Check for Cloudflare again after retries
        page_text = await page.get_content()
        page_lower = page_text.lower() if page_text else ""
        if "verify you are human" in page_lower or "cloudflare" in page_lower:
            print("[Cookie Refresh] Cloudflare still present - trying cf_verify again")
            try:
                await page.cf_verify()
                await asyncio.sleep(3)
            except:
                pass

        # Enter email/username
        print("[Cookie Refresh] Entering credentials...")
        try:
            username_field = await page.find('input[autocomplete="username"]', timeout=15)
            if not username_field:
                username_field = await page.find('input[name="text"]', timeout=5)

            if username_field:
                await username_field.click()
                await asyncio.sleep(0.5)
                # Type character by character with human-like delays
                for char in account_email:
                    await username_field.send_keys(char)
                    await asyncio.sleep(uniform(0.05, 0.12))
                print("[Cookie Refresh] Entered email")
                await asyncio.sleep(1.5)

                # Click Next
                next_btn = await page.find("Next", timeout=5)
                if next_btn:
                    await next_btn.click()
                    await asyncio.sleep(3)
        except Exception as e:
            print(f"[Cookie Refresh] Email entry error: {e}")

        # Check for rate limit error
        page_text = await page.get_content()
        page_lower = page_text.lower() if page_text else ""
        if "could not log you in now" in page_lower or "please try again later" in page_lower:
            print("[Cookie Refresh] Twitter rate limit - wait 30-60 min or try different IP")
            await browser.stop()
            return None

        # Handle username verification challenge
        if account_username:
            try:
                verify_field = await page.find('input[data-testid="ocfEnterTextTextInput"]', timeout=5)
                if verify_field:
                    await verify_field.click()
                    await asyncio.sleep(0.5)
                    for char in account_username:
                        await verify_field.send_keys(char)
                        await asyncio.sleep(uniform(0.05, 0.12))
                    print("[Cookie Refresh] Entered username verification")
                    await asyncio.sleep(1)
                    next_btn = await page.find("Next", timeout=5)
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(3)
            except:
                pass

        # Enter password
        try:
            password_field = await page.find('input[name="password"]', timeout=10)
            if not password_field:
                password_field = await page.find('input[type="password"]', timeout=5)

            if password_field:
                await password_field.click()
                await asyncio.sleep(0.5)
                for char in account_password:
                    await password_field.send_keys(char)
                    await asyncio.sleep(uniform(0.05, 0.12))
                print("[Cookie Refresh] Entered password")
                await asyncio.sleep(1.5)

                # Click Log in
                login_btn = await page.find("Log in", timeout=5)
                if login_btn:
                    await login_btn.click()
                    await asyncio.sleep(5)
        except Exception as e:
            print(f"[Cookie Refresh] Password entry error: {e}")

        # Navigate to home to ensure all cookies are set
        print("[Cookie Refresh] Navigating to home...")
        await page.get("https://x.com/home")
        await asyncio.sleep(3)

        # Extract cookies
        print("[Cookie Refresh] Extracting cookies...")
        all_cookies = await browser.cookies.get_all()

        cookie_dict = {}
        for cookie in all_cookies:
            name = cookie.name if hasattr(cookie, 'name') else cookie.get('name', '')
            value = cookie.value if hasattr(cookie, 'value') else cookie.get('value', '')
            if name in REQUIRED_COOKIES:
                cookie_dict[name] = value

        await browser.stop()

        if 'auth_token' in cookie_dict and 'ct0' in cookie_dict:
            print(f"[Cookie Refresh] SUCCESS - extracted {len(cookie_dict)} cookies")
            return cookie_dict
        else:
            print("[Cookie Refresh] FAILED - missing critical cookies (auth_token or ct0)")
            print(f"[Cookie Refresh] Got: {list(cookie_dict.keys())}")
            return None

    except Exception as e:
        print(f"[Cookie Refresh] Error: {e}")
        traceback.print_exc()
        if browser:
            try:
                await browser.stop()
            except:
                pass
        return None


def refresh_cookies(headless=False, account_email=None, account_password=None, account_username=None):
    """
    Sync wrapper for cookie refresh - maintains compatibility with existing code
    """
    # Check for lock file
    lock_file = Path(__file__).parent / ".refresh_cookies.lock"
    if lock_file.exists():
        try:
            lock_age = time.time() - lock_file.stat().st_mtime
            if lock_age < 300:
                print("[Cookie Refresh] Another instance running - skipping")
                return None
            else:
                lock_file.unlink()
        except:
            pass

    try:
        lock_file.touch()
    except:
        pass

    try:
        # Try to get existing event loop or create new one
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    _refresh_cookies_async(headless, account_email, account_password, account_username)
                ).result()
        except RuntimeError:
            # No event loop - create new one
            result = asyncio.run(
                _refresh_cookies_async(headless, account_email, account_password, account_username)
            )
    finally:
        try:
            lock_file.unlink()
        except:
            pass

    return result


def save_cookies(cookie_dict, cookies_path=None):
    """Save cookies to file"""
    if not cookie_dict:
        return False

    if cookies_path is None:
        cookies_path = COOKIES_PATH

    cookies_path.parent.mkdir(parents=True, exist_ok=True)

    with open(cookies_path, 'w') as f:
        json.dump(cookie_dict, f, indent=2)

    print(f"[Cookie Refresh] Cookies saved to {cookies_path}")
    return True


def main():
    """Command-line usage"""
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description='Refresh Twitter cookies with nodriver')
    parser.add_argument('--headless', action='store_true', help='Run headless (less reliable)')
    parser.add_argument('--account', type=int, default=1, help='Account number (1-4)')
    args = parser.parse_args()

    account_num = args.account
    email = os.getenv(f'TWITTER_ACCOUNT{account_num}_EMAIL')
    username = os.getenv(f'TWITTER_ACCOUNT{account_num}_USERNAME')
    password = os.getenv('TWITTER_PASSWORD')

    if not email or not password:
        print(f"ERROR: Set TWITTER_ACCOUNT{account_num}_EMAIL and TWITTER_PASSWORD in .env")
        sys.exit(1)

    print("=" * 60)
    print("Twitter Cookie Refresh (nodriver)")
    print("=" * 60)

    cookies = refresh_cookies(
        headless=args.headless,
        account_email=email,
        account_password=password,
        account_username=username
    )

    if cookies:
        cookies_path = Path(__file__).parent.parent / "cookies" / f"cookies_account{account_num}.json"
        save_cookies(cookies, cookies_path)
        print("\n[SUCCESS] Cookies refreshed!")
    else:
        print("\n[FAILED] Check errors above")
        sys.exit(1)


if __name__ == "__main__":
    main()
