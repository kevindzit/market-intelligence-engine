"""
Crypto Twitter Orchestrator
Manages all crypto Twitter sentiment scrapers in parallel
Monitors health and auto-restarts failed scrapers
"""

import subprocess
import time
import os
import sys
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

    def start_scraper(self, scraper):
        """Start a single scraper process"""
        script_path = self.project_root / scraper['script']

        if not script_path.exists():
            print(f"[ERROR] Script not found: {script_path}")
            return False

        try:
            # Start the scraper process
            process = subprocess.Popen(
                [sys.executable, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.project_root),
                text=True,
                bufsize=1
            )

            self.processes[scraper['name']] = process
            self.start_times[scraper['name']] = datetime.now()
            self.restart_counts[scraper['name']] = self.restart_counts.get(scraper['name'], 0)

            print(f"[STARTED] {scraper['name']} (PID: {process.pid})")
            print(f"          Tracking: {scraper['tokens']}")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to start {scraper['name']}: {e}")
            return False

    def check_health(self):
        """Check if all scrapers are running, restart if needed"""
        for scraper in CRYPTO_TWITTER_SCRAPERS:
            if not scraper['enabled']:
                continue

            name = scraper['name']

            # Check if process exists and is running
            if name not in self.processes or self.processes[name].poll() is not None:
                # Process died or doesn't exist
                if name in self.processes:
                    exit_code = self.processes[name].poll()
                    print(f"\n[DIED] {name} exited with code {exit_code}")
                    print(f"[RESTART] Restarting {name}...")
                    self.restart_counts[name] = self.restart_counts.get(name, 0) + 1

                    if self.restart_counts[name] > 10:
                        print(f"[CRITICAL] {name} has restarted {self.restart_counts[name]} times - may need manual intervention")

                # Start or restart the scraper
                self.start_scraper(scraper)

    def print_status(self):
        """Print current status of all scrapers"""
        print("\n" + "="*80)
        print("Crypto Twitter Scraper Fleet Status")
        print("="*80)
        print(f"{'Scraper':<30} | {'Status':<12} | {'Uptime':<15} | {'Restarts':<10}")
        print("-"*80)

        for scraper in CRYPTO_TWITTER_SCRAPERS:
            if not scraper['enabled']:
                continue

            name = scraper['name']

            if name in self.processes and self.processes[name].poll() is None:
                status = "✓ RUNNING"
                uptime = datetime.now() - self.start_times[name]
                uptime_str = str(uptime).split('.')[0]  # Remove microseconds
                restarts = self.restart_counts.get(name, 0)
            else:
                status = "✗ STOPPED"
                uptime_str = "N/A"
                restarts = self.restart_counts.get(name, 0)

            print(f"{name:<30} | {status:<12} | {uptime_str:<15} | {restarts:<10}")

        print("="*80)

    def run(self):
        """Main orchestrator loop"""
        print("\n" + "="*80)
        print("Crypto Twitter Orchestrator - Starting All Scrapers")
        print("="*80)
        print(f"Total scrapers: {len([s for s in CRYPTO_TWITTER_SCRAPERS if s['enabled']])}")
        print(f"Total tokens tracked: 41 tokens + 38 whale accounts")
        print("="*80 + "\n")

        # Start all enabled scrapers
        for scraper in CRYPTO_TWITTER_SCRAPERS:
            if scraper['enabled']:
                self.start_scraper(scraper)
                time.sleep(2)  # Stagger starts to avoid rate limit collisions

        print("\n[OK] All scrapers started successfully")
        print("[INFO] Monitoring health every 60 seconds...")
        print("[INFO] Press Ctrl+C to stop all scrapers\n")

        try:
            status_counter = 0
            while True:
                time.sleep(60)  # Check health every minute
                self.check_health()

                status_counter += 1
                if status_counter >= 5:  # Print status every 5 minutes
                    self.print_status()
                    status_counter = 0

        except KeyboardInterrupt:
            print("\n\n[SHUTDOWN] Stopping all scrapers...")
            self.stop_all()
            print("[OK] All scrapers stopped")

    def stop_all(self):
        """Stop all running scrapers"""
        for name, process in self.processes.items():
            if process.poll() is None:  # Still running
                print(f"[STOPPING] {name}...")
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    print(f"[FORCE KILL] {name} didn't stop gracefully")
                    process.kill()

if __name__ == "__main__":
    orchestrator = CryptoTwitterOrchestrator()
    orchestrator.run()
