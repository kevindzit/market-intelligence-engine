"""
Twitter IP Block Monitor for Orchestrator
Monitors scrapers for IP block indicators and triggers rotation
"""

import os
import sys
import time
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TwitterIPMonitor:
    """Monitor Twitter scrapers for IP blocks and trigger rotation"""

    def __init__(self, backend: str = "tor", check_interval: int = 60):
        """
        Initialize the IP monitor

        Args:
            backend: IP rotation backend (tor, adb, proton)
            check_interval: Seconds between IP block checks
        """
        self.backend = backend
        self.check_interval = check_interval
        self.running = False
        self.monitor_thread = None
        self.last_rotation = None
        self.rotation_cooldown = 300  # 5 minutes between rotations
        self.ip_block_indicators = [
            "could not log you in now",
            "please try again later",
            "rate limit detected",
            "twitter rate limit",
            "too many login attempts",
            "something went wrong",
            "verify you are human",
            "cloudflare"
        ]
        self.block_counts = defaultdict(int)
        self.last_check = {}

        # Paths to monitor
        self.log_dirs = [
            Path(__file__).parent.parent / "logs",
            Path(__file__).parent.parent / "outputs"
        ]

    def check_logs_for_blocks(self) -> bool:
        """
        Check recent logs for IP block indicators

        Returns:
            True if IP block detected, False otherwise
        """
        block_detected = False
        current_time = time.time()

        for log_dir in self.log_dirs:
            if not log_dir.exists():
                continue

            # Check all .txt and .log files modified in last 5 minutes
            for log_file in log_dir.glob("**/*.txt"):
                try:
                    # Skip if file not modified recently
                    mtime = log_file.stat().st_mtime
                    if current_time - mtime > 300:  # 5 minutes
                        continue

                    # Skip if we checked this file recently
                    last_check = self.last_check.get(str(log_file), 0)
                    if current_time - last_check < 30:  # 30 seconds
                        continue

                    # Read last 100 lines
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()[-100:]

                    content = ' '.join(lines).lower()

                    # Check for indicators
                    for indicator in self.ip_block_indicators:
                        if indicator in content:
                            print(f"[IP-MONITOR] Block indicator '{indicator}' found in {log_file.name}")
                            self.block_counts[indicator] += 1
                            block_detected = True

                    self.last_check[str(log_file)] = current_time

                except Exception as e:
                    # Ignore file read errors
                    pass

        return block_detected

    def can_rotate(self) -> bool:
        """Check if enough time has passed since last rotation"""
        if self.last_rotation is None:
            return True

        elapsed = time.time() - self.last_rotation
        return elapsed >= self.rotation_cooldown

    def rotate_ip(self) -> bool:
        """Trigger IP rotation"""
        if not self.can_rotate():
            wait_time = self.rotation_cooldown - (time.time() - self.last_rotation)
            print(f"[IP-MONITOR] Rotation on cooldown for {int(wait_time)}s")
            return False

        try:
            print(f"[IP-MONITOR] Triggering IP rotation via {self.backend}...")

            # Run IP rotation command
            cmd = [
                sys.executable,
                str(Path(__file__).parent.parent / "IP_bypass" / "runner.py"),
                "rotate",
                "--backend", self.backend
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                print(f"[IP-MONITOR] ✓ IP rotation successful")
                self.last_rotation = time.time()
                self.block_counts.clear()  # Reset block counts after rotation
                return True
            else:
                print(f"[IP-MONITOR] ✗ IP rotation failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print(f"[IP-MONITOR] ✗ IP rotation timed out")
            return False
        except Exception as e:
            print(f"[IP-MONITOR] ✗ IP rotation error: {e}")
            return False

    def monitor_loop(self):
        """Main monitoring loop"""
        print(f"[IP-MONITOR] Started monitoring (backend: {self.backend})")

        consecutive_blocks = 0

        while self.running:
            try:
                # Check for IP blocks
                if self.check_logs_for_blocks():
                    consecutive_blocks += 1
                    print(f"[IP-MONITOR] IP block detected ({consecutive_blocks} consecutive)")

                    # Trigger rotation after 2 consecutive detections
                    if consecutive_blocks >= 2:
                        if self.rotate_ip():
                            consecutive_blocks = 0

                            # Kill all Twitter scrapers to force reconnection
                            self.restart_twitter_scrapers()

                            # Wait longer after rotation
                            time.sleep(30)
                        else:
                            # Rotation failed or on cooldown, wait longer
                            time.sleep(self.check_interval * 2)
                else:
                    # No block detected, reset counter
                    if consecutive_blocks > 0:
                        print(f"[IP-MONITOR] No block detected, resetting counter")
                    consecutive_blocks = 0

            except Exception as e:
                print(f"[IP-MONITOR] Error in monitor loop: {e}")

            # Wait before next check
            time.sleep(self.check_interval)

        print(f"[IP-MONITOR] Stopped monitoring")

    def restart_twitter_scrapers(self):
        """Send signal to orchestrator to restart Twitter scrapers"""
        print(f"[IP-MONITOR] Signaling orchestrator to restart Twitter scrapers...")

        # Create a signal file that orchestrator can check
        signal_file = Path(__file__).parent.parent / "outputs" / ".restart_twitter_scrapers"
        try:
            signal_file.touch()
            print(f"[IP-MONITOR] Restart signal created")
        except Exception as e:
            print(f"[IP-MONITOR] Failed to create restart signal: {e}")

    def start(self):
        """Start the monitoring thread"""
        if self.running:
            print(f"[IP-MONITOR] Already running")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
        print(f"[IP-MONITOR] Monitor thread started")

    def stop(self):
        """Stop the monitoring thread"""
        if not self.running:
            return

        print(f"[IP-MONITOR] Stopping monitor...")
        self.running = False

        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        print(f"[IP-MONITOR] Monitor stopped")


def integrate_with_orchestrator():
    """
    Function to be called by orchestrator to start IP monitoring

    Returns:
        TwitterIPMonitor instance
    """
    # Check if Tor is available
    backend = os.getenv('IP_ROTATION_BACKEND', 'tor')

    # Create and start monitor
    monitor = TwitterIPMonitor(backend=backend, check_interval=60)
    monitor.start()

    return monitor


def main():
    """Standalone monitoring mode"""
    import argparse

    parser = argparse.ArgumentParser(description='Monitor Twitter scrapers for IP blocks')
    parser.add_argument('--backend', choices=['tor', 'adb', 'proton'], default='tor',
                        help='IP rotation backend')
    parser.add_argument('--interval', type=int, default=60,
                        help='Seconds between checks')

    args = parser.parse_args()

    print("=" * 60)
    print("Twitter IP Block Monitor")
    print("=" * 60)
    print(f"Backend: {args.backend}")
    print(f"Check interval: {args.interval}s")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    monitor = TwitterIPMonitor(backend=args.backend, check_interval=args.interval)
    monitor.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping monitor...")
        monitor.stop()


if __name__ == "__main__":
    main()