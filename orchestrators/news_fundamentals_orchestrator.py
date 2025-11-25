"""
News & Fundamentals Orchestrator - Manages scrapers that don't require VPN
Includes news, congressional trades, economic data, SEC filings, and crypto metrics
"""

import os
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path

# Import shared functionality from base orchestrator
sys.path.insert(0, str(Path(__file__).parent.parent))
from orchestrators.base_orchestrator import (
    Fore, Style, PROJECT_ROOT, running_processes, scraper_start_times,
    parse_interval_seconds, format_time_since, get_start_stagger_seconds,
    start_scraper, stop_scraper, stop_all_scrapers, monitor_and_restart_scrapers,
    run_preflight_checks, check_database_connection, DEFAULT_STAGGER_SECONDS
)

# Scrapers that don't require VPN/proxy
NON_VPN_SCRAPERS = [
    # News scrapers
    'newsapi reader',
    'rss aggregator',
    # Congressional data
    'senate scraper',
    'house scraper',
    # Economic data
    'fred economic data',
    # SEC filings
    'sec edgar reader',
    # Company fundamentals
    'fmp fundamentals',
    'yfinance fundamentals',
    # Crypto metrics (non-Binance)
    'fear & greed index',
    'stablecoin flow monitor',
    'exchange flows',
    'dex liquidity monitor',
    'defi tvl monitor',
    'options volatility monitor',
    'bridge flows monitor',
]

def load_non_vpn_scrapers():
    """Load configurations for scrapers that don't require VPN."""
    config_path = PROJECT_ROOT / 'config' / 'scrapers.yaml'

    if not config_path.exists():
        print(f"{Fore.RED}[ERROR] Config file not found: {config_path}{Style.RESET_ALL}")
        return []

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Filter for enabled non-VPN scrapers
        scrapers = []
        for scraper in config.get('scrapers', []):
            # Skip if disabled
            if not scraper.get('enabled', True):
                continue

            # Skip Twitter scrapers (handled by Twitter orchestrator)
            if 'twitter' in scraper['name'].lower():
                continue

            # Skip if explicitly requires proxy/VPN
            if scraper.get('use_proxy', False):
                continue

            # Check if it's in our non-VPN list
            name_lower = scraper['name'].lower()
            if any(nvs in name_lower for nvs in NON_VPN_SCRAPERS):
                scrapers.append(scraper)

        return scrapers
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to load config: {e}{Style.RESET_ALL}")
        return []

def categorize_scrapers(scrapers):
    """Categorize scrapers by type for organized display."""
    categories = {
        'News': [],
        'Congressional': [],
        'Economic': [],
        'SEC': [],
        'Fundamentals': [],
        'Crypto Metrics': [],
    }

    for scraper in scrapers:
        name_lower = scraper['name'].lower()

        if 'news' in name_lower or 'rss' in name_lower:
            categories['News'].append(scraper)
        elif 'senate' in name_lower or 'house' in name_lower:
            categories['Congressional'].append(scraper)
        elif 'fred' in name_lower:
            categories['Economic'].append(scraper)
        elif 'sec' in name_lower or 'edgar' in name_lower:
            categories['SEC'].append(scraper)
        elif 'fmp' in name_lower or 'yfinance' in name_lower:
            categories['Fundamentals'].append(scraper)
        else:
            categories['Crypto Metrics'].append(scraper)

    return categories

def display_dashboard(scrapers):
    """Display news/fundamentals scraper dashboard."""
    os.system('cls' if os.name == 'nt' else 'clear')

    print("="*80)
    print(" " * 15 + f"{Fore.GREEN}NEWS & FUNDAMENTALS ORCHESTRATOR{Style.RESET_ALL}")
    print(" " * 20 + "No VPN/Proxy Required")
    print("="*80)
    print(f"Started: {format_time_since(orchestrator_start_time)} ago | ")
    print(f"Active Scrapers: {len(running_processes)}")
    print("-"*80)

    # Categorize and display scrapers
    categories = categorize_scrapers(scrapers)

    for category, category_scrapers in categories.items():
        if not category_scrapers:
            continue

        print(f"\n{Fore.WHITE}{category.upper()}:{Style.RESET_ALL}")
        print("-"*40)

        for scraper in category_scrapers:
            name = scraper['name']
            process = running_processes.get(name)

            if process:
                if process.poll() is None:
                    status = f"{Fore.GREEN}RUNNING{Style.RESET_ALL}"
                else:
                    status = f"{Fore.RED}STOPPED{Style.RESET_ALL}"
                uptime = format_time_since(scraper_start_times.get(name))
                print(f"  [{status}] {name:<35} | Uptime: {uptime}")
            else:
                print(f"  [{Fore.YELLOW}WAITING{Style.RESET_ALL}] {name:<35}")

    # Show database stats
    db_ok, db_info = check_database_connection()
    if db_ok:
        print(f"\n{Fore.WHITE}DATABASE STATUS:{Style.RESET_ALL}")
        print(f"  Tables: {db_info['tables']} | Total Rows: {db_info['total_rows']:,}")

    # Show API status (if we have the info)
    print(f"\n{Fore.WHITE}API USAGE:{Style.RESET_ALL}")
    print(f"  NewsAPI: 100 calls/day (free)")
    print(f"  FMP: 250 calls/day (free)")
    print(f"  CoinGecko: 10k calls/month (free)")
    print(f"  DeFiLlama: Unlimited (free)")

    print("\n" + "="*80)
    print(f"Press Ctrl+C to stop all scrapers")
    print("="*80)

def main():
    """Main news/fundamentals orchestrator function."""
    global orchestrator_start_time
    orchestrator_start_time = datetime.now()

    print("\n" + "="*80)
    print(" " * 15 + f"{Fore.GREEN}NEWS & FUNDAMENTALS ORCHESTRATOR{Style.RESET_ALL}")
    print(" " * 18 + "Free APIs & Public Data")
    print("="*80)

    # Run preflight checks
    if not run_preflight_checks():
        response = input("\nContinue anyway? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print(f"{Fore.RED}[ABORT] Exiting...{Style.RESET_ALL}")
            return

    # Load scrapers
    scrapers = load_non_vpn_scrapers()

    if not scrapers:
        print(f"{Fore.RED}[ERROR] No news/fundamentals scrapers found or enabled{Style.RESET_ALL}")
        return

    # Display scrapers by category
    categories = categorize_scrapers(scrapers)

    print(f"\nFound {len(scrapers)} scrapers (no VPN required):")
    print("-"*80)

    for category, category_scrapers in categories.items():
        if category_scrapers:
            print(f"\n{Fore.WHITE}{category}:{Style.RESET_ALL}")
            for scraper in category_scrapers:
                interval = scraper.get('interval', 'unknown')
                mode = scraper.get('mode', 'daemon')
                mode_str = f" [{mode}]" if mode != 'daemon' else ""
                print(f"  • {scraper['name']:<35} (runs every {interval}){mode_str}")

    print("\n" + "="*80)
    print("Starting scrapers...")
    print("="*80 + "\n")

    # Start all scrapers with appropriate staggering
    for i, scraper in enumerate(scrapers):
        if i > 0:
            delay = get_start_stagger_seconds(scraper)
            if delay > 0:
                print(f"[WAIT] Waiting {delay} seconds before starting next scraper...")
                time.sleep(delay)

        start_scraper(scraper)

    print(f"\n{Fore.GREEN}[SUCCESS] All {len(scrapers)} scrapers started{Style.RESET_ALL}")
    print("="*80)

    # Start monitoring in a separate thread
    import threading
    monitor_thread = threading.Thread(
        target=monitor_and_restart_scrapers,
        args=(scrapers,),
        daemon=True
    )
    monitor_thread.start()

    # Main loop - display dashboard
    try:
        while True:
            time.sleep(30)
            display_dashboard(scrapers)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[SHUTDOWN] Stopping all scrapers...{Style.RESET_ALL}")
        stop_all_scrapers()
        print(f"{Fore.GREEN}[COMPLETE] All scrapers stopped{Style.RESET_ALL}")

if __name__ == "__main__":
    main()