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
from psycopg2 import pool
from datetime import datetime, timedelta, timezone
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

# Database connection pool (initialized lazily)
_db_pool = None

def get_db_pool():
    """Get or create the database connection pool."""
    global _db_pool
    if _db_pool is None:
        try:
            _db_pool = pool.SimpleConnectionPool(
                1, 5,  # min 1, max 5 connections
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 54594)),
                dbname=os.getenv('DB_NAME', 'pjx'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', 'postgres')
            )
        except Exception as e:
            print(f"{Fore.RED}[DB POOL] Failed to create pool: {e}{Style.RESET_ALL}")
            return None
    return _db_pool

def get_db_connection():
    """Get a connection from the pool."""
    pool = get_db_pool()
    if pool:
        try:
            return pool.getconn()
        except:
            return None
    return None

def return_db_connection(conn):
    """Return a connection to the pool."""
    pool = get_db_pool()
    if pool and conn:
        try:
            pool.putconn(conn)
        except:
            pass

def utc_now():
    """Get current UTC time as naive datetime (for comparing with PostgreSQL timestamps)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

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
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return None

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

        return counts
    except Exception as e:
        return None
    finally:
        return_db_connection(conn)

def get_tweets_by_scraper(minutes=15):
    """Get real tweet counts per scraper from database."""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return {}

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

        return scraper_counts
    except Exception:
        return {}
    finally:
        return_db_connection(conn)

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
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return []

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

        return alerts
    except Exception:
        return []
    finally:
        return_db_connection(conn)

def get_recent_tweets(limit=10):
    """Get the most recent tweets from database for history display."""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return []

        tweets = []
        with conn.cursor() as cur:
            cur.execute("""
                SELECT token, author_username, sentiment_label, sentiment_score,
                       LEFT(tweet_text, 60) as tweet_preview, scraped_at, source
                FROM twitter_sentiment
                ORDER BY scraped_at DESC
                LIMIT %s
            """, (limit,))
            tweets = cur.fetchall()

        return tweets
    except Exception:
        return []
    finally:
        return_db_connection(conn)

def get_velocity_metrics():
    """Get recent velocity metrics (sentiment momentum) from database."""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return []

        metrics = []
        with conn.cursor() as cur:
            # Get tokens with significant sentiment changes in last 15 min
            cur.execute("""
                WITH recent AS (
                    SELECT token,
                           AVG(sentiment_score) as avg_sentiment,
                           COUNT(*) as tweet_count,
                           AVG(CASE WHEN bot_probability IS NOT NULL THEN bot_probability ELSE 0 END) as avg_bot_prob
                    FROM twitter_sentiment
                    WHERE scraped_at >= NOW() - INTERVAL '15 minutes'
                    GROUP BY token
                    HAVING COUNT(*) >= 3
                ),
                older AS (
                    SELECT token,
                           AVG(sentiment_score) as avg_sentiment
                    FROM twitter_sentiment
                    WHERE scraped_at >= NOW() - INTERVAL '60 minutes'
                    AND scraped_at < NOW() - INTERVAL '15 minutes'
                    GROUP BY token
                )
                SELECT r.token,
                       r.avg_sentiment as recent_sentiment,
                       o.avg_sentiment as older_sentiment,
                       r.avg_sentiment - COALESCE(o.avg_sentiment, 0) as sentiment_change,
                       r.tweet_count,
                       r.avg_bot_prob
                FROM recent r
                LEFT JOIN older o ON r.token = o.token
                WHERE ABS(r.avg_sentiment - COALESCE(o.avg_sentiment, 0)) > 0.1
                ORDER BY ABS(r.avg_sentiment - COALESCE(o.avg_sentiment, 0)) DESC
                LIMIT 5
            """)
            metrics = cur.fetchall()

        return metrics
    except Exception:
        return []
    finally:
        return_db_connection(conn)

# Global error tracking with timestamps and status
tracked_errors = deque(maxlen=20)

def track_error(scraper_name, error_msg, is_handled=False, is_resolved=False):
    """Track an error with timestamp and status."""
    tracked_errors.append({
        'timestamp': utc_now(),  # Use UTC for consistency
        'scraper': scraper_name,
        'message': error_msg[:80],  # Truncate long messages
        'handled': is_handled,
        'resolved': is_resolved
    })

def get_tracked_errors(limit=5):
    """Get recent tracked errors for display."""
    return list(tracked_errors)[-limit:]

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

        print(f"  {status_color}{status_icon}{Style.RESET_ALL} {name:<25} | Tweets: {count_color}{tweet_count:>4}{Style.RESET_ALL} | Up: {uptime}{error_indicator}")

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
        track_error("Cookie System", cookie_msg, is_handled=False)

    # Scan scraper logs for errors and track them
    for name, logs in scraper_logs.items():
        for log in list(logs)[-5:]:  # Check last 5 logs per scraper
            log_lower = log.lower()
            if any(word in log_lower for word in ['error', 'failed', 'exception', 'blocked']):
                # Determine if it was handled (contains retry/recovering keywords)
                is_handled = any(word in log_lower for word in ['retry', 'retrying', 'recovered', 'refreshing'])
                # Only track if not already in recent tracked errors (avoid duplicates)
                recent_messages = [e.get('message', '') for e in list(tracked_errors)[-10:]]
                if log[:80] not in recent_messages:
                    track_error(name, log, is_handled=is_handled)

    # Database connection status
    db_ok, db_info = check_database_connection()
    if db_ok:
        conn = None
        try:
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM twitter_sentiment")
                    total_tweets = cur.fetchone()[0]
                print(f"\n{Fore.WHITE}[DB] DATABASE:{Style.RESET_ALL} {total_tweets:,} total tweets | {db_info['total_rows']:,} total rows")
        except:
            pass
        finally:
            return_db_connection(conn)

    # Show velocity metrics (sentiment momentum)
    try:
        velocity_data = get_velocity_metrics()
        if velocity_data:
            print(f"\n{Fore.WHITE}[VELOCITY] SENTIMENT MOMENTUM (15min vs 60min):{Style.RESET_ALL}")
            print("-"*90)
            for token, recent_sent, older_sent, change, count, bot_prob in velocity_data:
                # Direction indicator
                if change > 0.2:
                    direction = f"{Fore.GREEN}▲▲{Style.RESET_ALL}"
                    label = "STRONG UP"
                elif change > 0:
                    direction = f"{Fore.GREEN}▲{Style.RESET_ALL}"
                    label = "UP"
                elif change < -0.2:
                    direction = f"{Fore.RED}▼▼{Style.RESET_ALL}"
                    label = "STRONG DOWN"
                else:
                    direction = f"{Fore.RED}▼{Style.RESET_ALL}"
                    label = "DOWN"

                # Bot warning
                bot_warn = f" {Fore.YELLOW}[BOT?]{Style.RESET_ALL}" if bot_prob and bot_prob > 0.5 else ""

                print(f"  {direction} {token:<8} {label:<12} | Change: {change:+.2f} | Tweets: {count}{bot_warn}")
    except Exception:
        pass

    # Show tracked errors with status
    try:
        errors = get_tracked_errors(5)
        if errors:
            print(f"\n{Fore.WHITE}[ERRORS] RECENT ISSUES:{Style.RESET_ALL}")
            print("-"*90)
            for err in errors:
                try:
                    # Calculate time ago (using UTC)
                    age_seconds = (utc_now() - err['timestamp']).total_seconds()
                    if age_seconds < 0:
                        age_seconds = abs(age_seconds)
                    if age_seconds < 60:
                        age_str = f"{int(age_seconds)}s ago"
                    elif age_seconds < 3600:
                        age_str = f"{int(age_seconds/60)}m ago"
                    else:
                        age_str = f"{int(age_seconds/3600)}h ago"

                    # Status indicator
                    if err.get('resolved'):
                        status = f"{Fore.GREEN}[RESOLVED]{Style.RESET_ALL}"
                    elif err.get('handled'):
                        status = f"{Fore.YELLOW}[HANDLED]{Style.RESET_ALL}"
                    else:
                        status = f"{Fore.RED}[ACTIVE]{Style.RESET_ALL}"

                    scraper_name = str(err.get('scraper', 'unknown'))[:12]
                    message = str(err.get('message', ''))
                    print(f"  {status} {age_str:<8} [{scraper_name:<12}] {message}")
                except Exception:
                    pass
    except Exception:
        pass

    # Show recent tweet history at the bottom
    try:
        recent_tweets = get_recent_tweets(10)
        if recent_tweets:
            print(f"\n{Fore.WHITE}[HISTORY] LAST 10 TWEETS:{Style.RESET_ALL}")
            print("-"*90)
            for row in recent_tweets:
                try:
                    token, author, sentiment_label, sentiment_score, preview, scraped_at, source = row
                    # Format timestamp - use UTC for comparison with PostgreSQL
                    time_str = "?"
                    if scraped_at:
                        try:
                            # Remove timezone info if present for comparison
                            if hasattr(scraped_at, 'tzinfo') and scraped_at.tzinfo is not None:
                                scraped_at = scraped_at.replace(tzinfo=None)
                            age_seconds = (utc_now() - scraped_at).total_seconds()
                            if age_seconds < 0:
                                age_seconds = abs(age_seconds)
                            if age_seconds < 60:
                                time_str = f"{int(age_seconds)}s"
                            elif age_seconds < 3600:
                                time_str = f"{int(age_seconds/60)}m"
                            else:
                                time_str = f"{int(age_seconds/3600)}h"
                        except:
                            time_str = "?"

                    # Sentiment color
                    if sentiment_label == 'POSITIVE':
                        sent_color = Fore.GREEN
                        sent_icon = "+"
                    elif sentiment_label == 'NEGATIVE':
                        sent_color = Fore.RED
                        sent_icon = "-"
                    else:
                        sent_color = Fore.WHITE
                        sent_icon = "~"

                    # Clean up preview text
                    preview_clean = (str(preview) if preview else "")[:50].replace('\n', ' ').replace('\r', '')
                    author_clean = (str(author) if author else "unknown")[:12]
                    token_clean = str(token or "?")[:6]

                    print(f"  {time_str:<4} {sent_color}{sent_icon}{Style.RESET_ALL} {token_clean:<6} @{author_clean:<12} {preview_clean}")
                except Exception:
                    pass
    except Exception:
        pass

    dashboard_update_time = datetime.now()
    print("\n" + "="*90)
    print(f"Auto-refresh: 10s | Press Ctrl+C to stop | Next update: {(dashboard_update_time + timedelta(seconds=10)).strftime('%H:%M:%S')}")
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
    try:
        display_dashboard()
    except Exception as e:
        print(f"{Fore.RED}[DASHBOARD ERROR] {e}{Style.RESET_ALL}")

    # Main loop - display dashboard with 15-second updates
    try:
        while True:
            time.sleep(10)  # Update every 10 seconds for real-time monitoring
            try:
                display_dashboard()
            except Exception as e:
                print(f"{Fore.RED}[DASHBOARD ERROR] {e}{Style.RESET_ALL}")
                import traceback
                traceback.print_exc()
                time.sleep(5)  # Brief pause before retrying
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[SHUTDOWN] Stopping all Twitter scrapers...{Style.RESET_ALL}")
        stop_all_scrapers()
        print(f"{Fore.GREEN}[COMPLETE] All scrapers stopped{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
