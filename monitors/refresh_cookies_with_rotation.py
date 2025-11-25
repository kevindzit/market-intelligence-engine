"""
Enhanced Twitter Cookie Refresh with Automatic IP Rotation
Detects IP blocks and automatically rotates to a new IP before retrying
"""

import json
import sys
import os
import time
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from monitors.refresh_cookies import refresh_cookies, save_cookies, COOKIES_PATH

# Optional IP rotation backend (folder may be absent)
try:
    from IP_bypass.rotation_manager import RotationManager, RotationError
    ROTATION_AVAILABLE = True
except ImportError:
    RotationManager = None  # type: ignore

    class RotationError(Exception):
        """Fallback error when rotation backend is unavailable."""

    ROTATION_AVAILABLE = False

class IPRotatingCookieRefresher:
    """Cookie refresher with automatic IP rotation on rate limits"""

    def __init__(self, backend: str = "tor", max_ip_attempts: int = 5):
        """
        Initialize the IP-rotating cookie refresher

        Args:
            backend: IP rotation backend (tor, adb, or proton)
            max_ip_attempts: Maximum number of IP rotations to try
        """
        self.backend = backend
        self.max_ip_attempts = max_ip_attempts
        self.rotation_manager = None
        self.current_ip = None

    def _init_rotation_manager(self) -> bool:
        """Initialize rotation manager if not already done"""
        if self.rotation_manager is not None:
            return True

        if not ROTATION_AVAILABLE:
            print("[IP-REFRESH] Rotation backend not available (IP_bypass missing)")
            return False

        try:
            print(f"[IP-REFRESH] Initializing {self.backend} backend...")
            self.rotation_manager = RotationManager(backend=self.backend)

            # Get current IP
            try:
                ip_info = self.rotation_manager.current_ip()
                self.current_ip = ip_info.get('ip', 'unknown')
                print(f"[IP-REFRESH] Current IP: {self.current_ip}")
            except Exception as e:
                print(f"[IP-REFRESH] Could not get current IP: {e}")
                self.current_ip = 'unknown'

            return True

        except RotationError as e:
            if "tor not found" in str(e).lower():
                print("[IP-REFRESH] Tor not installed. Run: sudo apt install tor")
                print("[IP-REFRESH] Then start it: sudo service tor start")
            elif "tor is not running" in str(e).lower():
                print("[IP-REFRESH] Starting Tor service...")
                try:
                    subprocess.run(["sudo", "service", "tor", "start"], check=False)
                    time.sleep(3)
                    # Try again
                    self.rotation_manager = RotationManager(backend=self.backend)
                    return True
                except Exception:
                    print("[IP-REFRESH] Failed to start Tor service")
            else:
                print(f"[IP-REFRESH] Rotation manager error: {e}")
            return False

        except Exception as e:
            print(f"[IP-REFRESH] Failed to initialize rotation: {e}")
            return False

    def _rotate_ip(self) -> bool:
        """Rotate to a new IP address"""
        if not self._init_rotation_manager():
            return False

        try:
            print(f"[IP-REFRESH] Rotating IP (current: {self.current_ip})...")
            result = self.rotation_manager.rotate()

            if result.rotated:
                new_ip = result.ip_info.get('ip', 'unknown')
                print(f"[IP-REFRESH] ✓ Rotated to new IP: {new_ip}")
                self.current_ip = new_ip

                # Wait a bit for the new connection to stabilize
                time.sleep(3)
                return True
            else:
                print("[IP-REFRESH] ⚠ IP did not change, but continuing anyway")
                return True

        except Exception as e:
            print(f"[IP-REFRESH] Rotation failed: {e}")
            return False

    def refresh_with_rotation(
        self,
        account_email: str,
        account_password: str,
        account_username: Optional[str] = None,
        headless: bool = False,
        max_refresh_attempts: int = 3
    ) -> Optional[Dict]:
        """
        Refresh cookies with automatic IP rotation on rate limits

        Args:
            account_email: Twitter account email
            account_password: Twitter account password
            account_username: Twitter username (for verification)
            headless: Whether to run browser in headless mode
            max_refresh_attempts: Max attempts per IP before rotating

        Returns:
            Cookie dict if successful, None otherwise
        """

        print("=" * 60)
        print("Twitter Cookie Refresh with IP Rotation")
        print("=" * 60)
        print(f"[IP-REFRESH] Backend: {self.backend}")
        print(f"[IP-REFRESH] Account: {account_email}")

        # Initialize rotation manager
        if not self._init_rotation_manager():
            print("[IP-REFRESH] WARNING: IP rotation not available, continuing without it")
            # Fall back to regular refresh without rotation
            return refresh_cookies(
                headless=headless,
                account_email=account_email,
                account_password=account_password,
                account_username=account_username
            )

        ip_attempt = 0
        total_attempts = 0

        while ip_attempt < self.max_ip_attempts:
            ip_attempt += 1

            # Try refresh on current IP
            for refresh_attempt in range(1, max_refresh_attempts + 1):
                total_attempts += 1

                print(f"\n[IP-REFRESH] IP Attempt {ip_attempt}/{self.max_ip_attempts}, "
                      f"Refresh Attempt {refresh_attempt}/{max_refresh_attempts}")
                print(f"[IP-REFRESH] Current IP: {self.current_ip}")

                try:
                    # Call the original refresh function
                    cookies = refresh_cookies(
                        headless=headless,
                        account_email=account_email,
                        account_password=account_password,
                        account_username=account_username
                    )

                    if cookies:
                        print(f"[IP-REFRESH] ✓ SUCCESS! Got cookies on IP {self.current_ip}")
                        return cookies

                    # Check if it was an IP block by looking at the last error
                    # The refresh_cookies function already prints the error message
                    # We can detect it from the console output (not ideal but works)

                    # If None was returned, could be IP block or other error
                    print(f"[IP-REFRESH] Refresh attempt {refresh_attempt} failed")

                except Exception as e:
                    print(f"[IP-REFRESH] Exception during refresh: {e}")

                # Wait before retry on same IP
                if refresh_attempt < max_refresh_attempts:
                    wait_time = min(5 * refresh_attempt, 15)
                    print(f"[IP-REFRESH] Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)

            # All attempts on this IP failed - rotate to new IP
            if ip_attempt < self.max_ip_attempts:
                print(f"\n[IP-REFRESH] All attempts failed on IP {self.current_ip}")
                print(f"[IP-REFRESH] Rotating to new IP...")

                if not self._rotate_ip():
                    print("[IP-REFRESH] ✗ Failed to rotate IP, giving up")
                    break

                # Wait a bit after rotation before trying again
                print("[IP-REFRESH] Waiting 10s after IP rotation...")
                time.sleep(10)

        print(f"\n[IP-REFRESH] ✗ FAILED after {total_attempts} attempts across {ip_attempt} IPs")
        return None


def detect_ip_block_in_logs(log_file: Optional[Path] = None) -> bool:
    """
    Check recent logs for IP block indicators

    Returns:
        True if IP block detected, False otherwise
    """
    indicators = [
        "could not log you in now",
        "please try again later",
        "rate limit detected",
        "twitter rate limit",
        "too many login attempts"
    ]

    if log_file and log_file.exists():
        try:
            # Read last 50 lines of log
            with open(log_file, 'r') as f:
                lines = f.readlines()[-50:]

            text = ' '.join(lines).lower()
            for indicator in indicators:
                if indicator in text:
                    return True
        except Exception:
            pass

    return False


def auto_refresh_cookies_with_rotation(
    client=None,
    cookies_path: str = "cookies/cookies.json",
    backend: str = "tor",
    force_rotation: bool = False
) -> Optional[Dict]:
    """
    Enhanced auto-refresh with IP rotation support

    Args:
        client: Existing twikit client (for compatibility)
        cookies_path: Path to save cookies
        backend: IP rotation backend (tor, adb, proton)
        force_rotation: Force IP rotation even if not blocked

    Returns:
        New client if successful, None otherwise
    """
    from dotenv import load_dotenv
    load_dotenv(override=True)

    # Get credentials
    account_email = os.getenv('TWITTER_ACCOUNT1_EMAIL', os.getenv('TWITTER_EMAIL'))
    account_password = os.getenv('TWITTER_PASSWORD')
    account_username = os.getenv('TWITTER_ACCOUNT1_USERNAME', os.getenv('TWITTER_USERNAME'))

    if not account_email or not account_password:
        print("[IP-REFRESH] ERROR: Missing Twitter credentials in .env")
        return None

    # Determine if orchestrator mode
    orchestrator_mode = os.getenv('ORCHESTRATOR_RUNNING', 'false').lower() == 'true'
    headless = not orchestrator_mode  # Use headless unless orchestrator is running

    # Check if we should rotate IP first
    if force_rotation:
        print("[IP-REFRESH] Force rotation requested")
        refresher = IPRotatingCookieRefresher(backend=backend)
        refresher._rotate_ip()
        time.sleep(5)

    # Create refresher
    refresher = IPRotatingCookieRefresher(backend=backend, max_ip_attempts=3)

    # Try refresh with rotation
    cookies = refresher.refresh_with_rotation(
        account_email=account_email,
        account_password=account_password,
        account_username=account_username,
        headless=headless,
        max_refresh_attempts=2
    )

    if cookies:
        # Save cookies
        if save_cookies(cookies, Path(cookies_path)):
            print(f"[IP-REFRESH] ✓ Cookies saved to {cookies_path}")

            # Create new client with fresh cookies
            try:
                from twikit import Client
                new_client = Client()
                new_client.set_cookies(cookies)
                return new_client
            except Exception as e:
                print(f"[IP-REFRESH] Failed to create client: {e}")
                return None
        else:
            print("[IP-REFRESH] Failed to save cookies")
            return None
    else:
        print("[IP-REFRESH] Failed to refresh cookies even with IP rotation")
        return None


def main():
    """Command-line interface for testing"""
    import argparse

    parser = argparse.ArgumentParser(description='Refresh Twitter cookies with IP rotation')
    parser.add_argument('--backend', choices=['tor', 'adb', 'proton'], default='tor',
                        help='IP rotation backend to use')
    parser.add_argument('--headless', action='store_true',
                        help='Run browser in headless mode')
    parser.add_argument('--force-rotation', action='store_true',
                        help='Force IP rotation before attempting')
    parser.add_argument('--account', type=int, default=1,
                        help='Account number (1-4)')

    args = parser.parse_args()

    # Load credentials
    from dotenv import load_dotenv
    load_dotenv(override=True)

    if args.account == 1:
        account_email = os.getenv('TWITTER_ACCOUNT1_EMAIL', os.getenv('TWITTER_EMAIL'))
        account_password = os.getenv('TWITTER_PASSWORD')
        account_username = os.getenv('TWITTER_ACCOUNT1_USERNAME', os.getenv('TWITTER_USERNAME'))
    else:
        account_email = os.getenv(f'TWITTER_EMAIL_{args.account}')
        account_password = os.getenv(f'TWITTER_PASSWORD_{args.account}')
        account_username = os.getenv(f'TWITTER_USERNAME_{args.account}')

    if not account_email or not account_password:
        print("ERROR: Missing credentials in .env file")
        return 1

    # Run refresh
    refresher = IPRotatingCookieRefresher(backend=args.backend)

    if args.force_rotation:
        print("Rotating IP first...")
        refresher._rotate_ip()
        time.sleep(5)

    cookies = refresher.refresh_with_rotation(
        account_email=account_email,
        account_password=account_password,
        account_username=account_username,
        headless=args.headless
    )

    if cookies:
        save_cookies(cookies, COOKIES_PATH)
        print("\n✓ SUCCESS! Cookies refreshed and saved")
        return 0
    else:
        print("\n✗ FAILED to refresh cookies")
        return 1


if __name__ == "__main__":
    sys.exit(main())
