"""
Twitter Orchestrator - Manages all Twitter scrapers with mobile emulation
Monitors Twitter sentiment scrapers with auto-refresh cookies and mobile user agents
"""

import os
import sys
import time
import random
import yaml
import psycopg2
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, deque

# Import shared functionality from base orchestrator
sys.path.insert(0, str(Path(__file__).parent.parent))
from orchestrators.base_orchestrator import (
    Fore, Style, PROJECT_ROOT, running_processes, scraper_start_times,
    parse_interval_seconds, get_python_executable, format_time_since,
    get_start_stagger_seconds, start_scraper, stop_scraper, stop_all_scrapers,
    monitor_and_restart_scrapers, run_preflight_checks, check_database_connection,
    TWITTER_STAGGER_SECONDS, scraper_logs
)

# Mobile User Agents for Twitter scrapers (November 2025)
MOBILE_USER_AGENTS = [
    # iPhone 15 Pro - iOS 18
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
    # Samsung Galaxy S24 - Android 14
    'Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36',
    # Google Pixel 8 Pro - Android 14
    'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.111 Mobile Safari/537.36',
    # OnePlus 12 - Android 14
    'Mozilla/5.0 (Linux; Android 14; CPH2581) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.193 Mobile Safari/537.36',
    # iPhone 14 - iOS 17
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
]

# Global tracking for tweet activity
tweet_counts = defaultdict(lambda: deque(maxlen=100))  # Track last 100 updates per scraper
recent_errors = deque(maxlen=20)  # Track last 20 errors
dashboard_update_time = None

def get_random_mobile_user_agent():
    """Get a random mobile user agent for variation."""
    return random.choice(MOBILE_USER_AGENTS)

def get_tweet_counts_by_time():
    """Get real tweet counts from database for different time periods."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 54594)),
            dbname=os.getenv('DB_NAME', 'pjx'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'postgres')
        )

        time_periods = {
            '15min': 15,
            '30min': 30,
            '45min': 45,
            '1hr': 60,
            '2hr': 120,
            '4hr': 240,
            '8hr': 480,
            '12hr': 720,
            '24hr': 1440
        }

        counts = {}
        with conn.cursor() as cur:
            for period_name, minutes in time_periods.items():
                cur.execute("""
                    SELECT COUNT(*)
                    FROM twitter_sentiment
                    WHERE scraped_at >= NOW() - INTERVAL '%s minutes'
                """, (minutes,))
                counts[period_name] = cur.fetchone()[0]

        conn.close()
        return counts
    except Exception as e:
        return None

def get_tweets_by_scraper(minutes=15):
    """Get real tweet counts per scraper from database."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 54594)),
            dbname=os.getenv('DB_NAME', 'pjx'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'postgres')
        )

        scraper_counts = {}
        with conn.cursor() as cur:
            # Map scraper names to source field in database
            source_map = {
                'Twitter Meme Coins': 'memecoins',
                'Twitter Large Caps': 'largecaps',
                'Twitter DeFi': 'defi',
                'Twitter Layer 1s': 'layer1s',
                'Twitter Layer 2s': 'layer2s',
                'Twitter AI/ML': 'ai',
                'Twitter Whale Tracker': 'whale_tracker'
            }

            for scraper_name, source in source_map.items():
                cur.execute("""
                    SELECT COUNT(*)
                    FROM twitter_sentiment
                    WHERE source = %s
                    AND scraped_at >= NOW() - INTERVAL '%s minutes'
                """, (source, minutes))
                result = cur.fetchone()
                scraper_counts[scraper_name] = result[0] if result else 0

        conn.close()
        return scraper_counts
    except Exception:
        return {}

def get_last_tweet_times():
    """Get minutes since last tweet per scraper (based on scraped_at)."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 54594)),
            dbname=os.getenv('DB_NAME', 'pjx'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'postgres')
        )

        last_seen = {}
        with conn.cursor() as cur:
            source_map = {
                'Twitter Meme Coins': 'memecoins',
                'Twitter Large Caps': 'largecaps',
                'Twitter DeFi': 'defi',
                'Twitter Layer 1s': 'layer1s',
                'Twitter Layer 2s': 'layer2s',
                'Twitter AI/ML': 'ai',
                'Twitter Whale Tracker': 'whale_tracker'
            }

            for scraper_name, source in source_map.items():
                cur.execute("""
                    SELECT MAX(scraped_at)
                    FROM twitter_sentiment
                    WHERE source = %s
                """, (source,))
                result = cur.fetchone()
                last_ts = result[0] if result else None
                if last_ts:
                    minutes_ago = (datetime.now() - last_ts).total_seconds() / 60
                    last_seen[scraper_name] = minutes_ago
                else:
                    last_seen[scraper_name] = None

        conn.close()
        return last_seen
    except Exception:
        return {}

def get_recent_alerts():
    """Get recent high-alert tweets from database."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 54594)),
            dbname=os.getenv('DB_NAME', 'pjx'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'postgres')
        )

        alerts = []
        with conn.cursor() as cur:
            cur.execute("""
                SELECT token, alert_level, volume_spike, bot_probability
                FROM twitter_sentiment
                WHERE scraped_at >= NOW() - INTERVAL '5 minutes'
                AND (alert_level = 'HIGH' OR volume_spike > 2.0 OR bot_probability > 0.8)
                ORDER BY scraped_at DESC
                LIMIT 5
            """)
            alerts = cur.fetchall()

        conn.close()
        return alerts
    except Exception:
        return []

def check_cookie_status():
    """Check Twitter cookie file status."""
    cookie_file = PROJECT_ROOT / 'cookies' / 'cookies.json'

    if not cookie_file.exists():
        return False, "Cookie file not found"

    try:
        # Check cookie file age
        cookie_age = datetime.now() - datetime.fromtimestamp(cookie_file.stat().st_mtime)
        age_hours = cookie_age.total_seconds() / 3600

        if age_hours > 24:
            return True, f"Cookies are {age_hours:.1f} hours old (may need refresh)"
        else:
            return True, f"Cookies are {age_hours:.1f} hours old"
    except Exception as e:
        return False, str(e)

def check_all_cookie_accounts():
    """Check status of all Twitter cookie accounts."""
    cookies_dir = PROJECT_ROOT / 'cookies'

    if not cookies_dir.exists():
        return []

    accounts = []

    # Check for cookie files (excluding backups)
    for cookie_file in cookies_dir.glob('cookies*.json'):
        # Skip backup files
        if 'backup' in cookie_file.name.lower():
            continue

        try:
            # Get file stats
            stat_info = cookie_file.stat()
            last_modified = datetime.fromtimestamp(stat_info.st_mtime)
            age = datetime.now() - last_modified
            age_hours = age.total_seconds() / 3600

            # Determine account name
            if cookie_file.name == 'cookies.json':
                account_name = 'Main Account'
            elif 'account1' in cookie_file.name:
                account_name = 'Account 1'
            elif 'account2' in cookie_file.name:
                account_name = 'Account 2'
            elif 'account3' in cookie_file.name:
                account_name = 'Account 3'
            elif 'account4' in cookie_file.name:
                account_name = 'Account 4'
            else:
                # Extract account name from filename
                account_name = cookie_file.stem.replace('cookies_', '').replace('cookies', 'Main')

            # Determine if working (recently used)
            if age_hours < 2:
                status = 'ACTIVE'
                status_color = Fore.GREEN
            elif age_hours < 24:
                status = 'OK'
                status_color = Fore.GREEN
            elif age_hours < 48:
                status = 'OLD'
                status_color = Fore.YELLOW
            else:
                status = 'STALE'
                status_color = Fore.RED

            accounts.append({
                'name': account_name,
                'file': cookie_file.name,
                'last_updated': last_modified,
                'age_hours': age_hours,
                'status': status,
                'status_color': status_color
            })

        except Exception:
            continue

    # Sort by name
    accounts.sort(key=lambda x: x['name'])

    return accounts

def load_twitter_scrapers():
    """Load Twitter scraper configurations from config file."""
    config_path = PROJECT_ROOT / 'config' / 'scrapers.yaml'

    if not config_path.exists():
        print(f"{Fore.RED}[ERROR] Config file not found: {config_path}{Style.RESET_ALL}")
        return []

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Filter for enabled Twitter scrapers only
        twitter_scrapers = [
            scraper for scraper in config.get('scrapers', [])
            if 'twitter' in scraper['name'].lower() and scraper.get('enabled', True)
        ]

        return twitter_scrapers
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to load config: {e}{Style.RESET_ALL}")
        return []

def start_twitter_scraper(scraper):
    """Start a Twitter scraper with mobile emulation enabled."""
    # Set up mobile emulation environment
    mobile_ua = get_random_mobile_user_agent()
    env_overrides = {
        'ENABLE_MOBILE_EMULATION': 'true',
        'MOBILE_USER_AGENT': mobile_ua
    }

    # Log mobile emulation
    device = 'iPhone' if 'iPhone' in mobile_ua else 'Android' if 'Android' in mobile_ua else 'Mobile'
    print(f"{Fore.CYAN}[MOBILE] {scraper['name']}: Using {device} emulation{Style.RESET_ALL}")

    return start_scraper(scraper, env_overrides)

def display_dashboard():
    """Display Twitter scraper dashboard with real database metrics."""
    global dashboard_update_time

    os.system('cls' if os.name == 'nt' else 'clear')

    # Header
    print("="*90)
    print(" " * 25 + f"{Fore.CYAN}TWITTER SENTIMENT MONITOR{Style.RESET_ALL}")
    print(" " * 20 + f"Real-Time Database Activity Dashboard")
    print("="*90)

    # System status line
    uptime = format_time_since(orchestrator_start_time)
    current_time = datetime.now().strftime("%H:%M:%S")
    print(f"System Uptime: {Fore.GREEN}{uptime}{Style.RESET_ALL} | Time: {current_time} | Scrapers: {len(running_processes)}/7")
    print("-"*90)

    # Get real tweet counts from database
    time_counts = get_tweet_counts_by_time()
    if time_counts:
        print(f"\n{Fore.WHITE}[STATS] TWEET COLLECTION (FROM DATABASE):{Style.RESET_ALL}")
        print("-"*90)

        # Display time-based metrics in a clean format
        metrics = []
        for period, count in time_counts.items():
            color = Fore.GREEN if count > 0 else Fore.YELLOW
            metrics.append(f"{period}: {color}{count:,}{Style.RESET_ALL}")

        # Display in three rows (3 metrics each)
        print("  " + " | ".join(metrics[:3]))
        print("  " + " | ".join(metrics[3:6]))
        print("  " + " | ".join(metrics[6:]))

    # Get per-scraper activity (last 15 minutes)
    scraper_counts = get_tweets_by_scraper(15)
    last_tweet_times = get_last_tweet_times()

    print(f"\n{Fore.WHITE}[ACTIVITY] SCRAPER STATUS (Last 15 min):{Style.RESET_ALL}")
    print("-"*90)

    for name, process in running_processes.items():
        # Check if running
        is_running = process.poll() is None
        status_icon = "[OK]" if is_running else "[X]"
        status_color = Fore.GREEN if is_running else Fore.RED

        # Get tweet count from database
        tweet_count = scraper_counts.get(name, 0)
        count_color = Fore.GREEN if tweet_count > 0 else Fore.YELLOW

        # Get uptime
        uptime = format_time_since(scraper_start_times.get(name))

        # Check for recent errors in logs
        recent_logs = list(scraper_logs.get(name, []))[-3:]  # Last 3 log entries
        has_error = any('error' in log.lower() or 'failed' in log.lower() for log in recent_logs)
        error_indicator = f" {Fore.RED}[ERROR]{Style.RESET_ALL}" if has_error else ""

        # Last tweet age
        minutes_ago = last_tweet_times.get(name)
        if minutes_ago is None:
            last_str = "Last: --"
        elif minutes_ago < 1:
            last_str = "Last: <1m ago"
        elif minutes_ago < 60:
            last_str = f"Last: {int(minutes_ago)}m ago"
        else:
            hours = int(minutes_ago // 60)
            mins = int(minutes_ago % 60)
            last_str = f"Last: {hours}h {mins}m ago"

        print(f"  {status_color}{status_icon}{Style.RESET_ALL} {name:<25} | Tweets: {count_color}{tweet_count:>4}{Style.RESET_ALL} | {last_str:<16} | Up: {uptime}{error_indicator}")

    # Show all cookie accounts status
    cookie_accounts = check_all_cookie_accounts()
    if cookie_accounts:
        print(f"\n{Fore.WHITE}[ACCOUNTS] TWITTER COOKIE STATUS:{Style.RESET_ALL}")
        print("-"*90)

        for account in cookie_accounts:
            # Format last updated time
            if account['age_hours'] < 1:
                age_str = f"{int(account['age_hours'] * 60)}m ago"
            elif account['age_hours'] < 24:
                age_str = f"{account['age_hours']:.1f}h ago"
            else:
                age_str = f"{int(account['age_hours'] / 24)}d ago"

            # Show last update timestamp
            last_update = account['last_updated'].strftime("%m/%d %H:%M")

            print(f"  {account['status_color']}[{account['status']:<6}]{Style.RESET_ALL} {account['name']:<15} | Last: {last_update} ({age_str})")

    # Show recent alerts from database
    alerts = get_recent_alerts()
    if alerts:
        print(f"\n{Fore.WHITE}[!] ALERTS (Last 5 min):{Style.RESET_ALL}")
        print("-"*90)
        for token, alert_level, volume_spike, bot_prob in alerts[:5]:
            if alert_level == 'HIGH':
                print(f"  {Fore.RED}[HIGH] {token}{Style.RESET_ALL}")
            if volume_spike and volume_spike > 2.0:
                print(f"  {Fore.YELLOW}[VOL] {token} ({volume_spike:.1f}x normal){Style.RESET_ALL}")
            if bot_prob and bot_prob > 0.8:
                print(f"  {Fore.MAGENTA}[BOT] {token} ({bot_prob:.0%} probability){Style.RESET_ALL}")

    # Show cookie warning only if critical
    cookie_ok, cookie_msg = check_cookie_status()
    if not cookie_ok:
        print(f"\n{Fore.RED}[CRITICAL] COOKIE STATUS: {cookie_msg}{Style.RESET_ALL}")

    # Show any recent errors from scraper logs
    error_messages = []
    for name, logs in scraper_logs.items():
        for log in list(logs)[-5:]:  # Check last 5 logs per scraper
            if any(word in log.lower() for word in ['error', 'failed', 'exception', 'blocked']):
                error_messages.append((name, log))

    if error_messages:
        print(f"\n{Fore.WHITE}[ERRORS] RECENT ISSUES:{Style.RESET_ALL}")
        print("-"*90)
        for scraper, error in error_messages[-3:]:  # Show last 3 errors
            # Truncate long errors
            error_short = error[:60] + "..." if len(error) > 60 else error
            print(f"  [{scraper[:15]}] {Fore.RED}{error_short}{Style.RESET_ALL}")

    # Database connection status
    db_ok, db_info = check_database_connection()
    if db_ok:
        total_tweets_query = """
            SELECT COUNT(*) FROM twitter_sentiment
        """
        try:
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 54594)),
                dbname=os.getenv('DB_NAME', 'pjx'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', 'postgres')
            )
            with conn.cursor() as cur:
                cur.execute(total_tweets_query)
                total_tweets = cur.fetchone()[0]
            conn.close()

            print(f"\n{Fore.WHITE}[DB] DATABASE:{Style.RESET_ALL} {total_tweets:,} total tweets | {db_info['total_rows']:,} total rows")
        except:
            pass

    dashboard_update_time = datetime.now()
    print("\n" + "="*90)
    print(f"Auto-refresh: 15s | Press Ctrl+C to stop | Next update: {(dashboard_update_time + timedelta(seconds=15)).strftime('%H:%M:%S')}")
    print("="*90)

def main():
    """Main Twitter orchestrator function."""
    global orchestrator_start_time
    orchestrator_start_time = datetime.now()

    print("\n" + "="*80)
    print(" " * 20 + f"{Fore.CYAN}TWITTER ORCHESTRATOR{Style.RESET_ALL}")
    print(" " * 15 + "Mobile Emulation Strategy Active")
    print("="*80)

    # Run preflight checks
    if not run_preflight_checks():
        response = input("\nContinue anyway? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print(f"{Fore.RED}[ABORT] Exiting...{Style.RESET_ALL}")
            return

    # Check cookie status
    cookie_ok, cookie_msg = check_cookie_status()
    if not cookie_ok:
        print(f"{Fore.YELLOW}[WARNING] {cookie_msg}{Style.RESET_ALL}")
        print("Consider running: python monitors/refresh_cookies.py")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            return

    # Load Twitter scrapers
    scrapers = load_twitter_scrapers()

    if not scrapers:
        print(f"{Fore.RED}[ERROR] No Twitter scrapers found or enabled{Style.RESET_ALL}")
        return

    print(f"\nFound {len(scrapers)} Twitter scrapers:")
    for scraper in scrapers:
        interval = scraper.get('interval', 'unknown')
        print(f"  • {scraper['name']:<30} (runs every {interval})")

    print("\n" + "="*80)
    print("Starting Twitter scrapers with mobile emulation...")
    print("="*80 + "\n")

    # Start all Twitter scrapers with staggered timing
    for i, scraper in enumerate(scrapers):
        if i > 0:
            delay = TWITTER_STAGGER_SECONDS
            print(f"[WAIT] Waiting {delay} seconds before starting next scraper...")
            time.sleep(delay)

        start_twitter_scraper(scraper)

    print(f"\n{Fore.GREEN}[SUCCESS] All Twitter scrapers started with mobile emulation{Style.RESET_ALL}")
    print("="*80)

    # Start monitoring in a separate thread
    import threading
    monitor_thread = threading.Thread(
        target=monitor_and_restart_scrapers,
        args=(scrapers,),
        daemon=True
    )
    monitor_thread.start()

    # Wait a moment for scrapers to initialize, then show first dashboard
    time.sleep(3)
    display_dashboard()

    # Main loop - display dashboard with 15-second updates
    try:
        while True:
            time.sleep(15)  # Update every 15 seconds for real-time monitoring
            display_dashboard()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[SHUTDOWN] Stopping all Twitter scrapers...{Style.RESET_ALL}")
        stop_all_scrapers()
        print(f"{Fore.GREEN}[COMPLETE] All scrapers stopped{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
