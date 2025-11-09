#!/usr/bin/env python3
"""
Manual Cookie Refresh Script
Run this when Twitter scrapers are having authentication issues
Supports both single-account and multi-account modes
"""

import sys
import os
from pathlib import Path
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitors.refresh_cookies import refresh_cookies, save_cookies
from dotenv import load_dotenv

def main():
    """Manual cookie refresh with interactive prompts"""
    print("="*60)
    print("Twitter Cookie Refresh Tool")
    print("="*60)

    # Load environment variables
    load_dotenv(override=True)

    # Check for account pool
    try:
        from nice_funcs.twitter_account_pool import account_pool
        has_pool = True
        print("[INFO] Account pool detected")
    except ImportError:
        has_pool = False
        print("[INFO] Single account mode")

    if has_pool:
        print("\nAvailable accounts:")
        print("1. Account 1 (Primary)")
        print("2. Account 2")
        print("3. Account 3")
        print("4. Account 4")
        print("5. All accounts")

        choice = input("\nWhich account to refresh? (1-5): ").strip()

        if choice == '5':
            # Refresh all accounts
            for i in range(1, 5):
                print(f"\n[REFRESHING] Account {i}")
                refresh_account(i)
                if i < 4:
                    print("[WAIT] Waiting 10 seconds before next account...")
                    time.sleep(10)
        elif choice in ['1', '2', '3', '4']:
            refresh_account(int(choice))
        else:
            print("[ERROR] Invalid choice")
            return 1
    else:
        # Single account mode
        refresh_account(1)

    print("\n[SUCCESS] Cookie refresh complete!")
    return 0

def refresh_account(account_num):
    """Refresh cookies for a specific account"""
    # Get credentials
    email = os.getenv(f'TWITTER_ACCOUNT{account_num}_EMAIL')
    password = os.getenv('TWITTER_PASSWORD')
    username = os.getenv(f'TWITTER_ACCOUNT{account_num}_USERNAME')

    if not email or not password:
        print(f"[ERROR] Missing credentials for account {account_num}")
        print(f"[ERROR] Check TWITTER_ACCOUNT{account_num}_EMAIL and TWITTER_PASSWORD in .env")
        return False

    print(f"\n[ACCOUNT {account_num}] Refreshing cookies for: {email}")
    print(f"[ACCOUNT {account_num}] Username for verification: {username}")

    # Determine cookie path
    if account_num == 1:
        cookie_path = Path("cookies/cookies.json")
    else:
        cookie_path = Path(f"cookies/account_{account_num}_cookies.json")

    # Backup existing cookies
    if cookie_path.exists():
        backup_path = cookie_path.parent / f"{cookie_path.stem}.backup.json"
        with open(cookie_path, 'r') as f:
            backup = f.read()
        with open(backup_path, 'w') as f:
            f.write(backup)
        print(f"[BACKUP] Saved to {backup_path}")

    # Refresh cookies with automated login
    print(f"[BROWSER] Launching Chrome...")
    print(f"[BROWSER] If verification appears, username will be entered automatically")
    print(f"[BROWSER] You may need to complete additional steps if prompted")

    cookies = refresh_cookies(
        headless=False,
        account_email=email,
        account_password=password,
        account_username=username
    )

    if cookies:
        # Save cookies to appropriate file
        with open(cookie_path, 'w') as f:
            import json
            json.dump(cookies, f, indent=2)
        print(f"[SUCCESS] Cookies saved to {cookie_path}")

        # If using account pool, update it
        try:
            from nice_funcs.twitter_account_pool import account_pool
            if account_pool:
                success = account_pool.refresh_account(account_num)
                if success:
                    print(f"[SUCCESS] Account pool updated for account {account_num}")
        except:
            pass

        return True
    else:
        print(f"[ERROR] Failed to extract cookies for account {account_num}")
        return False

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Exiting...")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)