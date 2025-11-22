"""
Setup Twitter Account Cookies

Refresh one or more Twitter accounts by extracting cookies with the shared
`monitors.refresh_cookies` helper.

Examples:
  python scripts/setup_account_cookies.py --account 1
  python scripts/setup_account_cookies.py --accounts 2 3
  python scripts/setup_account_cookies.py --all
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from monitors.refresh_cookies import refresh_cookies

COOKIES_DIR = PROJECT_ROOT / "cookies"
MAX_ACCOUNTS = 10


def backup_file(path: Path) -> None:
    """Create a small backup copy if the cookie file already exists."""
    if not path.exists():
        return

    backup_path = path.parent / f"{path.stem}.backup{path.suffix}"
    backup_path.write_text(path.read_text())
    print(f"[BACKUP] {path.name} → {backup_path.name}")


def detect_configured_accounts() -> List[int]:
    """Return account numbers that have credentials in the .env file."""
    accounts: List[int] = []
    for idx in range(1, MAX_ACCOUNTS + 1):
        email = os.getenv(f"TWITTER_ACCOUNT{idx}_EMAIL")
        username = os.getenv(f"TWITTER_ACCOUNT{idx}_USERNAME")
        if email and username:
            accounts.append(idx)
    return accounts


def refresh_account(account_num: int, *, headless: bool = False) -> bool:
    """Refresh cookies for a single account."""
    email = os.getenv(f"TWITTER_ACCOUNT{account_num}_EMAIL")
    username = os.getenv(f"TWITTER_ACCOUNT{account_num}_USERNAME")
    password = os.getenv("TWITTER_PASSWORD")

    if not email or not username or not password:
        print(f"[ERROR] Missing credentials for Account {account_num}")
        print(
            f"        Need TWITTER_ACCOUNT{account_num}_EMAIL, "
            f"TWITTER_ACCOUNT{account_num}_USERNAME, and TWITTER_PASSWORD"
        )
        return False

    print("=" * 70)
    print(f"Account {account_num}: {email}")
    print(f"Username: {username}")
    print(f"Headless mode: {'ON' if headless else 'OFF'}")
    print("=" * 70)

    cookie_targets = [COOKIES_DIR / f"cookies_account{account_num}.json"]

    # Account 1 also feeds the single-account fallback file.
    if account_num == 1:
        cookie_targets.append(COOKIES_DIR / "cookies.json")

    for target in cookie_targets:
        backup_file(target)

    cookies = refresh_cookies(
        headless=headless,
        account_email=email,
        account_password=password,
        account_username=username,
    )

    if not cookies:
        print(f"[FAILED] Could not extract cookies for Account {account_num}")
        return False

    for target in cookie_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        print(f"[OK] Cookies saved to {target.relative_to(PROJECT_ROOT)}")

    print(f"[SUCCESS] Account {account_num} ready to use\n")
    return True


def determine_accounts(args: argparse.Namespace) -> List[int]:
    """Resolve which account numbers should be refreshed based on CLI input."""
    if args.all:
        configured = detect_configured_accounts()
        if not configured:
            print("[ERROR] No accounts with credentials found in .env")
        return configured

    if args.accounts:
        return sorted(set(args.accounts))

    if args.account:
        return [args.account]

    return [1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract fresh cookies for one or more Twitter accounts"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--account",
        type=int,
        help="Refresh a single account (default: 1 if no flags provided)",
    )
    group.add_argument(
        "--accounts",
        type=int,
        nargs="+",
        metavar="N",
        help="Refresh a specific list of account numbers",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Refresh every account with credentials in the .env",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode instead of showing the window",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    load_dotenv(override=True)
    COOKIES_DIR.mkdir(exist_ok=True)

    args = parse_args()
    account_numbers = determine_accounts(args)

    if not account_numbers:
        return 1

    print(f"Refreshing accounts: {', '.join(str(n) for n in account_numbers)}\n")
    success = True
    for account_num in account_numbers:
        if not refresh_account(account_num, headless=args.headless):
            success = False

    if success:
        print("All requested accounts refreshed successfully.")
        return 0

    print("Some accounts failed to refresh. See logs above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
