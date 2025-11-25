"""
Scraper Orchestrator - Production-Quality Monitoring System
Manages all data collection scrapers with real-time database health monitoring
Easy to expand: Just edit config/scrapers.yaml to add new scrapers!
"""

import argparse
import os
import sys
import time
import subprocess
import yaml
import signal
import psycopg2
import threading
from collections import deque, defaultdict
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import re
import random

# Force UTF-8 console output so Unicode dashboard symbols never crash on Windows
for stream_name in ("stdout", "stderr"):
    stream = getattr(sys, stream_name, None)
    if stream and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# Try to import colorama for Windows-compatible colors
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    COLORS_ENABLED = True
except ImportError:
    # Fallback: no colors
    class Fore:
        GREEN = RED = YELLOW = CYAN = WHITE = MAGENTA = BLUE = ""
    class Style:
        BRIGHT = RESET_ALL = ""
    COLORS_ENABLED = False

# ============================================================================
# MOBILE EMULATION FOR TWITTER SCRAPERS (Chad Scraper Strategy)
# ============================================================================

# Mobile User Agents for Twitter scrapers (November 2025)
MOBILE_USER_AGENTS = [
    # iPhone 15 Pro - iOS 18
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
    # Samsung Galaxy S24 - Android 14
    'Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36',
    # Google Pixel 8 Pro - Android 14
    'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.111 Mobile Safari/537.36',
]

MOBILE_EMULATION_ENABLED = True

def get_random_mobile_user_agent():
    """Get a random mobile user agent"""
    return random.choice(MOBILE_USER_AGENTS)

# Global state
running_processes = {}
restart_attempts = {}  # Track restart attempts per scraper
scraper_start_times = {}  # Track when each scraper started
orchestrator_start_time = None
last_backup_time = None
last_backup_attempt = None
last_summary_time = None
scraper_configs = {}
scraper_modes = {}
scraper_intervals = {}
oneshot_status = defaultdict(dict)
oneshot_schedule = {}
tor_available = False

# Project root (handles launches from other directories)
PROJECT_ROOT = Path(__file__).parent.resolve()

# Load environment variables from .env so child scrapers inherit required keys
DOTENV_PATH = PROJECT_ROOT / '.env'
if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=DOTENV_PATH, override=False)
else:
    load_dotenv(override=False)  # Fallback to default search locations

# Activity logging
scraper_logs = defaultdict(lambda: deque(maxlen=10))  # Last 10 log lines per scraper
scraper_activity = defaultdict(dict)  # Track key metrics per scraper

# Configuration
MAX_RESTART_ATTEMPTS = 3
BACKUP_INTERVAL_HOURS = 24
BACKUP_RETRY_INTERVAL_MINUTES = 30
SUMMARY_INTERVAL_MINUTES = 15
MONITOR_INTERVAL_SECONDS = 30
MAX_LOG_LINES_PER_SCRAPER = 10
TWITTER_ACTIVITY_LOOKBACK_MINUTES = 20
COOKIE_WARNING_MINUTES = 120
COOKIE_STALE_MINUTES = 360
DEFAULT_STAGGER_SECONDS = 2
TWITTER_STAGGER_SECONDS = 5
STREAMING_STAGGER_SECONDS = 1
PROXY_ALL_SCRAPERS = os.getenv('PROXY_ALL_SCRAPERS', 'false').lower() == 'true'

TWITTER_SOURCE_MAP = {
    'Twitter Meme Coins': 'memecoins',
    'Twitter Large Caps': 'largecaps',
    'Twitter DeFi': 'defi',
    'Twitter Layer 1s': 'layer1s',
    'Twitter Layer 2s': 'layer2s',
    'Twitter AI/ML': 'ai',
    'Twitter Emerging': 'emerging',
    'Twitter Whale Tracker': 'whale_tracker'
}

SCRAPER_TABLE_KEYWORDS = {
    'twitter': 'twitter_sentiment',
    'binance ohlcv': 'crypto_ohlcv',
    'order book': 'order_book_depth',
    'funding': 'funding_rates',
    'fear & greed': 'fear_greed_index',
    'liquidation': 'liquidations',
    'open interest': 'open_interest',
    'sec edgar': 'sec_filings',
    'senate': 'congressional_trades',
    'house': 'congressional_trades',
    'stablecoin': 'stablecoin_metrics',
    'dex liquidity': 'dex_liquidity',
    'exchange flows': 'exchange_flows',
    'options volatility': 'options_volatility',
    'options vol': 'options_volatility',
    'tvl': 'defi_tvl_chains',
    'bridge flow': 'bridge_flows',
    'bridge flows': 'bridge_flows',
    'newsapi': 'news_articles',
    'rss': 'news_articles'
}

TABLE_DEFAULT_THRESHOLD_MINUTES = {
    'twitter_sentiment': 15,
    'crypto_ohlcv': 10,
    'news_articles': 30,
    'order_book_depth': 5,
    'funding_rates': 90,
    'fear_greed_index': 1500,
    'liquidations': 60,
    'open_interest': 90,
    'congressional_trades': 10080,
    'sec_filings': 1440,
    'stablecoin_metrics': 60,
    'dex_liquidity': 60,
    'exchange_flows': 60,
    'options_volatility': 90,
    'defi_tvl_chains': 90,
    'bridge_flows': 90
}

TABLE_MIN_THRESHOLD_OVERRIDES = {
    # Binance order book constantly streams, but inserts can be bursty.
    'order_book_depth': 12
}

STALENESS_INTERVAL_MULTIPLIER = 3
MIN_DYNAMIC_THRESHOLD_MINUTES = 5


def cleanup_cookie_locks(max_age_seconds=300):
    """Remove stale cookie refresh lock files so auto-refresh can run again."""
    cookies_dir = PROJECT_ROOT / "cookies"
    if not cookies_dir.exists():
        return

    removed = []
    now = datetime.now()

    for lock_file in cookies_dir.glob("*.lock"):
        try:
            age_seconds = now.timestamp() - lock_file.stat().st_mtime
        except OSError:
            continue

        if age_seconds < 0 or age_seconds <= max_age_seconds:
            continue

        try:
            lock_file.unlink()
            removed.append(lock_file.name)
        except OSError:
            continue

    if removed:
        print(f"[CHECK] Cleared stale cookie locks: {', '.join(removed)}")


def get_cookie_file_stats():
    """Return pool cookie freshness info, filtering out fallback/backup files."""
    cookies_dir = PROJECT_ROOT / "cookies"
    if not cookies_dir.exists():
        return []

    stats = []
    now = datetime.now()

    prefix = 'cookies_account'
    suffix = '.json'

    for path in cookies_dir.glob(f'{prefix}*.json'):
        name = path.name
        if not (name.startswith(prefix) and name.endswith(suffix)):
            continue

        number_part = name[len(prefix):-len(suffix)]
        if not number_part.isdigit():
            continue

        account_num = int(number_part)
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue

        age_minutes = max((now - mtime).total_seconds() / 60, 0)
        stats.append({
            'name': name,
            'account_num': account_num,
            'updated_at': mtime,
            'age_minutes': age_minutes,
            'is_primary': False,
        })

    stats.sort(key=lambda entry: entry['account_num'])
    return stats


def humanize_seconds(seconds):
    """Convert seconds into a compact human-readable string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m" + (f" {seconds}s" if seconds and minutes < 5 else "")
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h" + (f" {minutes}m" if minutes else "")


def format_time_since(timestamp):
    """Return 'Xm ago' style strings for past timestamps."""
    if not timestamp:
        return "never"
    delta = datetime.now() - timestamp
    total_seconds = max(int(delta.total_seconds()), 0)
    if total_seconds == 0:
        return "just now"
    return f"{humanize_seconds(total_seconds)} ago"


def format_time_until(timestamp):
    """Return 'in Xm' style string for future timestamps."""
    if not timestamp:
        return "n/a"
    delta = timestamp - datetime.now()
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "due now"
    return f"in {humanize_seconds(total_seconds)}"


def parse_interval_seconds(interval_str):
    """Convert config interval strings like '5 minutes' into seconds."""
    if not interval_str:
        return 5 * 60

    text = interval_str.strip().lower()
    if text in {'daily', 'once per day', '1 day', 'day'}:
        return 24 * 60 * 60
    if text in {'hourly', '1 hour', 'hour'}:
        return 60 * 60

    match = re.match(r'(\d+)\s*(second|minute|hour|day)s?', text)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if unit.startswith('second'):
            return max(value, 1)
        if unit.startswith('minute'):
            return max(value, 1) * 60
        if unit.startswith('hour'):
            return max(value, 1) * 3600
        if unit.startswith('day'):
            return max(value, 1) * 86400

    return 5 * 60


def map_scraper_to_table(scraper_name):
    """Return the table that should receive data for the given scraper name."""
    if not scraper_name:
        return None
    lower_name = scraper_name.lower()
    for keyword, table in SCRAPER_TABLE_KEYWORDS.items():
        if keyword in lower_name:
            return table
    return None


def get_start_stagger_seconds(scraper):
    """Return a safe-but-fast stagger delay for starting scrapers."""
    if not scraper:
        return DEFAULT_STAGGER_SECONDS

    # Explicit override wins if present in config
    override = scraper.get('stagger_seconds')
    if isinstance(override, (int, float)) and override >= 0:
        return float(override)

    name = scraper.get('name', '').lower()
    if 'twitter' in name:
        # Leave spacing to avoid simultaneous login/search bursts on the pool
        return max(DEFAULT_STAGGER_SECONDS, TWITTER_STAGGER_SECONDS)

    if any(key in name for key in ['order book', 'liquidation', 'ohlcv', 'open interest']):
        # Streaming/public APIs tolerate tight spacing
        return STREAMING_STAGGER_SECONDS

    return DEFAULT_STAGGER_SECONDS


def build_table_thresholds(scrapers):
    """Derive per-table freshness thresholds from scraper intervals."""
    table_thresholds = {}
    for scraper in scrapers:
        if not scraper.get('enabled'):
            continue
        table = map_scraper_to_table(scraper.get('name'))
        if not table:
            continue

        interval_seconds = parse_interval_seconds(scraper.get('interval'))
        interval_minutes = max(interval_seconds / 60, 1 / 60)
        threshold_minutes = max(
            interval_minutes * STALENESS_INTERVAL_MULTIPLIER,
            MIN_DYNAMIC_THRESHOLD_MINUTES
        )
        if table in TABLE_MIN_THRESHOLD_OVERRIDES:
            threshold_minutes = max(threshold_minutes, TABLE_MIN_THRESHOLD_OVERRIDES[table])

        existing = table_thresholds.get(table)
        if existing is None or threshold_minutes > existing:
            table_thresholds[table] = threshold_minutes

    return table_thresholds


# ============================================================================
# DATABASE MONITORING
# ============================================================================

class DatabaseMonitor:
    """Monitors database health and data collection rates."""

    def __init__(self):
        self.dsn = None
        self.connection_ok = False
        self.last_row_counts = {}
        self.tables_to_monitor = {
            'twitter_sentiment': 'scraped_at',
            'crypto_ohlcv': 'scraped_at',
            'news_articles': 'scraped_at',
            'congressional_trades': 'scraped_at',
            'order_book_depth': 'timestamp',
            'funding_rates': 'scraped_at',
            'fear_greed_index': 'scraped_at',
            'liquidations': 'timestamp',
            'open_interest': 'scraped_at',
            'sec_filings': 'scraped_at',
            'stablecoin_metrics': 'scraped_at',
            'dex_liquidity': 'scraped_at',
            'exchange_flows': 'scraped_at',
            'options_volatility': 'scraped_at',
            'defi_tvl_chains': 'scraped_at',
            'bridge_flows': 'scraped_at'
        }
        self.base_thresholds = dict(TABLE_DEFAULT_THRESHOLD_MINUTES)
        self.table_thresholds = dict(self.base_thresholds)
        self.heartbeat_map = {
            'sec_filings': 'SEC EDGAR Reader',
            'exchange_flows': 'Exchange Flows'
        }

    def _open_connection(self):
        if not self.dsn:
            return None
        return psycopg2.connect(**self.dsn, connect_timeout=5)

    def connect(self):
        """Establish database connection (tested, short-lived)."""
        try:
            load_dotenv(override=True)
            self.dsn = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': os.getenv('DB_PORT', '54594'),
                'database': os.getenv('DB_NAME', 'pjx'),
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', '')
            }

            with closing(self._open_connection()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('SELECT 1')

            self.connection_ok = True
            return True
        except Exception as e:
            self.connection_ok = False
            print(f"{Fore.RED}[ERROR] Database connection failed: {e}{Style.RESET_ALL}")
            return False

    def get_table_stats(self):
        """Get row counts and last update times for all tables."""
        if not self.dsn:
            return None

        stats = {}

        try:
            with closing(self._open_connection()) as conn:
                with conn.cursor() as cursor:
                    heartbeat_cache = self._fetch_heartbeats(cursor)
                    for table, time_col in self.tables_to_monitor.items():
                        try:
                            cursor.execute(f"SELECT COUNT(*) FROM {table}")
                            count = cursor.fetchone()[0]

                            cursor.execute(f"SELECT MAX({time_col}) FROM {table}")
                            last_update = cursor.fetchone()[0]

                            heartbeat_name = self.heartbeat_map.get(table)
                            if heartbeat_name:
                                hb_ts = heartbeat_cache.get(heartbeat_name)
                                if hb_ts and (not last_update or hb_ts > last_update):
                                    last_update = hb_ts

                            change = count - self.last_row_counts.get(table, count)
                            self.last_row_counts[table] = count

                            stats[table] = {
                                'count': count,
                                'last_update': last_update,
                                'change': change
                            }

                        except Exception as e:
                            stats[table] = {'error': str(e)}

        except Exception as e:
            print(f"{Fore.RED}[ERROR] Failed to get table stats: {e}{Style.RESET_ALL}")
            return None

        return stats

    def _fetch_heartbeats(self, cursor):
        """Load all scraper heartbeat timestamps."""
        try:
            cursor.execute("SELECT scraper_name, last_run FROM scraper_heartbeats")
            return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception:
            return {}

    def get_stablecoin_snapshot(self):
        """Return latest stablecoin metrics for dashboard display."""
        if not self.dsn:
            return None

        query = """
            SELECT symbol,
                   market_cap,
                   total_volume_24h,
                   velocity_ratio,
                   supply_change_pct_24h,
                   price_deviation_pct,
                   timestamp
            FROM (
                SELECT symbol,
                       market_cap,
                       total_volume_24h,
                       velocity_ratio,
                       supply_change_pct_24h,
                       price_deviation_pct,
                       timestamp,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) AS rn
                FROM stablecoin_metrics
            ) latest
            WHERE rn = 1
        """

        try:
            with closing(self._open_connection()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
        except Exception:
            return None

        if not rows:
            return None

        total_mcap = 0
        total_volume = 0
        velocity_values = []
        supply_alerts = []
        depeg_alerts = []

        for symbol, mcap, vol, velocity, supply_pct, dev_pct, _ in rows:
            if mcap:
                total_mcap += float(mcap)
            if vol:
                total_volume += float(vol)
            if velocity:
                velocity_values.append(float(velocity))

            if supply_pct is not None and abs(supply_pct) >= 1:
                supply_alerts.append((symbol, float(supply_pct)))

            if dev_pct is not None and abs(dev_pct) >= 0.5:
                depeg_alerts.append((symbol, float(dev_pct)))

        avg_velocity = sum(velocity_values) / len(velocity_values) if velocity_values else 0
        supply_alerts.sort(key=lambda x: abs(x[1]), reverse=True)
        depeg_alerts.sort(key=lambda x: abs(x[1]), reverse=True)

        return {
            'total_market_cap': total_mcap,
            'total_volume': total_volume,
            'avg_velocity': avg_velocity,
            'supply_alerts': supply_alerts[:3],
            'depeg_alerts': depeg_alerts[:3]
        }

    def get_dex_snapshot(self, lookback_minutes=120):
        """Return aggregated DEX liquidity stats."""
        if not self.dsn:
            return None

        query = """
            SELECT token,
                   SUM(liquidity_usd) AS liquidity,
                   SUM(volume_24h) AS volume,
                   AVG(volume_to_liquidity_ratio) AS ratio,
                   MAX(scraped_at) AS last_time
            FROM dex_liquidity
            WHERE scraped_at >= NOW() - INTERVAL %s
            GROUP BY token
            ORDER BY volume DESC
            LIMIT 5
        """

        interval = f"{lookback_minutes} minutes"
        try:
            with closing(self._open_connection()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (interval,))
                    rows = cursor.fetchall()
        except Exception:
            return None

        if not rows:
            return None

        data = []
        for token, liquidity, volume, ratio, last_time in rows:
            data.append({
                'token': token,
                'liquidity': float(liquidity or 0),
                'volume': float(volume or 0),
                'ratio': float(ratio or 0),
                'last_time': last_time
            })

        return {
            'top_tokens': data,
            'lookback_minutes': lookback_minutes
        }

    def get_exchange_flow_snapshot(self, lookback_hours=6):
        """Return recent exchange flows."""
        if not self.dsn:
            return None

        query = """
            SELECT token, flow_type, usd_value, exchange, is_smart_money, signal_strength, timestamp
            FROM exchange_flows
            WHERE timestamp >= NOW() - INTERVAL %s
            ORDER BY timestamp DESC
            LIMIT 5
        """

        interval = f"{lookback_hours} hours"
        try:
            with closing(self._open_connection()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (interval,))
                    rows = cursor.fetchall()
        except Exception:
            return None

        if not rows:
            return None

        flows = []
        for token, flow_type, usd_value, exchange, is_smart, strength, ts in rows:
            flows.append({
                'token': token,
                'flow_type': flow_type,
                'usd_value': float(usd_value or 0),
                'exchange': exchange,
                'is_smart': bool(is_smart),
                'strength': float(strength or 0),
                'timestamp': ts
            })

        return {
            'recent_flows': flows,
            'lookback_hours': lookback_hours
        }

    def get_twitter_collection_stats(self):
        """Return Twitter collection statistics for various time periods."""
        if not self.dsn:
            return None

        stats = {}

        try:
            with closing(self._open_connection()) as conn:
                with conn.cursor() as cursor:
                    # Last 15 minutes
                    cursor.execute("""
                        SELECT COUNT(*) FROM twitter_sentiment
                        WHERE scraped_at >= NOW() - INTERVAL '15 minutes'
                    """)
                    stats['last_15min'] = cursor.fetchone()[0]

                    # Last hour
                    cursor.execute("""
                        SELECT COUNT(*) FROM twitter_sentiment
                        WHERE scraped_at >= NOW() - INTERVAL '1 hour'
                    """)
                    last_hour_count = cursor.fetchone()[0]
                    if last_hour_count > 0:
                        stats['last_hour'] = last_hour_count
                        stats['last_hour_avg'] = last_hour_count / 4.0

                    # Get uptime to determine what breakdowns to show
                    if not orchestrator_start_time:
                        return stats

                    uptime_hours = (datetime.now() - orchestrator_start_time).total_seconds() / 3600

                    # Hourly breakdown (show if uptime > 1 hour, up to last 6 hours)
                    if uptime_hours >= 1:
                        max_hours = min(int(uptime_hours) + 1, 6)
                        hourly_breakdown = []

                        for hour in range(max_hours):
                            cursor.execute("""
                                SELECT COUNT(*) FROM twitter_sentiment
                                WHERE scraped_at >= NOW() - INTERVAL %s
                                  AND scraped_at < NOW() - INTERVAL %s
                            """, (f'{hour+1} hours', f'{hour} hours'))

                            count = cursor.fetchone()[0]
                            if hour == 0:
                                label = "Current hour"
                            elif hour == 1:
                                label = "1 hour ago"
                            else:
                                label = f"{hour} hours ago"

                            hourly_breakdown.append({'label': label, 'count': count})

                        if hourly_breakdown:
                            stats['hourly_breakdown'] = hourly_breakdown

                    # Daily breakdown (show if uptime > 24 hours, up to last 7 days)
                    if uptime_hours >= 24:
                        max_days = min(int(uptime_hours / 24) + 1, 7)
                        daily_breakdown = []

                        for day in range(max_days):
                            cursor.execute("""
                                SELECT COUNT(*) FROM twitter_sentiment
                                WHERE scraped_at >= NOW() - INTERVAL %s
                                  AND scraped_at < NOW() - INTERVAL %s
                            """, (f'{day+1} days', f'{day} days'))

                            count = cursor.fetchone()[0]
                            if day == 0:
                                label = "Today"
                            elif day == 1:
                                label = "Yesterday"
                            else:
                                label = f"{day} days ago"

                            daily_breakdown.append({'label': label, 'count': count})

                        if daily_breakdown:
                            stats['daily_breakdown'] = daily_breakdown

        except Exception:
            return None

        return stats if stats else None

    def get_recent_twitter_activity(self, minutes=TWITTER_ACTIVITY_LOOKBACK_MINUTES):
        """Aggregate recent twitter_sentiment inserts per scraper source."""
        if not self.dsn:
            return {}

        since = datetime.now() - timedelta(minutes=minutes)
        activity = {}

        try:
            with closing(self._open_connection()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT source, token, COUNT(*) as cnt, MAX(scraped_at) as last_time
                        FROM twitter_sentiment
                        WHERE scraped_at >= %s
                        GROUP BY source, token
                        ORDER BY last_time DESC
                    """, (since,))

                    for source, token, count, last_time in cursor.fetchall():
                        info = activity.setdefault(source, {
                            'tokens': [],
                            'total_saved': 0,
                            'last_saved': None,
                            'lookback_minutes': minutes
                        })
                        info['tokens'].append({
                            'token': token,
                            'count': count,
                            'time': last_time
                        })
                        info['total_saved'] += count

                        if last_time and (info['last_saved'] is None or last_time > info['last_saved']):
                            info['last_saved'] = last_time

            for info in activity.values():
                info['tokens'] = info['tokens'][:5]

        except Exception as e:
            print(f"{Fore.YELLOW}[WARNING] Failed to load twitter activity: {e}{Style.RESET_ALL}")
            return {}

        return activity

    def check_data_freshness(self, stats):
        """Check if data is stale (scraper running but not inserting)."""
        if not stats:
            return []

        warnings = []
        now = datetime.now()

        for table, data in stats.items():
            if 'error' in data or not data.get('last_update'):
                continue

            age = (now - data['last_update'].replace(tzinfo=None)).total_seconds() / 60
            threshold = self.table_thresholds.get(table, TABLE_DEFAULT_THRESHOLD_MINUTES.get(table, 60))

            if age > threshold:
                warnings.append((table, age))

        return warnings

    def close(self):
        """Marker for compatibility (connections are short-lived)."""
        self.dsn = None

    def set_table_thresholds(self, custom_thresholds=None):
        """Update freshness thresholds using defaults plus any custom overrides."""
        merged = dict(self.base_thresholds)
        if custom_thresholds:
            for table, minutes in custom_thresholds.items():
                merged[table] = max(merged.get(table, 0), minutes)
        self.table_thresholds = merged


# ============================================================================
# REAL-TIME SCRAPER OUTPUT MONITORING
# ============================================================================


def parse_scraper_output(line, scraper_name):
    """Parse scraper output and extract key information

    Extracts:
    - Tweet counts (e.g., "Found 25 tweets")
    - Token mentions (e.g., "Processing BTC", "$PEPE")
    - Cookie refresh attempts/success
    - Errors and warnings
    - Sentiment scores
    """
    line = line.strip()
    if not line:
        return None

    info = {'raw': line, 'type': 'info'}
    lower_line = line.lower()
    now = datetime.now()

    activity = scraper_activity[scraper_name]
    activity['last_log_time'] = now
    if 'token_history' not in activity:
        activity['token_history'] = deque(maxlen=12)
    token_history = activity['token_history']

    def _append_token_event(token, count=None):
        """Track recent tokens scanned with optional tweet counts."""
        entry = {'token': token, 'count': count, 'time': now}
        if token_history and token_history[-1]['token'] == token and token_history[-1].get('count') is None:
            token_history[-1].update(entry)
        else:
            token_history.append(entry)
        activity['last_token'] = token
        activity['last_token_time'] = now

    # Cookie refresh detection
    if 'auto-refresh' in lower_line or 'cookie refresh' in lower_line:
        info['type'] = 'cookie_refresh'
        if 'lock acquired' in lower_line:
            info['message'] = 'Starting cookie refresh...'
            activity['cookie_status'] = 'refreshing'
        elif 'lock released' in lower_line:
            info['message'] = 'Cookie lock released'
        elif 'successfully' in lower_line or '✓' in line:
            info['message'] = 'Cookie refresh successful ✓'
            activity['cookie_status'] = 'ok'
            activity['last_cookie_refresh'] = now
        elif 'failed' in lower_line or '✗' in line:
            info['message'] = 'Cookie refresh failed ✗'
            activity['cookie_status'] = 'failed'
            activity['last_cookie_failure'] = now
        elif 'waiting' in lower_line:
            info['message'] = 'Waiting for another refresh slot'
    # Authentication failures
    elif 'auth error' in lower_line or 'authentication failed' in lower_line:
        info['type'] = 'error'
        info['message'] = 'Authentication error - forcing cookie refresh'
        activity['cookie_status'] = 'failed'
        activity['last_auth_error'] = now

    # Tweet count detection - "[OK] Collected X quality tweets for TOKEN"
    elif 'collected' in lower_line and 'tweets for' in lower_line:
        match = re.search(r'Collected (\d+) (?:quality )?tweets for ([A-Z]{2,10})\b', line)
        if match:
            count = int(match.group(1))
            token = match.group(2)
            info['type'] = 'tweet_count'
            info['message'] = f'✓ ${token}: {count} tweets'
            activity['last_tweet_count'] = count
            activity['total_tweets'] = activity.get('total_tweets', 0) + count
            _append_token_event(token, count)

    # Generic tweet count detection (fallback)
    elif 'found' in lower_line and 'tweet' in lower_line:
        match = re.search(r'Found (\d+) tweet', line, re.IGNORECASE)
        if match:
            count = int(match.group(1))
            info['type'] = 'tweet_count'
            info['message'] = f'Found {count} tweets'
            activity['last_tweet_count'] = count
            activity['total_tweets'] = activity.get('total_tweets', 0) + count

    # Token processing detection - "Searching: $TOKEN"
    elif 'searching:' in line and '$' in line:
        match = re.search(r'\$([A-Z]{2,10})\b', line)
        if match:
            token = match.group(1)
            info['type'] = 'token'
            info['message'] = f'Scanning ${token}'
            activity['current_token'] = token
            activity['tokens_in_cycle'] = activity.get('tokens_in_cycle', 0) + 1
            _append_token_event(token)

    # Generic token processing detection (fallback)
    elif any(indicator.lower() in lower_line for indicator in ['processing', 'scraping', 'analyzing']):
        tokens = re.findall(r'\$?([A-Z]{2,10})\b', line)
        if tokens and len(tokens[0]) <= 6:
            token = tokens[0]
            info['type'] = 'token'
            info['message'] = f'Processing ${token}'
            activity['current_token'] = token
            activity['tokens_in_cycle'] = activity.get('tokens_in_cycle', 0) + 1
            _append_token_event(token)

    # Cycle summary table rows: "PEPE | 23 | ..."
    elif '|' in line:
        parts = [p.strip() for p in line.split('|')]
        if parts and len(parts) >= 2:
            token = parts[0]
            if token.upper() == token and token.upper() != 'TOKEN' and 2 <= len(token) <= 10 and re.match(r'^[A-Z0-9]+$', token):
                try:
                    count = int(re.sub(r'[^0-9]', '', parts[1]))
                except ValueError:
                    count = None
                if count is not None:
                    info['type'] = 'tweet_count'
                    info['message'] = f'Cycle stats ${token}: {count} tweets'
                    _append_token_event(token, count)

    # Volume spike detection - "TOKEN: 2.5x normal volume (45 tweets) - BUY_SIGNAL"
    elif 'x normal volume' in lower_line or ('tweets)' in line and 'signal' in lower_line):
        match = re.search(r'([A-Z]{2,10}):\s+([\d.]+)x\s+normal volume\s+\((\d+)\s+tweets\)', line)
        if match:
            token = match.group(1)
            multiplier = match.group(2)
            count = match.group(3)
            info['type'] = 'alert'
            info['message'] = f'🚨 ${token} VOLUME SPIKE: {multiplier}x ({count} tweets)'
        else:
            info['type'] = 'alert'
            info['message'] = line[:100]

    # Generic sentiment/volume spike detection (fallback)
    elif '🚀' in line or 'momentum' in lower_line or 'spike' in lower_line:
        info['type'] = 'alert'
        info['message'] = line[:80]

    # Insert detection (database) - "[OK] Saved X new tweets"
    elif 'saved' in lower_line and 'tweet' in lower_line:
        match = re.search(r'Saved (\d+) (?:new )?tweets', line, re.IGNORECASE)
        if match:
            count = int(match.group(1))
            info['type'] = 'database'
            info['message'] = f'💾 Saved {count} to database'
            activity['total_saved'] = activity.get('total_saved', 0) + count
            activity['last_saved_count'] = count
            activity['last_db_save'] = now

    # Generic insert detection (fallback)
    elif 'inserted' in lower_line:
        match = re.search(r'(\d+)\s+(?:tweets?|records?)', line)
        if match:
            count = int(match.group(1))
            info['type'] = 'database'
            info['message'] = f'Saved {count} tweets to DB'
            activity['total_saved'] = activity.get('total_saved', 0) + count
            activity['last_saved_count'] = count
            activity['last_db_save'] = now

    # Error detection
    elif 'error' in lower_line:
        info['type'] = 'error'
        info['message'] = line[:150]
        activity['last_error'] = {'message': info['message'], 'time': now}

    # Warning detection
    elif 'warning' in lower_line or 'warn' in lower_line:
        info['type'] = 'warning'
        info['message'] = line[:150]

    # Auth errors (specific detection)
    elif any(keyword in lower_line for keyword in ['401', '403', 'unauthorized', 'forbidden']):
        info['type'] = 'error'
        info['message'] = f"🔒 {line[:120]}"
        activity['cookie_status'] = 'failed'
        activity['last_auth_error'] = now

    # Rate limit detection
    elif 'rate limit' in lower_line or 'toomanyrequests' in lower_line:
        info['type'] = 'rate_limit'
        info['message'] = 'Rate limit hit, waiting...'
        activity['rate_limited'] = True
        wait_match = re.search(r'waiting (\d+)', lower_line)
        if wait_match:
            seconds = int(wait_match.group(1))
            activity['rate_limit_reset'] = now + timedelta(seconds=seconds)

    # Cycle start detection
    elif 'starting collection cycle' in lower_line:
        info['type'] = 'info'
        if re.search(r'\[(\d{2}:\d{2}:\d{2})\]', line):
            info['message'] = '▶ Starting new collection cycle'
        else:
            info['message'] = line[:80]
        activity['last_cycle_start'] = now
        activity['cycle_status'] = 'running'
        activity['tokens_in_cycle'] = 0

    # Cycle completion / sleep notices
    elif 'cycle completed' in lower_line:
        info['type'] = 'info'
        info['message'] = 'Cycle completed'
        activity['last_cycle_completed'] = now
        activity['cycle_status'] = 'idle'
        activity['cycles_completed'] = activity.get('cycles_completed', 0) + 1
        if activity.get('last_cycle_start'):
            activity['last_cycle_duration'] = (now - activity['last_cycle_start']).total_seconds()
    elif 'cycle summary' in lower_line:
        info['type'] = 'info'
        info['message'] = 'Cycle summary ready'
        activity['last_cycle_summary'] = now
    elif 'no tweets collected this cycle' in lower_line:
        info['type'] = 'warning'
        info['message'] = 'Cycle produced zero tweets'
        activity['last_cycle_empty'] = now
    elif 'next cycle' in lower_line or 'sleeping' in lower_line or 'waiting' in lower_line:
        info['type'] = 'sleep'
        match = re.search(r'(\d+)', line)
        if match:
            seconds = int(match.group(1))
            info['message'] = f'⏸ Sleeping {seconds}s'
            activity['next_cycle_eta'] = now + timedelta(seconds=seconds)
        else:
            info['message'] = line[:80]

    # Catch-all for other important messages
    elif any(keyword in lower_line for keyword in ['starting', 'tracking', 'collected', ' ok', 'searching']):
        info['type'] = 'info'
        info['message'] = line[:100]

    activity['last_status_message'] = info.get('message', info['raw'])
    return info

def monitor_scraper_output(stream, scraper_name, stream_type):
    """Monitor a single IO stream and log activity without blocking others."""
    try:
        for raw_line in iter(stream.readline, b''):
            if not raw_line:
                break

            decoded = raw_line.decode('utf-8', errors='ignore')
            timestamp = datetime.now().strftime('%H:%M:%S')

            if stream_type == 'stdout':
                parsed = parse_scraper_output(decoded, scraper_name)
                if parsed:
                    scraper_logs[scraper_name].append({
                        'time': timestamp,
                        'type': parsed['type'],
                        'message': parsed.get('message', parsed['raw'])
                    })
            else:
                message = decoded.strip()
                if message:
                    scraper_logs[scraper_name].append({
                        'time': timestamp,
                        'type': 'error',
                        'message': message[:200]
                    })
    except Exception:
        pass


def start_output_monitor_thread(process, scraper_name):
    """Start background threads to monitor stdout and stderr independently."""
    threads = []

    if process.stdout:
        t_out = threading.Thread(
            target=monitor_scraper_output,
            args=(process.stdout, scraper_name, 'stdout'),
            daemon=True
        )
        t_out.start()
        threads.append(t_out)

    if process.stderr:
        t_err = threading.Thread(
            target=monitor_scraper_output,
            args=(process.stderr, scraper_name, 'stderr'),
            daemon=True
        )
        t_err.start()
        threads.append(t_err)

    return threads


# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

def check_and_start_tor():
    """Check if Tor is running and start it if not."""
    print(f"[CHECK] Tor service ... ", end="")

    try:
        # Check if Tor is running (use UTF-8 encoding for WSL output)
        result = subprocess.run(
            ['wsl', 'sudo', 'service', 'tor', 'status'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=5
        )

        if result.stdout and 'is running' in result.stdout.lower():
            print(f"{Fore.GREEN}✓ Running{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.YELLOW}○ Not running, starting...{Style.RESET_ALL}", end=" ")

            # Start Tor
            start_result = subprocess.run(
                ['wsl', 'sudo', 'service', 'tor', 'start'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=10
            )

            if start_result.returncode == 0:
                print(f"{Fore.GREEN}✓ Started{Style.RESET_ALL}")
                time.sleep(2)  # Give Tor a moment to initialize
                return True
            else:
                print(f"{Fore.RED}✗ Failed to start{Style.RESET_ALL}")
                return False

    except subprocess.TimeoutExpired:
        print(f"{Fore.RED}✗ Timeout{Style.RESET_ALL}")
        return False
    except Exception as e:
        print(f"{Fore.RED}✗ Error: {e}{Style.RESET_ALL}")
        return False


def run_preflight_checks():
    """Run system checks before starting scrapers."""
    global tor_available
    print(f"\n{'='*80}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'PRE-FLIGHT SYSTEM CHECKS':^80}{Style.RESET_ALL}")
    print(f"{'='*80}\n")

    checks_passed = True
    db_monitor = None

    # Make sure stale cookie refresh locks don't block auto-refresh
    cleanup_cookie_locks()

    # Check and start Tor if needed
    tor_available = check_and_start_tor()
    if not tor_available:
        print(f"{Fore.YELLOW}[WARNING] Tor not available - IP rotation disabled{Style.RESET_ALL}")
        print(f"         To enable: wsl sudo service tor start")

    # 1. Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"[CHECK] Python version: {py_version} ... ", end="")
    if sys.version_info >= (3, 9):
        print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}✗ (Require 3.9+){Style.RESET_ALL}")
        checks_passed = False

    # 2. Required directories
    required_dirs = ['logs', 'outputs', 'backups', 'config']
    for dir_path in required_dirs:
        print(f"[CHECK] Directory '{dir_path}' ... ", end="")
        path = PROJECT_ROOT / dir_path
        if path.exists():
            print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}Creating...{Style.RESET_ALL}", end=" ")
            path.mkdir(parents=True, exist_ok=True)
            print(f"{Fore.GREEN}✓{Style.RESET_ALL}")

    # 3. Config file
    print(f"[CHECK] Config file (config/scrapers.yaml) ... ", end="")
    if (PROJECT_ROOT / "config/scrapers.yaml").exists():
        print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}✗ Missing{Style.RESET_ALL}")
        checks_passed = False

    # 4. Database connectivity
    print(f"[CHECK] Database connection ... ", end="")
    db_monitor = DatabaseMonitor()
    if db_monitor.connect():
        print(f"{Fore.GREEN}✓ Connected{Style.RESET_ALL}")

        # Check table existence
        stats = db_monitor.get_table_stats()
        if stats:
            print(f"\n[INFO] Database Status:")
            total_rows = sum(s['count'] for s in stats.values() if 'count' in s)
            tables_found = len([s for s in stats.values() if 'count' in s])
            print(f"       - {tables_found} tables found")
            print(f"       - {total_rows:,} total rows")

            # Show top 3 tables by size
            top_tables = sorted(
                [(k, v['count']) for k, v in stats.items() if 'count' in v],
                key=lambda x: x[1],
                reverse=True
            )[:3]

            if top_tables:
                print(f"       - Largest tables:")
                for table, count in top_tables:
                    print(f"         * {table}: {count:,} rows")
    else:
        print(f"{Fore.RED}✗ Failed{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[WARNING] Scrapers will fail without database!{Style.RESET_ALL}")
        checks_passed = False
        db_monitor = None

    # 5. Environment variables
    print(f"\n[CHECK] Environment variables ... ", end="")
    load_dotenv(override=True)

    required_vars = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER']
    missing = [v for v in required_vars if not os.getenv(v)]

    if not missing:
        print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}⚠ Missing: {', '.join(missing)}{Style.RESET_ALL}")
        print(f"       Using defaults where possible")

    # 6. Backup script
    print(f"[CHECK] Backup script (scripts/backup_postgres.py) ... ", end="")
    if (PROJECT_ROOT / "scripts/backup_postgres.py").exists():
        print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}○ Not found (backups disabled){Style.RESET_ALL}")

    print(f"\n{'='*80}")
    if checks_passed:
        print(f"{Fore.GREEN}{Style.BRIGHT}✓ ALL CHECKS PASSED - READY TO START{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}{Style.BRIGHT}⚠ SOME CHECKS FAILED - REVIEW ABOVE{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[WARNING] System may not function correctly{Style.RESET_ALL}")
    print(f"{'='*80}\n")

    return checks_passed, db_monitor


# ============================================================================
# STATUS DASHBOARD
# ============================================================================

def display_dashboard(scrapers, db_stats=None, twitter_activity=None, cookie_stats=None, table_thresholds=None):
    """Display enhanced status dashboard with colors and metrics."""
    print(f"\n{'='*80}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'PJX TRADING SYSTEM - ORCHESTRATOR DASHBOARD':^80}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")

    if orchestrator_start_time:
        uptime = datetime.now() - orchestrator_start_time
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        print(f"{Fore.WHITE}Uptime: {hours}h {minutes}m{Style.RESET_ALL}")

    print(f"{'='*80}\n")

    # Scraper Status Section
    print(f"{Fore.YELLOW}{Style.BRIGHT}SCRAPER STATUS:{Style.RESET_ALL}")
    print(f"{'NAME':<32} {'STATUS':<15} {'PID':<8} {'UPTIME':<12} {'RESTARTS':<10}")
    print(f"{'-'*80}")

    for scraper in scrapers:
        name = scraper['name']
        enabled = scraper.get('enabled', False)
        config = scraper_configs.get(name, scraper)
        mode = config.get('mode', 'daemon').lower()

        if not enabled:
            print(f"{Fore.WHITE}{name:<32} DISABLED{Style.RESET_ALL}")
            continue

        if name in running_processes:
            process = running_processes[name]
            if process and process.poll() is None:
                # Running
                status = f"{Fore.GREEN}✓ RUNNING{Style.RESET_ALL}"
                pid = str(process.pid)
                uptime = get_scraper_uptime(name)
                restarts = restart_attempts.get(name, 0)

                restart_color = Fore.GREEN if restarts == 0 else Fore.YELLOW if restarts < 2 else Fore.RED
                restart_str = f"{restart_color}{restarts}/3{Style.RESET_ALL}"

                print(f"{name:<32} {status:<24} {pid:<8} {uptime:<12} {restart_str}")
            else:
                # Crashed
                status = f"{Fore.RED}✗ CRASHED{Style.RESET_ALL}"
                print(f"{name:<32} {status:<24} {'N/A':<8} {'N/A':<12} {restart_attempts.get(name, 0)}/3")
        else:
            restarts = restart_attempts.get(name, 0)
            if mode == 'oneshot':
                info = oneshot_status.get(name, {})
                last_completed = info.get('last_completed')
                next_run = info.get('next_run')
                if last_completed:
                    status = f"{Fore.CYAN}WAITING{Style.RESET_ALL}"
                    uptime = format_time_until(next_run) if next_run else format_time_since(last_completed)
                    print(f"{name:<32} {status:<24} {'N/A':<8} {uptime:<12} {restarts}/3")
                else:
                    status = f"{Fore.YELLOW}○ NOT STARTED{Style.RESET_ALL}"
                    print(f"{name:<32} {status:<24} {'N/A':<8} {'N/A':<12} {restarts}/3")
            else:
                status = f"{Fore.YELLOW}○ NOT STARTED{Style.RESET_ALL}"
                print(f"{name:<32} {status:<24} {'N/A':<8} {'N/A':<12} {restarts}/3")

    # Database Section
    if db_stats:
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}DATABASE HEALTH:{Style.RESET_ALL}")
        print(f"{'TABLE':<28} {'ROWS':<15} {'CHANGE':<12} {'FRESHNESS':<15}")
        print(f"{'-'*80}")

        # Choose thresholds: prefer dynamic thresholds passed in, else defaults
        threshold_map = table_thresholds or TABLE_DEFAULT_THRESHOLD_MINUTES

        for table, stats in sorted(db_stats.items()):
            if 'error' in stats:
                print(f"{table:<28} {Fore.RED}ERROR: {stats['error'][:30]}{Style.RESET_ALL}")
                continue

            count = f"{stats['count']:,}"
            change = stats.get('change', 0)

            if change > 0:
                change_str = f"{Fore.GREEN}+{change}{Style.RESET_ALL}"
            elif change < 0:
                change_str = f"{Fore.RED}{change}{Style.RESET_ALL}"
            else:
                change_str = f"{Fore.WHITE}0{Style.RESET_ALL}"

            # Freshness indicator
            if stats['last_update']:
                age_min = (datetime.now() - stats['last_update'].replace(tzinfo=None)).total_seconds() / 60
                threshold = threshold_map.get(table, TABLE_DEFAULT_THRESHOLD_MINUTES.get(table, 60))
                # Use table-aware thresholds for color coding
                if age_min <= threshold * 0.5:
                    fresh = f"{Fore.GREEN}✓ Fresh ({age_min:.0f}m){Style.RESET_ALL}"
                elif age_min <= threshold:
                    fresh = f"{Fore.YELLOW}○ Aging ({age_min:.0f}m){Style.RESET_ALL}"
                else:
                    fresh = f"{Fore.RED}✗ Stale ({age_min:.0f}m){Style.RESET_ALL}"
            else:
                fresh = f"{Fore.WHITE}○ Empty{Style.RESET_ALL}"

            print(f"{table:<28} {count:<15} {change_str:<20} {fresh}")

        # Show total statistics
        total_rows = sum(s['count'] for s in db_stats.values() if 'count' in s)
        total_change = sum(s.get('change', 0) for s in db_stats.values())

        print(f"\n{'TOTALS':<28} {total_rows:,} rows      {'+' if total_change >= 0 else ''}{total_change} new")

    # Twitter Activity Section
    twitter_scrapers = [s for s in scrapers if 'twitter' in s['name'].lower() and s.get('enabled')]
    if twitter_scrapers:
        print(f"\n{Fore.CYAN}{Style.BRIGHT}TWITTER SCRAPER ACTIVITY:{Style.RESET_ALL}")

        for scraper in twitter_scrapers:
            name = scraper['name']
            source_key = TWITTER_SOURCE_MAP.get(name)
            db_info = twitter_activity.get(source_key) if twitter_activity and source_key else None

            # Skip if not running
            if name not in running_processes or not running_processes[name] or running_processes[name].poll() is not None:
                if not db_info:
                    continue
                activity = scraper_activity.get(name, {})
                logs = []
            else:
                activity = scraper_activity.get(name, {})
                logs = list(scraper_logs.get(name, []))

            # Header with scraper name
            print(f"\n{Fore.MAGENTA}► {name}{Style.RESET_ALL}")

            # Cycle + status line
            status_bits = []
            cycle_status = activity.get('cycle_status')
            if cycle_status == 'running':
                status_bits.append(f"{Fore.GREEN}RUNNING{Style.RESET_ALL}")
            elif cycle_status:
                status_bits.append(f"{Fore.WHITE}{cycle_status.upper()}{Style.RESET_ALL}")

            if activity.get('current_token'):
                status_bits.append(f"Now {Fore.CYAN}${activity['current_token']}{Style.RESET_ALL}")
            if activity.get('tokens_in_cycle'):
                status_bits.append(f"{activity['tokens_in_cycle']} tokens this cycle")

            if activity.get('last_cycle_completed'):
                status_bits.append(f"Last cycle {format_time_since(activity['last_cycle_completed'])}")
            elif activity.get('last_cycle_start'):
                status_bits.append(f"Started {format_time_since(activity['last_cycle_start'])}")

            if activity.get('next_cycle_eta'):
                status_bits.append(f"Next {format_time_until(activity['next_cycle_eta'])}")

            if status_bits:
                print(f"  {' | '.join(status_bits)}")

            # Database / tweet metrics
            db_bits = []
            if activity.get('last_tweet_count'):
                db_bits.append(f"Last pull {activity['last_tweet_count']} tweets")
            if activity.get('last_saved_count') is not None:
                saved = activity['last_saved_count']
                when = format_time_since(activity.get('last_db_save')) if activity.get('last_db_save') else ''
                db_bits.append(f"Saved {saved} ({when})" if when else f"Saved {saved}")
            if activity.get('total_saved'):
                db_bits.append(f"Total saved {activity['total_saved']:,}")
            if activity.get('total_tweets'):
                db_bits.append(f"Total collected {activity['total_tweets']:,}")
            if db_info and db_info.get('total_saved'):
                db_bits.append(f"DB {db_info['total_saved']:,} in {db_info['lookback_minutes']}m")
            if db_info and db_info.get('last_saved'):
                last_saved = db_info['last_saved']
                if getattr(last_saved, 'tzinfo', None):
                    last_saved = last_saved.replace(tzinfo=None)
                db_bits.append(f"DB save {format_time_since(last_saved)}")
            if db_bits:
                print(f"  Database: {' | '.join(db_bits)}")

            # Cookie / auth / rate limit state
            cookie_bits = []
            cookie_status = activity.get('cookie_status')
            if cookie_status == 'ok':
                last_refresh = activity.get('last_cookie_refresh')
                msg = f"{Fore.GREEN}OK{Style.RESET_ALL}"
                if last_refresh:
                    msg += f" ({format_time_since(last_refresh)})"
                cookie_bits.append(msg)
            elif cookie_status == 'refreshing':
                cookie_bits.append(f"{Fore.YELLOW}Refreshing…{Style.RESET_ALL}")
            elif cookie_status == 'failed':
                msg = f"{Fore.RED}FAILED{Style.RESET_ALL}"
                if activity.get('last_cookie_failure'):
                    msg += f" ({format_time_since(activity['last_cookie_failure'])})"
                cookie_bits.append(msg)

            if activity.get('last_auth_error'):
                cookie_bits.append(f"Auth issue {format_time_since(activity['last_auth_error'])}")
            if activity.get('rate_limited'):
                reset = activity.get('rate_limit_reset')
                cookie_bits.append(f"Rate limit {format_time_until(reset)}")

            if cookie_bits:
                print(f"  Cookies: {' | '.join(cookie_bits)}")

            # Recent token history
            token_history = list(activity.get('token_history', []))
            if token_history:
                recent_tokens = []
                for entry in token_history[-4:]:
                    label = f"${entry['token']}"
                    if entry.get('count') is not None:
                        label += f"({entry['count']})"
                    recent_tokens.append(label)
                print(f"  Tokens: {' → '.join(recent_tokens)}")
            elif db_info and db_info.get('tokens'):
                recent_tokens = [f"${t['token']}({t['count']})" for t in db_info['tokens']]
                print(f"  Tokens (DB): {' → '.join(recent_tokens)}")

            # Last error context
            if activity.get('last_error'):
                err = activity['last_error']
                when = format_time_since(err.get('time'))
                print(f"  {Fore.RED}Last error {when}: {err['message']}{Style.RESET_ALL}")

            # Show recent activity logs (last 5 lines)
            if logs:
                print(f"  {Fore.WHITE}Recent Activity:{Style.RESET_ALL}")
                for log in logs[-5:]:
                    # Color-code by type
                    if log['type'] == 'error':
                        color = Fore.RED
                        icon = '✗'
                    elif log['type'] == 'warning':
                        color = Fore.YELLOW
                        icon = '⚠'
                    elif log['type'] == 'alert':
                        color = Fore.MAGENTA
                        icon = '🚀'
                    elif log['type'] == 'cookie_refresh':
                        color = Fore.CYAN
                        icon = '🔄'
                    elif log['type'] == 'tweet_count':
                        color = Fore.GREEN
                        icon = '📊'
                    elif log['type'] == 'database':
                        color = Fore.BLUE
                        icon = '💾'
                    elif log['type'] == 'rate_limit':
                        color = Fore.YELLOW
                        icon = '⏸'
                    else:
                        color = Fore.WHITE
                        icon = '•'

                    print(f"    {Fore.WHITE}[{log['time']}]{Style.RESET_ALL} {color}{icon} {log['message']}{Style.RESET_ALL}")

    if cookie_stats:
        print(f"\n{Fore.CYAN}{Style.BRIGHT}COOKIE HEALTH:{Style.RESET_ALL}")
        for entry in cookie_stats:
            age = entry['age_minutes']
            last_updated = entry['updated_at']
            if age > COOKIE_STALE_MINUTES:
                color = Fore.RED
                status = 'STALE'
            elif age > COOKIE_WARNING_MINUTES:
                color = Fore.YELLOW
                status = 'Aging'
            else:
                color = Fore.GREEN
                status = 'Fresh'
            label = f"A{entry.get('account_num', '?')}"
            print(f"  {label:<4} {entry['name']:<22} {color}{status:<6}{Style.RESET_ALL} updated {format_time_since(last_updated)}")

    print(f"\n{'='*80}\n")


def get_scraper_uptime(scraper_name):
    """Calculate scraper uptime."""
    if scraper_name not in scraper_start_times:
        return "N/A"

    uptime = datetime.now() - scraper_start_times[scraper_name]
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


# ============================================================================
# STUCK SCRAPER DETECTION
# ============================================================================

def detect_stuck_scrapers(db_monitor, stats=None, warnings=None):
    """Detect scrapers that are running but not producing data."""
    if not db_monitor:
        return []

    if stats is None:
        stats = db_monitor.get_table_stats()
    if not stats:
        return []

    if warnings is None:
        warnings = db_monitor.check_data_freshness(stats)

    stuck = []
    for name, process in running_processes.items():
        if process and process.poll() is None:  # Running
            table = map_scraper_to_table(name)

            if table:
                # Check if this table is in warnings
                for warning_table, age in warnings:
                    if warning_table == table:
                        stuck.append((name, age))
                        break

    return stuck


# ============================================================================
# ONESHOT SCHEDULING HELPERS
# ============================================================================

def schedule_next_oneshot_run(name, reference_time=None):
    """Compute the next run time for a one-shot scraper."""
    if reference_time is None:
        reference_time = datetime.now()
    interval = scraper_intervals.get(name, 24 * 60 * 60)
    oneshot_status[name]['next_run'] = reference_time + timedelta(seconds=interval)


# ============================================================================
# PERIODIC SUMMARIES
# ============================================================================

def print_summary_stats(db_monitor):
    """Print periodic summary statistics."""
    global last_summary_time

    if not db_monitor:
        return

    stats = db_monitor.get_table_stats()
    if not stats:
        return

    uptime = datetime.now() - orchestrator_start_time

    print(f"\n{'='*80}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{SUMMARY_INTERVAL_MINUTES}-MINUTE SUMMARY{Style.RESET_ALL}")
    print(f"System Uptime: {uptime.total_seconds() / 3600:.1f} hours")
    print(f"{'='*80}")

    # Total statistics
    total_rows = sum(s['count'] for s in stats.values() if 'count' in s)
    total_change = sum(s.get('change', 0) for s in stats.values())

    print(f"\nTotal Records: {Fore.CYAN}{total_rows:,}{Style.RESET_ALL}")
    print(f"Records Added (last {MONITOR_INTERVAL_SECONDS}s): {Fore.GREEN}+{total_change}{Style.RESET_ALL}" if total_change > 0 else f"Records Added (last {MONITOR_INTERVAL_SECONDS}s): {total_change}")

    # Top tables by activity
    active_tables = sorted(
        [(k, v.get('change', 0)) for k, v in stats.items() if 'count' in v],
        key=lambda x: x[1],
        reverse=True
    )[:5]

    if any(change > 0 for _, change in active_tables):
        print(f"\n{Fore.YELLOW}Most Active Tables:{Style.RESET_ALL}")
        for table, change in active_tables:
            if change > 0:
                print(f"  • {table}: {Fore.GREEN}+{change}{Style.RESET_ALL}")

    # Check for stale data
    warnings = db_monitor.check_data_freshness(stats)
    if warnings:
        print(f"\n{Fore.YELLOW}Data Freshness Warnings:{Style.RESET_ALL}")
        for table, age in warnings[:5]:  # Show top 5
            print(f"  • {table}: {Fore.YELLOW}No updates for {age:.0f} minutes{Style.RESET_ALL}")

    # Scraper health
    total_scrapers = len([p for p in running_processes.values() if p and p.poll() is None])
    crashed_scrapers = len([p for p in running_processes.values() if p and p.poll() is not None])

    print(f"\n{Fore.YELLOW}Scraper Health:{Style.RESET_ALL}")
    print(f"  • Running: {Fore.GREEN}{total_scrapers}{Style.RESET_ALL}")
    if crashed_scrapers > 0:
        print(f"  • Crashed: {Fore.RED}{crashed_scrapers}{Style.RESET_ALL}")

    # Next backup time
    if last_backup_time:
        next_backup = last_backup_time + timedelta(hours=BACKUP_INTERVAL_HOURS)
        time_until = next_backup - datetime.now()
        hours_until = time_until.total_seconds() / 3600
        print(f"\n{Fore.CYAN}Next Backup:{Style.RESET_ALL} {hours_until:.1f} hours")

    # Stablecoin snapshot
    stablecoin_snapshot = db_monitor.get_stablecoin_snapshot()
    if stablecoin_snapshot:
        print(f"\n{Fore.CYAN}Stablecoin Liquidity:{Style.RESET_ALL}")
        print(f"  • Total Market Cap: ${stablecoin_snapshot['total_market_cap']:,.0f}")
        print(f"  • Total Volume 24h: ${stablecoin_snapshot['total_volume']:,.0f}")
        print(f"  • Avg Velocity: {stablecoin_snapshot['avg_velocity']:.3f}x")
        if stablecoin_snapshot['supply_alerts']:
            alerts = ', '.join(
                f"{sym} {pct:+.2f}%"
                for sym, pct in stablecoin_snapshot['supply_alerts']
            )
            print(f"  • Supply Shifts: {alerts}")
        if stablecoin_snapshot['depeg_alerts']:
            alerts = ', '.join(
                f"{sym} {pct:+.2f}%"
                for sym, pct in stablecoin_snapshot['depeg_alerts']
            )
            print(f"  • De-peg Watch: {alerts}")

    # DEX summary
    dex_snapshot = db_monitor.get_dex_snapshot()
    if dex_snapshot and dex_snapshot['top_tokens']:
        print(f"\n{Fore.CYAN}DEX Liquidity (last {dex_snapshot['lookback_minutes']}m):{Style.RESET_ALL}")
        for entry in dex_snapshot['top_tokens']:
            print(
                f"  • {entry['token']}: "
                f"Liquidity ${entry['liquidity']:,.0f}, "
                f"Volume ${entry['volume']:,.0f}, "
                f"V/L {entry['ratio']:.2f}"
            )

    # Twitter collection stats
    twitter_stats = db_monitor.get_twitter_collection_stats()
    if twitter_stats:
        print(f"\n{Fore.CYAN}Twitter Collection Stats:{Style.RESET_ALL}")

        # Last 15 minutes
        if 'last_15min' in twitter_stats:
            print(f"  • Last 15 min: {Fore.GREEN}{twitter_stats['last_15min']:,} tweets{Style.RESET_ALL}")

        # Last hour (if we have 4+ 15-min intervals)
        if 'last_hour' in twitter_stats:
            print(f"  • Last hour: {Fore.GREEN}{twitter_stats['last_hour']:,} tweets{Style.RESET_ALL} ({twitter_stats['last_hour_avg']:.0f}/15min avg)")

        # Hourly breakdown (if uptime > 1 hour)
        if 'hourly_breakdown' in twitter_stats and twitter_stats['hourly_breakdown']:
            print(f"  • Hourly breakdown:")
            for hour_data in twitter_stats['hourly_breakdown']:
                print(f"    - {hour_data['label']}: {hour_data['count']:,} tweets")

        # Daily breakdown (if uptime > 24 hours)
        if 'daily_breakdown' in twitter_stats and twitter_stats['daily_breakdown']:
            print(f"  • Daily breakdown:")
            for day_data in twitter_stats['daily_breakdown']:
                print(f"    - {day_data['label']}: {day_data['count']:,} tweets")

    # Exchange flow summary
    flow_snapshot = db_monitor.get_exchange_flow_snapshot()
    if flow_snapshot and flow_snapshot['recent_flows']:
        print(f"\n{Fore.CYAN}Exchange Flows (last {flow_snapshot['lookback_hours']}h):{Style.RESET_ALL}")
        for flow in flow_snapshot['recent_flows']:
            smart_tag = " (Smart)" if flow['is_smart'] else ""
            print(
                f"  • {flow['token']} {flow['flow_type']} "
                f"${flow['usd_value']:,.0f} via {flow['exchange']}{smart_tag}"
            )

    print(f"{'='*80}\n")

    last_summary_time = datetime.now()


# ============================================================================
# CORE FUNCTIONS (from original)
# ============================================================================

def load_config():
    """Load scraper configuration from YAML file."""
    config_path = PROJECT_ROOT / "config/scrapers.yaml"

    if not config_path.exists():
        print(f"{Fore.RED}[ERROR] config/scrapers.yaml not found!{Style.RESET_ALL}")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    return config.get('scrapers', [])


def get_python_executable():
    """Get the correct Python executable path."""
    # Try configured venv first
    venv_path = os.getenv('PYTHON_VENV', r'C:\venvs\pjxvenv\Scripts\python.exe')
    if os.path.exists(venv_path):
        return venv_path

    # Try local venv
    venv_paths = [
        PROJECT_ROOT / '.venv' / 'Scripts' / 'python.exe',  # Windows
        PROJECT_ROOT / '.venv' / 'bin' / 'python',           # Unix
    ]

    for path in venv_paths:
        if path.exists():
            return str(path.absolute())

    # Fall back to current Python
    return sys.executable


def start_scraper(scraper):
    """Start a single scraper as a background process."""
    name = scraper['name']
    name_lower = name.lower()
    script = scraper['script']
    script_path = (PROJECT_ROOT / script).resolve()
    mode = scraper.get('mode', 'daemon').lower()
    interval_seconds = parse_interval_seconds(scraper.get('interval'))

    if not script_path.exists():
        print(f"{Fore.YELLOW}[WARNING] {name}: Script not found at {script_path}{Style.RESET_ALL}")
        return None

    try:
        python_exe = get_python_executable()

        # Create environment with orchestrator flag
        env = os.environ.copy()
        env['ORCHESTRATOR_RUNNING'] = 'true'
        env.setdefault('PYTHONIOENCODING', 'utf-8')
        env.setdefault('PYTHONUTF8', '1')
        # Always bypass the proxy for local connections (chromedriver, DB, etc.)
        env.setdefault('NO_PROXY', '127.0.0.1,localhost')
        env.setdefault('no_proxy', '127.0.0.1,localhost')

        # Enable mobile emulation for Twitter scrapers (Chad Scraper strategy)
        if 'twitter' in name_lower and MOBILE_EMULATION_ENABLED:
            # Set mobile user agent
            mobile_ua = get_random_mobile_user_agent()
            env['MOBILE_USER_AGENT'] = mobile_ua
            env['ENABLE_MOBILE_EMULATION'] = 'true'

            # Log that we're using mobile emulation
            print(f"{Fore.CYAN}[MOBILE] {name}: Using mobile emulation{Style.RESET_ALL}")

        # Only route through Tor when required. Override rules:
        # - use_proxy: false -> never proxy this scraper
        # - PROXY_ALL_SCRAPERS=true -> proxy everything (except localhost)
        # - default: proxy Binance scrapers (US-blocked) and any scraper explicitly marked use_proxy
        proxy_flag = scraper.get('use_proxy')
        if proxy_flag is False:
            wants_proxy = False
        else:
            wants_proxy = (
                PROXY_ALL_SCRAPERS
                or proxy_flag is True
                or 'binance' in name_lower
                # Don't use Tor for Twitter when mobile emulation is enabled
                or ('twitter' in name_lower and not MOBILE_EMULATION_ENABLED)
            )
        proxy_enabled = tor_available and wants_proxy
        if proxy_enabled:
            # WSL Tor proxy is accessible from Windows via localhost
            env['HTTP_PROXY'] = 'socks5h://127.0.0.1:9050'
            env['HTTPS_PROXY'] = 'socks5h://127.0.0.1:9050'
            env['ALL_PROXY'] = 'socks5h://127.0.0.1:9050'
        else:
            # Remove any inherited proxy settings so non-Twitter scrapers use direct connections
            env.pop('HTTP_PROXY', None)
            env.pop('HTTPS_PROXY', None)
            env.pop('ALL_PROXY', None)
            if wants_proxy and not tor_available:
                print(f"{Fore.YELLOW}[WARNING] {name}: Tor proxy requested but not available; using direct connection{Style.RESET_ALL}")

        # Start process in background with output capture
        # -u flag ensures unbuffered output for real-time monitoring
        process = subprocess.Popen(
            [python_exe, '-u', str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # Unbuffered (best for real-time monitoring)
            universal_newlines=False,  # We'll decode manually
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
            cwd=str(PROJECT_ROOT),
            env=env  # Pass modified environment
        )

        scraper_start_times[name] = datetime.now()
        scraper_modes[name] = mode
        scraper_intervals[name] = interval_seconds

        if mode == 'oneshot':
            oneshot_status[name]['last_started'] = datetime.now()
            oneshot_status[name].pop('next_run', None)

        # Start real-time output monitoring for every scraper
        start_output_monitor_thread(process, name)
        monitor_note = " - Real-time monitoring enabled" if 'twitter' in name.lower() else ""
        print(f"{Fore.GREEN}[STARTED] {name} (PID: {process.pid}){monitor_note}{Style.RESET_ALL}")

        return process

    except Exception as e:
        print(f"{Fore.RED}[ERROR] {name}: Failed to start - {e}{Style.RESET_ALL}")
        return None


def stop_scraper(name, process):
    """Stop a running scraper."""
    try:
        if sys.platform == 'win32':
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()

        try:
            process.wait(timeout=5)
            print(f"{Fore.WHITE}[STOPPED] {name}{Style.RESET_ALL}")
        except subprocess.TimeoutExpired:
            process.kill()
            print(f"{Fore.YELLOW}[KILLED] {name} (forced){Style.RESET_ALL}")

        return True

    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to stop {name}: {e}{Style.RESET_ALL}")
        return False


def stop_all_scrapers():
    """Stop all running scrapers."""
    print(f"\n{'='*80}")
    print(f"{Fore.YELLOW}Stopping all scrapers...{Style.RESET_ALL}")
    print(f"{'='*80}")

    for name, process in running_processes.items():
        if process and process.poll() is None:
            stop_scraper(name, process)

    running_processes.clear()


def run_database_backup():
    """Run database backup script."""
    global last_backup_time, last_backup_attempt

    try:
        attempt_time = datetime.now()
        last_backup_attempt = attempt_time

        print(f"\n{Fore.CYAN}[BACKUP] Starting daily database backup at {attempt_time.strftime('%H:%M:%S')}{Style.RESET_ALL}")

        python_exe = get_python_executable()
        backup_script = PROJECT_ROOT / "scripts/backup_postgres.py"

        if not backup_script.exists():
            print(f"{Fore.YELLOW}[WARNING] Backup script not found{Style.RESET_ALL}")
            return False

        result = subprocess.run(
            [python_exe, str(backup_script)],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            print(f"{Fore.GREEN}[BACKUP] Database backup completed successfully{Style.RESET_ALL}")
            last_backup_time = attempt_time
            return True
        else:
            print(f"{Fore.RED}[ERROR] Backup failed with exit code {result.returncode}{Style.RESET_ALL}")
            return False

    except Exception as e:
        print(f"{Fore.RED}[ERROR] Backup failed: {e}{Style.RESET_ALL}")
        return False


def should_run_backup():
    """Check if it's time to run a backup."""
    global last_backup_time, last_backup_attempt

    now = datetime.now()
    retry_interval = timedelta(minutes=BACKUP_RETRY_INTERVAL_MINUTES)

    if last_backup_time is None:
        if last_backup_attempt is None:
            return True
        return now - last_backup_attempt >= retry_interval

    if now - last_backup_time < timedelta(hours=BACKUP_INTERVAL_HOURS):
        return False

    if last_backup_attempt is None:
        return True

    return now - last_backup_attempt >= retry_interval


def monitor_scrapers(db_monitor, allowed_names=None, diag_deadline=None):
    """Monitor running scrapers and restart if they crash."""
    global last_summary_time, scraper_configs

    scrapers = load_config()
    if allowed_names:
        scrapers = [s for s in scrapers if s['name'] in allowed_names]
    scraper_configs = {s['name']: s for s in scrapers}
    if db_monitor:
        db_monitor.set_table_thresholds(build_table_thresholds(scrapers))
    scrapers_dict = {
        s['name']: s
        for s in scrapers
        if s.get('enabled', False) and (not allowed_names or s['name'] in allowed_names)
    }
    last_summary_time = datetime.now()

    while True:
        try:
            # Check if it's time to run a backup
            if should_run_backup():
                run_database_backup()

            # Get database stats
            db_stats = None
            twitter_db_activity = None
            cookie_stats = get_cookie_file_stats()
            freshness_warnings = None
            if db_monitor:
                db_stats = db_monitor.get_table_stats()
                twitter_db_activity = db_monitor.get_recent_twitter_activity()
                if db_stats:
                    freshness_warnings = db_monitor.check_data_freshness(db_stats)

            # Display dashboard
            display_dashboard(scrapers, db_stats, twitter_db_activity, cookie_stats, table_thresholds=db_monitor.table_thresholds if db_monitor else None)

            # Check for stuck scrapers (displayed in DB health table only)
            if db_monitor:
                stuck = detect_stuck_scrapers(db_monitor, stats=db_stats, warnings=freshness_warnings)
                # Staleness info shown in database health table - no need for separate warnings

            # Check each process for crashes
            for name, process in list(running_processes.items()):
                if process and process.poll() is not None:  # Process ended
                    exit_code = process.returncode
                    mode = scraper_modes.get(name, 'daemon')

                    if mode == 'oneshot' and exit_code == 0:
                        completion_time = datetime.now()
                        print(f"{Fore.CYAN}[COMPLETE] {name} finished run at {completion_time.strftime('%H:%M:%S')}{Style.RESET_ALL}")
                        restart_attempts[name] = 0
                        oneshot_status[name]['last_completed'] = completion_time
                        schedule_next_oneshot_run(name, completion_time)
                        running_processes.pop(name, None)
                        scraper_start_times.pop(name, None)
                        continue

                    print(f"{Fore.RED}[WARNING] {name} stopped unexpectedly (exit code: {exit_code}){Style.RESET_ALL}")

                    attempts = restart_attempts.get(name, 0)

                    if attempts < MAX_RESTART_ATTEMPTS:
                        restart_attempts[name] = attempts + 1
                        print(f"{Fore.YELLOW}[RESTART] Attempting to restart {name} (attempt {restart_attempts[name]}/{MAX_RESTART_ATTEMPTS}){Style.RESET_ALL}")

                        time.sleep(5)

                        if name in scrapers_dict:
                            new_process = start_scraper(scrapers_dict[name])
                            if new_process:
                                running_processes[name] = new_process
                                print(f"{Fore.GREEN}[OK] {name} restarted successfully (PID: {new_process.pid}){Style.RESET_ALL}")
                            else:
                                print(f"{Fore.RED}[ERROR] Failed to restart {name}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}[FATAL] {name} has crashed {MAX_RESTART_ATTEMPTS} times. Giving up.{Style.RESET_ALL}")
                        del running_processes[name]
                        if mode == 'oneshot':
                            failure_time = datetime.now()
                            oneshot_status[name]['last_failed'] = failure_time
                            schedule_next_oneshot_run(name, failure_time)

            # Schedule one-shot scrapers for their next run
            now = datetime.now()
            for name, config in scrapers_dict.items():
                mode = config.get('mode', 'daemon').lower()
                if mode != 'oneshot' or name in running_processes:
                    continue

                next_run = oneshot_status.get(name, {}).get('next_run')
                if next_run and now >= next_run:
                    print(f"{Fore.CYAN}[SCHEDULE] Restarting one-shot scraper {name}{Style.RESET_ALL}")
                    new_process = start_scraper(config)
                    if new_process:
                        running_processes[name] = new_process
                        restart_attempts[name] = 0
                    else:
                        print(f"{Fore.RED}[ERROR] Failed to restart one-shot scraper {name}{Style.RESET_ALL}")

            # Check for IP rotation restart signal
            restart_signal_file = PROJECT_ROOT / "outputs" / ".restart_twitter_scrapers"
            if restart_signal_file.exists():
                print(f"{Fore.YELLOW}[IP-ROTATION] Restart signal detected - restarting Twitter scrapers{Style.RESET_ALL}")
                try:
                    restart_signal_file.unlink()
                    # Restart all Twitter scrapers
                    for name, process in list(running_processes.items()):
                        if 'twitter' in name.lower():
                            print(f"{Fore.YELLOW}[IP-ROTATION] Stopping {name} for IP rotation...{Style.RESET_ALL}")
                            stop_scraper(name, process)
                            del running_processes[name]
                            # Will be restarted in next iteration
                except Exception as e:
                    print(f"{Fore.RED}[ERROR] Failed to process restart signal: {e}{Style.RESET_ALL}")

            # Periodic summary
            if datetime.now() - last_summary_time >= timedelta(minutes=SUMMARY_INTERVAL_MINUTES):
                print_summary_stats(db_monitor)

            # Sleep before next check
            if diag_deadline and datetime.now() >= diag_deadline:
                print(f"{Fore.CYAN}[DIAG] Requested runtime reached, stopping scrapers...{Style.RESET_ALL}")
                break

            time.sleep(MONITOR_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}[SIGNAL] Keyboard interrupt received...{Style.RESET_ALL}")
            break


def main(args=None):
    """Main orchestrator function."""
    global orchestrator_start_time, scraper_configs, ip_monitor
    orchestrator_start_time = datetime.now()
    ip_monitor = None

    if args is None:
        args = argparse.Namespace(diag=None, diag_seconds=0)
    diag_pattern = args.diag.lower() if getattr(args, 'diag', None) else None
    diag_deadline = None
    if diag_pattern and getattr(args, 'diag_seconds', 0):
        diag_deadline = datetime.now() + timedelta(seconds=args.diag_seconds)

    print(f"\n{'='*80}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'PJX TRADING SYSTEM - ORCHESTRATOR':^80}{Style.RESET_ALL}")
    print(f"{'='*80}")

    # Run pre-flight checks
    checks_passed, db_monitor = run_preflight_checks()

    if not checks_passed:
        print(f"{Fore.YELLOW}[WARNING] Some checks failed - proceed with caution{Style.RESET_ALL}")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print(f"{Fore.RED}[ABORT] Exiting...{Style.RESET_ALL}")
            return

    # Initialize IP rotation monitor for Twitter scrapers
    ip_monitor = None
    try:
        from monitors.twitter_ip_monitor import integrate_with_orchestrator
        ip_monitor = integrate_with_orchestrator()
        print(f"{Fore.GREEN}[OK] IP rotation monitor started{Style.RESET_ALL}")
    except ImportError:
        print(f"{Fore.YELLOW}[INFO] IP rotation monitor not available{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}[WARNING] Failed to start IP monitor: {e}{Style.RESET_ALL}")

    # Load configuration
    scrapers = load_config()
    scraper_configs = {s['name']: s for s in scrapers}
    enabled_scrapers = [s for s in scrapers if s.get('enabled', False)]
    if db_monitor:
        db_monitor.set_table_thresholds(build_table_thresholds(scrapers))

    if diag_pattern:
        filtered = [s for s in enabled_scrapers if diag_pattern in s['name'].lower()]
        if not filtered:
            print(f"{Fore.RED}[ERROR] No scraper matches '{args.diag}' for diag mode{Style.RESET_ALL}")
            return
        enabled_scrapers = filtered
        print(f"{Fore.CYAN}[DIAG] Running diagnostic mode for {len(enabled_scrapers)} scraper(s){Style.RESET_ALL}")

    if not enabled_scrapers:
        print(f"\n{Fore.YELLOW}[WARNING] No scrapers are enabled in config/scrapers.yaml{Style.RESET_ALL}")
        print(f"{Fore.WHITE}[INFO] Edit config/scrapers.yaml and set 'enabled: true'{Style.RESET_ALL}")
        return

    print(f"\n{Fore.YELLOW}Found {len(enabled_scrapers)} enabled scrapers:{Style.RESET_ALL}")
    for scraper in enabled_scrapers:
        name = scraper['name']
        category = scraper.get('category', 'unknown')
        interval = scraper.get('interval', 'N/A')
        print(f"  • [{category:15}] {name:30} (runs {interval})")

    print(f"\n{'='*80}")
    print(f"{Fore.YELLOW}Starting scrapers...{Style.RESET_ALL}")
    print(f"{'='*80}\n")

    # Start all enabled scrapers with staggered timing
    for i, scraper in enumerate(enabled_scrapers):
        name = scraper['name']
        process = start_scraper(scraper)

        if process:
            running_processes[name] = process

        # Stagger starts to reduce burst risk while keeping startup quick
        if i < len(enabled_scrapers) - 1:
            delay = get_start_stagger_seconds(scraper)
            if delay > 0:
                print(f"{Fore.WHITE}[WAIT] Waiting {delay:.0f} seconds before starting next scraper...{Style.RESET_ALL}")
                time.sleep(delay)

    if not running_processes:
        print(f"\n{Fore.RED}[ERROR] No scrapers started successfully!{Style.RESET_ALL}")
        return

    print(f"\n{'='*80}")
    print(f"{Fore.GREEN}[INFO] Orchestrator running. Press Ctrl+C to stop all scrapers.{Style.RESET_ALL}")
    print(f"{Fore.WHITE}[INFO] Dashboard updates every {MONITOR_INTERVAL_SECONDS} seconds{Style.RESET_ALL}")
    print(f"{Fore.WHITE}[INFO] Summary reports every {SUMMARY_INTERVAL_MINUTES} minutes{Style.RESET_ALL}")
    print(f"{'='*80}\n")

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        print(f"\n{Fore.YELLOW}[SIGNAL] Shutdown signal received...{Style.RESET_ALL}")
        if db_monitor:
            db_monitor.close()
        if ip_monitor:
            try:
                ip_monitor.stop()
                print(f"{Fore.GREEN}[OK] IP monitor stopped{Style.RESET_ALL}")
            except:
                pass
        stop_all_scrapers()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)

    allowed_names = {s['name'] for s in enabled_scrapers}

    # Monitor scrapers
    try:
        monitor_scrapers(db_monitor, allowed_names=allowed_names, diag_deadline=diag_deadline)
    finally:
        if db_monitor:
            db_monitor.close()
        if ip_monitor:
            try:
                ip_monitor.stop()
                print(f"{Fore.GREEN}[OK] IP monitor stopped{Style.RESET_ALL}")
            except:
                pass
        stop_all_scrapers()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PJX scraper orchestrator")
    parser.add_argument('--diag', metavar='NAME', help='Run only scrapers matching NAME (case-insensitive substring)')
    parser.add_argument('--diag-seconds', type=int, default=0, help='Automatically stop after N seconds in diag mode (0 = run until interrupted)')
    args = parser.parse_args()

    try:
        main(args)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[INTERRUPTED] Shutting down...{Style.RESET_ALL}")
        stop_all_scrapers()
    except Exception as e:
        print(f"\n{Fore.RED}[FATAL ERROR] {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        stop_all_scrapers()
        sys.exit(1)
