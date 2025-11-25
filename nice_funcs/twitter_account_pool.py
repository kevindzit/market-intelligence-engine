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
import time
import sys
import re
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
        self.clients = []  # List of metadata per account
        self.current_index = 0
        self.rate_limit_window = 15 * 60  # 15 minutes in seconds

        # Load all available account cookie files
        self._load_accounts()

    def _acquire_refresh_lock(self, cookies_file, timeout=120):
        """
        Acquire a lock for refreshing cookies (prevents multiple processes from refreshing simultaneously)

        Args:
            cookies_file: Path to the cookies file being refreshed
            timeout: Max seconds to wait for lock (default: 120)

        Returns:
            tuple: (acquired: bool, should_refresh: bool)
                - acquired=True: We got the lock, should refresh
                - acquired=False, should_refresh=False: Another process is refreshing, wait for them
        """
        lock_file = Path(str(cookies_file) + ".lock")
        start_time = time.time()

        # Try to acquire lock
        while True:
            if not lock_file.exists():
                # No lock exists - try to create it
                try:
                    # Create lock file with our PID
                    lock_file.write_text(f"{os.getpid()}\n{datetime.now().isoformat()}")
                    # Small delay to ensure file is written
                    time.sleep(0.1)

                    # Verify we actually created it (race condition check)
                    if lock_file.exists():
                        content = lock_file.read_text().strip()
                        if content.startswith(str(os.getpid())):
                            # We successfully acquired the lock
                            return (True, True)
                except:
                    # Failed to create lock, another process might have beaten us
                    pass

            # Lock exists - check if it's stale
            try:
                if lock_file.exists():
                    content = lock_file.read_text().strip()
                    lines = content.split('\n')
                    if len(lines) >= 2:
                        lock_time = datetime.fromisoformat(lines[1])
                        age = (datetime.now() - lock_time).total_seconds()

                        # If lock is older than 120 seconds, it's stale (Chrome might have crashed)
                        if age > 120:
                            print(f"[Cookie Lock] Stale lock detected (age: {age:.0f}s), removing...")
                            lock_file.unlink()
                            continue
            except:
                # Couldn't read lock file, it might be being written
                pass

            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout:
                print(f"[Cookie Lock] Timeout after {timeout}s waiting for refresh lock")
                return (False, False)

            # Wait and retry
            print(f"[Cookie Lock] Another process is refreshing cookies, waiting... ({elapsed:.0f}s/{timeout}s)")
            time.sleep(5)

    def _release_refresh_lock(self, cookies_file):
        """
        Release the refresh lock

        Args:
            cookies_file: Path to the cookies file
        """
        lock_file = Path(str(cookies_file) + ".lock")
        try:
            if lock_file.exists():
                lock_file.unlink()
        except Exception as e:
            print(f"[Cookie Lock] Warning: Could not remove lock file: {e}")

    def _load_accounts(self):
        """Load all cookies_accountN.json files (and main cookies.json) and create clients."""
        project_root = Path(__file__).parent.parent
        cookies_dir = project_root / "cookies"
        loaded_count = 0

        cookies_files = []

        # Gather all numbered account cookies (handles gaps, e.g., missing account3)
        for path in cookies_dir.glob("cookies_account*.json"):
            if "backup" in path.name.lower():
                continue
            match = re.search(r"account(\d+)", path.stem)
            if not match:
                continue
            cookies_files.append((int(match.group(1)), path, f"Account {match.group(1)}"))

        # Optionally include the main cookies.json as the next account in rotation
        main_cookies = cookies_dir / "cookies.json"
        if main_cookies.exists() and "backup" not in main_cookies.name.lower():
            next_num = (max([num for num, _, _ in cookies_files], default=0) + 1) or 1
            cookies_files.append((next_num, main_cookies, "Main Account"))

        # Sort by account number for deterministic rotation
        cookies_files.sort(key=lambda item: item[0])

        for account_num, cookies_file, label in cookies_files:
            try:
                client = Client('en-US')
                client.load_cookies(str(cookies_file))

                self.clients.append({
                    'client': client,
                    'account_num': account_num,
                    'label': label,
                    'last_used': datetime.now() - timedelta(hours=1),  # Available immediately
                    'cookies_file': str(cookies_file),
                    'rate_limited_until': datetime.now() - timedelta(hours=1)
                })

                loaded_count += 1
                print(f"[Account Pool] [OK] Loaded Account {account_num} ({label})")

            except Exception as e:
                print(f"[Account Pool] [FAIL] Failed to load {label} ({account_num}): {e}")

        if loaded_count == 0:
            print("[Account Pool] [WARN] No account cookie files found!")
            print("[Account Pool] [WARN] Run 'python scripts/setup_account_cookies.py' to set up accounts")
            print("[Account Pool] [WARN] Falling back to single-account mode")
        else:
            print(f"[Account Pool] [OK] Loaded {loaded_count} accounts")
            print(f"[Account Pool] [OK] Rate limit capacity: {loaded_count * 50} searches/15min")

    def _find_account_entry(self, client):
        for account in self.clients:
            if account['client'] is client:
                return account
        return None

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

        now = datetime.now()

        for i in range(len(self.clients)):
            index = (self.current_index + i) % len(self.clients)
            account = self.clients[index]

            if now >= account.get('rate_limited_until', datetime.min):
                account['last_used'] = now
                self.current_index = (index + 1) % len(self.clients)
                print(f"[Account Pool] Using Account {account['account_num']}")
                return account['client']

        # No account is currently ready - pick the one that becomes available soonest
        next_ready = min(
            self.clients,
            key=lambda acc: acc.get('rate_limited_until', datetime.min)
        )
        wait_time = max((next_ready['rate_limited_until'] - now).total_seconds(), 0)
        if wait_time > 0:
            print(f"[Account Pool] [WAIT] All accounts cooling down. Next refresh in {int(wait_time)}s")

        self.current_index = (self.clients.index(next_ready) + 1) % len(self.clients)
        next_ready['last_used'] = now
        return next_ready['client']

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

    def refresh_account(self, account_num, max_attempts=10):
        """
        Refresh cookies for a specific account (with locking to prevent race conditions)

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

        cookies_file = account['cookies_file']

        # Try to acquire refresh lock (prevents multiple processes from refreshing simultaneously)
        acquired, should_refresh = self._acquire_refresh_lock(cookies_file, timeout=120)

        try:
            if should_refresh:
                # We got the lock - we need to do the refresh
                print(f"[Account Pool] [LOCK ACQUIRED] This process will refresh Account {account_num}")

                # Get credentials from .env
                account_email = os.getenv(f'TWITTER_ACCOUNT{account_num}_EMAIL')
                account_username = os.getenv(f'TWITTER_ACCOUNT{account_num}_USERNAME')
                account_password = os.getenv('TWITTER_PASSWORD')

                if not account_email or not account_password or not account_username:
                    print(f"[Account Pool] [FAIL] Missing credentials in .env for Account {account_num}")
                    print(f"[Account Pool] [FAIL] Need TWITTER_ACCOUNT{account_num}_EMAIL, TWITTER_ACCOUNT{account_num}_USERNAME, and TWITTER_PASSWORD")
                    return False

                orchestrator_mode = os.getenv('ORCHESTRATOR_RUNNING', 'false').lower() == 'true'

                # When orchestrated, always show the window so the operator can see/assist.
                # Otherwise, try headless first and fall back to interactive near the end.
                def should_use_headless(attempt):
                    if orchestrator_mode:
                        return False
                    # Keep final 2 attempts interactive
                    return attempt <= max_attempts - 2

                cookies = None

                for attempt in range(1, max_attempts + 1):
                    use_headless = should_use_headless(attempt)
                    mode_label = "automated" if use_headless else "interactive"
                    print(f"[Account Pool] Attempt {attempt}/{max_attempts} ({mode_label})")

                    cookies = refresh_cookies(
                        headless=use_headless,
                        account_email=account_email,
                        account_password=account_password,
                        account_username=account_username
                    )

                    if cookies:
                        break

                    wait_seconds = min(5 * attempt, 30)
                    print(f"[Account Pool] Attempt {attempt} failed. Retrying in {wait_seconds}s...")
                    time.sleep(wait_seconds)

                if not cookies:
                    print(f"[Account Pool] [FAIL] Failed to extract cookies for Account {account_num} after {max_attempts} attempts")
                    return False

                # Save to account-specific file
                try:
                    with open(cookies_file, 'w') as f:
                        json.dump(cookies, f, indent=2)

                    print(f"[Account Pool] [OK] Cookies saved for Account {account_num}")

                except Exception as e:
                    print(f"[Account Pool] [FAIL] Error saving cookies for Account {account_num}: {e}")
                    return False

            else:
                # Another process is/was refreshing - just reload the cookies
                print(f"[Account Pool] [WAIT COMPLETE] Another process refreshed Account {account_num}, reloading...")

            # Create new client with fresh cookies (either we just saved them, or another process did)
            try:
                new_client = Client('en-US')
                new_client.load_cookies(cookies_file)

                # Update pool with new client
                account['client'] = new_client
                account['last_used'] = datetime.now() - timedelta(hours=1)  # Make it available

                print(f"[Account Pool] [OK] Account {account_num} client refreshed successfully!")
                return True

            except Exception as e:
                print(f"[Account Pool] [FAIL] Error loading refreshed cookies for Account {account_num}: {e}")
                return False

        finally:
            # Always release the lock if we acquired it
            if acquired:
                self._release_refresh_lock(cookies_file)
                print(f"[Account Pool] [LOCK RELEASED] Account {account_num}")

    def rotate_after_rate_limit(self, current_client):
        """Mark the current account as rate limited and return the next available client."""
        account = self._find_account_entry(current_client)
        now = datetime.now()
        if account:
            cooldown = now + timedelta(seconds=self.rate_limit_window)
            account['rate_limited_until'] = cooldown
            account['last_used'] = now
            print(f"[Account Pool] Account {account['account_num']} hit rate limit. Cooling down for {self.rate_limit_window//60}m")

        new_client = self.get_client()
        return new_client

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
