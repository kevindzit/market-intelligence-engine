"""
Setup Twitter Account Cookies
Extract cookies for a specific Twitter account
Usage: python scripts/setup_account_cookies.py --account 1
"""

import sys
import json
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitors.refresh_cookies import refresh_cookies

def setup_account_cookies(account_num):
    """
    Extract cookies for a specific account number

    Args:
        account_num: Account number (1, 2, 3, 4, etc.)
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()

    print("="*70)
    print(f"Twitter Account Cookie Setup - Account {account_num}")
    print("="*70)

    # Get credentials from .env
    account_email = os.getenv(f'TWITTER_ACCOUNT{account_num}_EMAIL')
    account_username = os.getenv(f'TWITTER_ACCOUNT{account_num}_USERNAME')
    account_password = os.getenv('TWITTER_PASSWORD')

    if not account_email or not account_password or not account_username:
        print(f"\n[ERROR] Missing credentials in .env for Account {account_num}")
        print(f"Please add TWITTER_ACCOUNT{account_num}_EMAIL, TWITTER_ACCOUNT{account_num}_USERNAME, and TWITTER_PASSWORD to .env")
        return False

    print(f"\nAccount Email: {account_email}")
    print(f"Account Username: {account_username}")
    print("Account Password: ******* (from .env)")
    print("\nStarting automated login...")

    # Use automated login
    print(f"\n[Account {account_num}] Starting automated login and cookie extraction...")
    cookies = refresh_cookies(headless=False, account_email=account_email, account_password=account_password, account_username=account_username)

    if not cookies:
        print(f"\n[FAILED] Could not extract cookies for Account {account_num}")
        print("Check if credentials are correct in .env!")
        return False

    # Save to account-specific file in cookies/ folder
    cookies_dir = Path(__file__).parent / "cookies"
    cookies_dir.mkdir(exist_ok=True)  # Create if doesn't exist
    cookies_file = cookies_dir / f"cookies_account{account_num}.json"

    try:
        with open(cookies_file, 'w') as f:
            json.dump(cookies, f, indent=2)

        print(f"\n[SUCCESS] Cookies saved to: {cookies_file.name}")
        print(f"[SUCCESS] Account {account_num} is ready to use!")
        return True

    except Exception as e:
        print(f"\n[FAILED] Could not save cookies: {e}")
        return False

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Extract Twitter cookies for a specific account"
    )
    parser.add_argument(
        '--account',
        type=int,
        required=True,
        help='Account number to set up (1, 2, 3, etc.)'
    )

    args = parser.parse_args()
    success = setup_account_cookies(args.account)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
