"""
Twitter Account Pool Manager
Manages multiple Twitter accounts to bypass rate limits
Auto-rotates between accounts when rate limits are hit

Rate Limits (per account, resets every 15 minutes):
- search_tweet: 50 calls/15min
- get_user_tweets: 50 calls/15min
- get_user_by_screen_name: 95 calls/15min

With 4 accounts = 200 searches/15min instead of 50!
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from twikit import Client

class TwitterAccountPool:
    """
    Manages a pool of Twitter accounts for rate limit avoidance

    Usage:
        pool = TwitterAccountPool()
        client = pool.get_client()  # Returns fresh client
    """

    def __init__(self):
        """Initialize account pool by loading all available account cookies"""
        self.clients = []  # List of (client, account_num, last_used_time)
        self.current_index = 0
        self.rate_limit_window = 15 * 60  # 15 minutes in seconds

        # Load all available account cookie files
        self._load_accounts()

    def _load_accounts(self):
        """Load all cookies_accountN.json files and create clients"""
        project_root = Path(__file__).parent.parent
        cookies_dir = project_root / "cookies"
        account_num = 1
        loaded_count = 0

        # Keep trying to load account files until we don't find one
        while True:
            cookies_file = cookies_dir / f"cookies_account{account_num}.json"

            if not cookies_file.exists():
                # No more account files found
                break

            try:
                # Create client for this account
                client = Client('en-US')
                client.load_cookies(str(cookies_file))

                # Add to pool with initial timestamp (far in past so it's available immediately)
                self.clients.append({
                    'client': client,
                    'account_num': account_num,
                    'last_used': datetime.now() - timedelta(hours=1),  # Available immediately
                    'cookies_file': str(cookies_file)
                })

                loaded_count += 1
                print(f"[Account Pool] [OK] Loaded Account {account_num}")

            except Exception as e:
                print(f"[Account Pool] [FAIL] Failed to load Account {account_num}: {e}")

            account_num += 1

        if loaded_count == 0:
            print("[Account Pool] [WARN] No account cookie files found!")
            print("[Account Pool] [WARN] Run 'python scripts/setup_account_cookies.py' to set up accounts")
            print("[Account Pool] [WARN] Falling back to single-account mode")
        else:
            print(f"[Account Pool] [OK] Loaded {loaded_count} accounts")
            print(f"[Account Pool] [OK] Rate limit capacity: {loaded_count * 50} searches/15min")

    def get_client(self):
        """
        Get a fresh Twitter client from the pool

        Returns the next available client that hasn't been rate limited.
        If all clients are rate limited, waits for the oldest one to refresh.

        Returns:
            Client: TwiKit Client instance ready to use
        """
        if not self.clients:
            # No accounts in pool - fall back to single account mode
            print("[Account Pool] [WARN] No accounts available, using fallback mode")
            return None

        # If only one account, return it
        if len(self.clients) == 1:
            return self.clients[0]['client']

        # Find the next available (non-rate-limited) account
        now = datetime.now()

        # Try to find an account that's past the rate limit window
        for i in range(len(self.clients)):
            # Round-robin through accounts
            index = (self.current_index + i) % len(self.clients)
            account = self.clients[index]

            time_since_use = (now - account['last_used']).total_seconds()

            if time_since_use >= self.rate_limit_window:
                # This account is fresh - use it
                account['last_used'] = now
                self.current_index = (index + 1) % len(self.clients)

                print(f"[Account Pool] Using Account {account['account_num']}")
                return account['client']

        # All accounts recently used - find the oldest one
        oldest_account = min(self.clients, key=lambda x: x['last_used'])
        time_since_use = (now - oldest_account['last_used']).total_seconds()

        if time_since_use < self.rate_limit_window:
            wait_time = self.rate_limit_window - time_since_use
            print(f"[Account Pool] [WAIT] All accounts rate limited. Next refresh in {int(wait_time)}s")
            # Note: We don't actually wait here - the calling code handles rate limit errors

        # Use the oldest account (closest to being refreshed)
        oldest_account['last_used'] = now
        print(f"[Account Pool] Using Account {oldest_account['account_num']} (least recently used)")
        return oldest_account['client']

    def get_account_num(self, client):
        """
        Get the account number for a specific client instance

        Args:
            client: TwiKit Client instance

        Returns:
            int or None: Account number (1, 2, 3, etc.) or None if not found
        """
        for account in self.clients:
            if account['client'] is client:
                return account['account_num']
        return None

    def refresh_account(self, account_num):
        """
        Refresh cookies for a specific account

        Args:
            account_num: Account number to refresh (1, 2, 3, etc.)

        Returns:
            bool: True if refresh succeeded, False otherwise
        """
        import os
        from dotenv import load_dotenv
        from monitors.refresh_cookies import refresh_cookies

        load_dotenv()

        print(f"[Account Pool] 🔄 Refreshing Account {account_num} cookies...")

        # Find the account in our pool
        account = None
        for acc in self.clients:
            if acc['account_num'] == account_num:
                account = acc
                break

        if not account:
            print(f"[Account Pool] [FAIL] Account {account_num} not found in pool")
            return False

        # Get credentials from .env
        account_email = os.getenv(f'TWITTER_ACCOUNT{account_num}_EMAIL')
        account_username = os.getenv(f'TWITTER_ACCOUNT{account_num}_USERNAME')
        account_password = os.getenv('TWITTER_PASSWORD')

        if not account_email or not account_password or not account_username:
            print(f"[Account Pool] [FAIL] Missing credentials in .env for Account {account_num}")
            print(f"[Account Pool] [FAIL] Need TWITTER_ACCOUNT{account_num}_EMAIL, TWITTER_ACCOUNT{account_num}_USERNAME, and TWITTER_PASSWORD")
            return False

        # Extract fresh cookies with automated login
        cookies = refresh_cookies(headless=False, account_email=account_email, account_password=account_password, account_username=account_username)

        if not cookies:
            print(f"[Account Pool] [FAIL] Failed to extract cookies for Account {account_num}")
            return False

        # Save to account-specific file
        try:
            with open(account['cookies_file'], 'w') as f:
                json.dump(cookies, f, indent=2)

            # Create new client with fresh cookies
            new_client = Client('en-US')
            new_client.load_cookies(account['cookies_file'])

            # Update pool with new client
            account['client'] = new_client
            account['last_used'] = datetime.now() - timedelta(hours=1)  # Make it available

            print(f"[Account Pool] [OK] Account {account_num} refreshed successfully!")
            return True

        except Exception as e:
            print(f"[Account Pool] [FAIL] Error refreshing Account {account_num}: {e}")
            return False

    def get_status(self):
        """Get status of all accounts in the pool"""
        if not self.clients:
            return "No accounts in pool"

        now = datetime.now()
        status_lines = [f"Account Pool Status ({len(self.clients)} accounts):"]

        for account in self.clients:
            time_since_use = (now - account['last_used']).total_seconds()
            minutes = int(time_since_use / 60)

            if time_since_use >= self.rate_limit_window:
                status = "[OK] Available"
            else:
                wait_time = int((self.rate_limit_window - time_since_use) / 60)
                status = f"[WAIT] {wait_time}m"

            status_lines.append(f"  Account {account['account_num']}: {status} (last used {minutes}m ago)")

        return "\n".join(status_lines)


# Global singleton instance
_pool_instance = None

def get_account_pool():
    """
    Get or create the global account pool instance

    Returns:
        TwitterAccountPool: The global pool instance
    """
    global _pool_instance

    if _pool_instance is None:
        _pool_instance = TwitterAccountPool()

    return _pool_instance


# Convenience alias
account_pool = get_account_pool()
