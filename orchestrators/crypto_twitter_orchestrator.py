"""
Crypto Twitter Orchestrator
Manages all crypto Twitter sentiment scrapers in parallel
Monitors health and auto-restarts failed scrapers
"""

import subprocess
import time
import os
import sys
import threading
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Crypto Twitter scrapers to run
CRYPTO_TWITTER_SCRAPERS = [
    {
        'name': 'Twitter Meme Coins',
        'script': 'crypto_scrapers/twitter_memecoins.py',
        'tokens': 'PEPE, DOGE, SHIB, BONK, WIF',
        'enabled': True
    },
    {
        'name': 'Twitter Large Caps',
        'script': 'crypto_scrapers/twitter_largecaps.py',
        'tokens': 'BTC, ETH, SOL, BNB, XRP, ADA, TRX',
        'enabled': True
    },
    {
        'name': 'Twitter DeFi',
        'script': 'crypto_scrapers/twitter_defi.py',
        'tokens': 'UNI, AAVE, LDO, MKR, CRV, GMX, SNX',
        'enabled': True
    },
    {
        'name': 'Twitter Layer 1s',
        'script': 'crypto_scrapers/twitter_layer1s.py',
        'tokens': 'AVAX, DOT, NEAR, ATOM, ICP, ALGO, FTM',
        'enabled': True
    },
    {
        'name': 'Twitter Layer 2s',
        'script': 'crypto_scrapers/twitter_layer2s.py',
        'tokens': 'ARB, OP, MATIC, METIS, IMX',
        'enabled': True
    },
    {
        'name': 'Twitter AI/ML',
        'script': 'crypto_scrapers/twitter_ai.py',
        'tokens': 'RENDER, FET, GRT, OCEAN, AGIX, TAO, RNDR',
        'enabled': True
    },
    {
        'name': 'Twitter Whale Tracker',
        'script': 'crypto_scrapers/twitter_whales.py',
        'tokens': '38 whale accounts',
        'enabled': True
    }
]

class CryptoTwitterOrchestrator:
    def __init__(self):
        self.processes = {}
        self.start_times = {}
        self.restart_counts = {}
        self.project_root = Path(__file__).parent.parent
        self.output_threads = {}

    def stream_output(self, scraper_name, stream, stream_type):
        """Stream output from a scraper to console with timestamps"""
        try:
            for line in iter(stream.readline, ''):
                if line:
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    line = line.rstrip()
                    # Only show critical events - keep it clean
                    show_line = False

                    # Always show these
                    if any(keyword in line for keyword in ['VOLUME SPIKE', 'MOMENTUM ALERT', 'ERROR', 'WARN',
                                                           'FATAL', 'Rate limited', 'Cookie refresh']):
                        show_line = True

                    # Show cycle summaries (but filter out initialization spam)
                    elif 'Saved' in line and 'tweets' in line:
                        show_line = True
                    elif 'Cycle Summary' in line or 'cycle in' in line:
                        show_line = True

                    # Whale tracker - only show if tweets found (suppress "No new tweets" spam)
                    elif scraper_name == 'Twitter Whale Tracker':
                        if 'Found' in line and 'tweets' in line:
                            show_line = True
                        elif 'Cycle completed' in line:
                            show_line = True

                    if show_line:
                        print(f"[{timestamp}] [{scraper_name}] {line}", flush=True)
        except Exception as e:
            pass

    def start_scraper(self, scraper):
        """Start a single scraper process"""
        script_path = self.project_root / scraper['script']

        if not script_path.exists():
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] [ERROR] Script not found: {script_path}")
            return False

        try:
            # Start the scraper process with unbuffered output
            process = subprocess.Popen(
                [sys.executable, '-u', str(script_path)],  # -u flag disables buffering
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.project_root),
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            self.processes[scraper['name']] = process
            self.start_times[scraper['name']] = datetime.now()
            self.restart_counts[scraper['name']] = self.restart_counts.get(scraper['name'], 0)

            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] [STARTED] {scraper['name']} (PID: {process.pid})")
            print(f"[{timestamp}]           Tracking: {scraper['tokens']}")

            # Start threads to stream stdout and stderr
            stdout_thread = threading.Thread(
                target=self.stream_output,
                args=(scraper['name'], process.stdout, 'stdout'),
                daemon=True
            )
            stderr_thread = threading.Thread(
                target=self.stream_output,
                args=(scraper['name'], process.stderr, 'stderr'),
                daemon=True
            )

            stdout_thread.start()
            stderr_thread.start()

            self.output_threads[scraper['name']] = (stdout_thread, stderr_thread)

            return True

        except Exception as e:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] [ERROR] Failed to start {scraper['name']}: {e}")
            return False

    def check_health(self):
        """Check if all scrapers are running, restart if needed"""
        timestamp = datetime.now().strftime('%H:%M:%S')

        dead_scrapers = []
        for scraper in CRYPTO_TWITTER_SCRAPERS:
            if not scraper['enabled']:
                continue

            name = scraper['name']

            # Check if process exists and is running
            if name not in self.processes or self.processes[name].poll() is not None:
                # Process died or doesn't exist
                if name in self.processes:
                    exit_code = self.processes[name].poll()
                    dead_scrapers.append(name)
                    print(f"\n[{timestamp}] [DIED] {name} exited with code {exit_code}")
                    print(f"[{timestamp}] [RESTART] Restarting {name}...")
                    self.restart_counts[name] = self.restart_counts.get(name, 0) + 1

                    if self.restart_counts[name] > 10:
                        print(f"[{timestamp}] [CRITICAL] {name} has restarted {self.restart_counts[name]} times - may need manual intervention")

                # Start or restart the scraper
                self.start_scraper(scraper)

        # Only print health check if there were issues (keep output clean)
        if not dead_scrapers:
            print(f"[{timestamp}] [HEALTH] All scrapers OK")

    def print_status(self):
        """Print current status of all scrapers"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{timestamp}] ========== FLEET STATUS ==========")

        running = 0
        stopped = 0

        for scraper in CRYPTO_TWITTER_SCRAPERS:
            if not scraper['enabled']:
                continue

            name = scraper['name']

            if name in self.processes and self.processes[name].poll() is None:
                uptime = datetime.now() - self.start_times[name]
                uptime_str = str(uptime).split('.')[0]  # Remove microseconds
                restarts = self.restart_counts.get(name, 0)
                print(f"[{timestamp}] [{name}] UP {uptime_str} | Restarts: {restarts}")
                running += 1
            else:
                print(f"[{timestamp}] [{name}] STOPPED")
                stopped += 1

        print(f"[{timestamp}] Summary: {running} running, {stopped} stopped")
        print(f"[{timestamp}] =====================================\n")

    def run(self):
        """Main orchestrator loop"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print("\n" + "="*80)
        print(f"[{timestamp}] Crypto Twitter Orchestrator - Starting All Scrapers")
        print("="*80)
        print(f"Total scrapers: {len([s for s in CRYPTO_TWITTER_SCRAPERS if s['enabled']])}")
        print(f"Total tokens tracked: 41 tokens + 38 whale accounts")
        print("="*80 + "\n")

        # Start all enabled scrapers
        for scraper in CRYPTO_TWITTER_SCRAPERS:
            if scraper['enabled']:
                self.start_scraper(scraper)
                time.sleep(2)  # Stagger starts to avoid rate limit collisions

        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{timestamp}] [OK] All scrapers started successfully")
        print(f"[{timestamp}] [INFO] Health checks every 60 seconds, status table every 10 minutes")
        print(f"[{timestamp}] [INFO] Press Ctrl+C to stop all scrapers\n")

        try:
            status_counter = 0
            while True:
                time.sleep(60)  # Check health every minute
                self.check_health()

                status_counter += 1
                if status_counter >= 10:  # Print status table every 10 minutes
                    self.print_status()
                    status_counter = 0

        except KeyboardInterrupt:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"\n\n[{timestamp}] [SHUTDOWN] Stopping all scrapers...")
            self.stop_all()
            print(f"[{timestamp}] [OK] All scrapers stopped")

    def stop_all(self):
        """Stop all running scrapers"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        for name, process in self.processes.items():
            if process.poll() is None:  # Still running
                print(f"[{timestamp}] [STOPPING] {name}...")
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    print(f"[{timestamp}] [FORCE KILL] {name} didn't stop gracefully")
                    process.kill()

if __name__ == "__main__":
    orchestrator = CryptoTwitterOrchestrator()
    orchestrator.run()
