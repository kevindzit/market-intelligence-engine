"""
Binance/VPN Orchestrator - Manages scrapers requiring non-US IP addresses
Includes all Binance data scrapers and other services blocked in the US
"""

import os
import sys
import time
import subprocess
import yaml
from datetime import datetime
from pathlib import Path

# Import shared functionality from base orchestrator
sys.path.insert(0, str(Path(__file__).parent.parent))
from orchestrators.base_orchestrator import (
    Fore, Style, PROJECT_ROOT, running_processes, scraper_start_times,
    parse_interval_seconds, format_time_since, get_start_stagger_seconds,
    start_scraper, stop_scraper, stop_all_scrapers, monitor_and_restart_scrapers,
    run_preflight_checks, check_database_connection, STREAMING_STAGGER_SECONDS
)

def check_tor_status():
    """Check if Tor service is running and accessible."""
    try:
        # Check if Tor is running via WSL
        result = subprocess.run(
            ['wsl', 'sudo', 'service', 'tor', 'status'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=5
        )

        if result.stdout and 'Active: active (running)' in result.stdout:
            return True, "Tor service is running"
        else:
            # Try to start Tor
            subprocess.run(['wsl', 'sudo', 'service', 'tor', 'start'],
                         capture_output=True, encoding='utf-8', errors='replace', timeout=10)
            time.sleep(3)

            # Check again
            result = subprocess.run(
                ['wsl', 'sudo', 'service', 'tor', 'status'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=5
            )

            if result.stdout and 'Active: active (running)' in result.stdout:
                return True, "Tor service started"
            else:
                return False, "Tor service not running"
    except FileNotFoundError:
        return False, "WSL not found (Tor runs in WSL)"
    except subprocess.TimeoutExpired:
        return False, "Tor check timed out"
    except Exception as e:
        return False, f"Tor check failed: {e}"

def check_current_ip():
    """Check current external IP address."""
    try:
        import requests

        # Check if using Tor proxy
        proxy_env = os.getenv('HTTP_PROXY')
        if proxy_env and 'socks5' in proxy_env:
            # Using Tor proxy
            response = requests.get('http://ipinfo.io/json',
                                  proxies={'http': proxy_env, 'https': proxy_env},
                                  timeout=10)
        else:
            # Direct connection
            response = requests.get('http://ipinfo.io/json', timeout=10)

        data = response.json()
        ip = data.get('ip', 'Unknown')
        country = data.get('country', 'Unknown')

        if country == 'US':
            return ip, country, False  # US IP - Binance won't work
        else:
            return ip, country, True   # Non-US IP - Good for Binance

    except Exception as e:
        return 'Unknown', 'Unknown', False

def load_vpn_scrapers():
    """Load configurations for scrapers that require VPN/non-US IP."""
    config_path = PROJECT_ROOT / 'config' / 'scrapers.yaml'

    if not config_path.exists():
        print(f"{Fore.RED}[ERROR] Config file not found: {config_path}{Style.RESET_ALL}")
        return []

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Filter for enabled VPN-required scrapers
        scrapers = []
        for scraper in config.get('scrapers', []):
            # Skip if disabled
            if not scraper.get('enabled', True):
                continue

            # Skip Twitter scrapers (handled by Twitter orchestrator)
            if 'twitter' in scraper['name'].lower():
                continue

            # Include if explicitly requires proxy/VPN or is Binance-related
            name_lower = scraper['name'].lower()
            if scraper.get('use_proxy', False) or 'binance' in name_lower:
                scrapers.append(scraper)

        return scrapers
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to load config: {e}{Style.RESET_ALL}")
        return []

def categorize_binance_scrapers(scrapers):
    """Categorize Binance scrapers by data type."""
    categories = {
        'Price Data': [],       # OHLCV
        'Market Depth': [],     # Order book, liquidations
        'Derivatives': [],      # Funding rates, open interest
    }

    for scraper in scrapers:
        name_lower = scraper['name'].lower()

        if 'ohlcv' in name_lower:
            categories['Price Data'].append(scraper)
        elif 'order book' in name_lower or 'liquidation' in name_lower:
            categories['Market Depth'].append(scraper)
        elif 'funding' in name_lower or 'open interest' in name_lower or 'oi' in name_lower:
            categories['Derivatives'].append(scraper)
        else:
            # Default to market depth for other Binance scrapers
            categories['Market Depth'].append(scraper)

    return categories

def start_vpn_scraper(scraper):
    """Start a scraper with VPN/proxy configuration."""
    env_overrides = {}

    # Set proxy environment variables if Tor is available
    tor_ok, _ = check_tor_status()
    if tor_ok:
        proxy_url = "socks5://127.0.0.1:9050"
        env_overrides.update({
            'HTTP_PROXY': proxy_url,
            'HTTPS_PROXY': proxy_url,
            'ALL_PROXY': proxy_url,
            'NO_PROXY': 'localhost,127.0.0.1'
        })
        print(f"{Fore.CYAN}[PROXY] {scraper['name']}: Using Tor proxy{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}[WARNING] {scraper['name']}: Starting without proxy (may fail){Style.RESET_ALL}")

    return start_scraper(scraper, env_overrides)

def display_dashboard(scrapers):
    """Display Binance/VPN scraper dashboard."""
    os.system('cls' if os.name == 'nt' else 'clear')

    print("="*80)
    print(" " * 20 + f"{Fore.MAGENTA}BINANCE/VPN ORCHESTRATOR{Style.RESET_ALL}")
    print(" " * 18 + "Requires Non-US IP Address")
    print("="*80)

    # Show IP status
    ip, country, is_good = check_current_ip()
    ip_color = Fore.GREEN if is_good else Fore.RED
    print(f"Current IP: {ip_color}{ip} ({country}){Style.RESET_ALL}")

    # Show Tor status
    tor_ok, tor_msg = check_tor_status()
    tor_color = Fore.GREEN if tor_ok else Fore.YELLOW
    print(f"Tor Status: {tor_color}{tor_msg}{Style.RESET_ALL}")

    print(f"\nStarted: {format_time_since(orchestrator_start_time)} ago | ")
    print(f"Active Scrapers: {len(running_processes)}")
    print("-"*80)

    # Show Binance scrapers by category
    categories = categorize_binance_scrapers(scrapers)

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
                interval = scraper.get('interval', 'unknown')
                print(f"  [{status}] {name:<30} | Every {interval:<10} | Up: {uptime}")
            else:
                interval = scraper.get('interval', 'unknown')
                print(f"  [{Fore.YELLOW}WAITING{Style.RESET_ALL}] {name:<30} | Every {interval}")

    # Show database stats
    db_ok, db_info = check_database_connection()
    if db_ok:
        print(f"\n{Fore.WHITE}DATABASE STATUS:{Style.RESET_ALL}")
        print(f"  Tables: {db_info['tables']} | Total Rows: {db_info['total_rows']:,}")

    # Show warnings if needed
    if not is_good:
        print(f"\n{Fore.RED}⚠ WARNING: US IP detected - Binance scrapers may fail!{Style.RESET_ALL}")
        print(f"  Consider using VPN or configuring Tor proxy")

    print("\n" + "="*80)
    print(f"Press Ctrl+C to stop all scrapers")
    print("="*80)

def main():
    """Main Binance/VPN orchestrator function."""
    global orchestrator_start_time
    orchestrator_start_time = datetime.now()

    print("\n" + "="*80)
    print(" " * 20 + f"{Fore.MAGENTA}BINANCE/VPN ORCHESTRATOR{Style.RESET_ALL}")
    print(" " * 15 + "For US-Blocked Services & APIs")
    print("="*80)

    # Check IP and Tor status
    print("\n[CHECK] Network status...")
    ip, country, is_good = check_current_ip()
    ip_color = Fore.GREEN if is_good else Fore.RED
    print(f"  Current IP: {ip_color}{ip} ({country}){Style.RESET_ALL}")

    tor_ok, tor_msg = check_tor_status()
    tor_color = Fore.GREEN if tor_ok else Fore.YELLOW
    print(f"  Tor proxy: {tor_color}{tor_msg}{Style.RESET_ALL}")

    if not is_good and not tor_ok:
        print(f"\n{Fore.YELLOW}⚠ WARNING: You have a US IP and no Tor proxy!{Style.RESET_ALL}")
        print("Binance and other US-blocked services will likely fail.")
        print("\nOptions:")
        print("  1. Start Tor: wsl sudo service tor start")
        print("  2. Use a VPN service")
        print("  3. Continue anyway (scrapers may fail)")

        response = input("\nContinue anyway? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print(f"{Fore.RED}[ABORT] Exiting...{Style.RESET_ALL}")
            return

    # Run preflight checks
    if not run_preflight_checks():
        response = input("\nContinue with warnings? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print(f"{Fore.RED}[ABORT] Exiting...{Style.RESET_ALL}")
            return

    # Load scrapers
    scrapers = load_vpn_scrapers()

    if not scrapers:
        print(f"{Fore.RED}[ERROR] No VPN-required scrapers found or enabled{Style.RESET_ALL}")
        return

    # Display scrapers by category
    categories = categorize_binance_scrapers(scrapers)

    print(f"\nFound {len(scrapers)} VPN-required scrapers:")
    print("-"*80)

    for category, category_scrapers in categories.items():
        if category_scrapers:
            print(f"\n{Fore.WHITE}Binance {category}:{Style.RESET_ALL}")
            for scraper in category_scrapers:
                interval = scraper.get('interval', 'unknown')
                print(f"  • {scraper['name']:<35} (runs every {interval})")

    print("\n" + "="*80)
    print("Starting Binance scrapers...")
    print("="*80 + "\n")

    # Start all scrapers with appropriate staggering
    for i, scraper in enumerate(scrapers):
        if i > 0:
            # Use minimal delay for high-frequency Binance scrapers
            delay = get_start_stagger_seconds(scraper)
            if delay > 0:
                print(f"[WAIT] Waiting {delay} seconds before starting next scraper...")
                time.sleep(delay)

        start_vpn_scraper(scraper)

    print(f"\n{Fore.GREEN}[SUCCESS] All {len(scrapers)} Binance scrapers started{Style.RESET_ALL}")

    if tor_ok:
        print(f"{Fore.CYAN}[INFO] Using Tor proxy for all scrapers{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}[WARNING] No proxy configured - scrapers may fail{Style.RESET_ALL}")

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
        print(f"\n{Fore.YELLOW}[SHUTDOWN] Stopping all Binance scrapers...{Style.RESET_ALL}")
        stop_all_scrapers()
        print(f"{Fore.GREEN}[COMPLETE] All scrapers stopped{Style.RESET_ALL}")

if __name__ == "__main__":
    main()