"""
Shared Twitter Scraping Functions
Used by all Twitter scrapers in crypto_scrapers/
Includes: VADER setup, bot detection, Yale coefficient, client initialization
"""

import os
import sys
import json
import psycopg2
from psycopg2 import pool
import httpx
import re
from random import randint
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pathlib import Path


def _force_utf8_io():
    """Ensure stdout/stderr use UTF-8 to avoid Windows charmap crashes."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


_force_utf8_io()

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from monitors.refresh_cookies import refresh_cookies, save_cookies

# ============================================================================
# CONSTANTS
# ============================================================================

# Spam/bot filtering keywords
SPAM_KEYWORDS = [
    'discord', 'telegram', 'airdrop', 'giveaway', 'free tokens',
    'DM me', 'click here', 'join now', '100x guaranteed',
    'presale', 'whitelist', 'mint now'
]

# Bot username detection pattern
BOT_USERNAME_PATTERN = r'^[a-zA-Z]{7,8}\d{8}$'

# User agent rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

# Comprehensive crypto lexicon (150+ terms)
# Based on: GitHub PR #81, academic research, 2025 crypto Twitter slang
CRYPTO_LEXICON = {
    # VERY BULLISH (2.5 to 4.0) - Strong positive signals
    'moonshot': 3.0, '100x': 3.2, '10x': 2.8, 'gem': 3.0,
    'alpha': 2.8, 'early': 2.6, 'stealth launch': 2.9,
    'all time high': 2.3, 'ath': 2.3, 'bull run': 2.5,

    # BULLISH (1.0 to 2.5) - Positive sentiment
    'bullish': 2.3, 'bull': 1.8, 'bulls': 1.9, 'bull market': 2.3,
    'moon': 2.0, 'mooning': 2.2, 'to the moon': 2.5,
    'lambo': 1.8, 'rocket': 2.0, 'pump': 1.4, 'pumping': 1.6,
    'diamond hands': 2.1, 'hodl': 1.0, 'hold': 1.0,
    'long': 1.3, 'accumulate': 1.7, 'buy the dip': 1.8,
    'btd': 1.8, 'breakout': 2.0, 'bounce': 1.1,
    'support': 1.0, 'reversal': 1.2, 'recovery': 1.4,
    'lfg': 2.0, 'wagmi': 2.1, 'send it': 2.3,
    'send': 1.9, 'degen': 1.5, 'ape': 1.6, 'aping': 1.7,
    'based': 1.8, 'giga': 2.2, 'chad': 1.9,
    'strategy': 1.5, 'arbitrage': 0.4,
    'launching': 1.8, 'stealth': 1.7, 'deployed': 1.5,

    # MODERATELY POSITIVE (0.1 to 1.0)
    'green': 0.8, 'profit': 0.9, 'gains': 0.9,
    'uptrend': 0.8, 'trending': 0.6, 'momentum': 0.7,
    'volume spike': 0.8, 'buying pressure': 0.7,
    'accumulation': 0.6, 'entry': 0.5, 'loaded': 0.9,
    'bag': 0.3, 'position': 0.2, 'conviction': 0.6,

    # NEUTRAL/CONTEXT (0.0) - Depends on context
    'gm': 0.0, 'gn': 0.0, 'ser': 0.0, 'anon': 0.0,
    'fren': 0.0, 'whale': 0.0, 'whales': -1.1,
    'sec': 0.0, 'regulation': -1.2, 'regulations': -1.2,
    'ico': -0.4, 'presale': -0.5,

    # MODERATELY NEGATIVE (-1.0 to -0.1)
    'resistance': -0.3, 'overbought': -0.5, 'overvalued': -0.6,
    'distribution': -0.5, 'selling pressure': -0.7,
    'correction': -0.4, 'pullback': -0.3, 'consolidation': -0.2,
    'downtrend': -0.8, 'red': -0.7, 'loss': -0.8,
    'bot': -0.9, 'bots': -0.9, 'manipulation': -2.7,

    # BEARISH (-2.5 to -1.0) - Negative sentiment
    'bearish': -1.4, 'bear': -1.3, 'bear market': -1.6,
    'dump': -1.8, 'dumping': -2.0, 'dumped': -2.1,
    'paper hands': -1.5, 'weak hands': -1.3,
    'fud': -1.9, 'fear': -1.2, 'panic': -1.6,
    'crash': -2.0, 'crashing': -2.2, 'crashed': -2.3,
    'short': -0.8, 'shorting': -1.0, 'shorts': -0.9,
    'sell': -1.0, 'selling': -1.1, 'sold': -1.2,
    'exit': -0.8, 'top signal': -1.4, 'local top': -1.2,
    'bagholding': -1.6, 'bagholder': -1.4, 'bag holder': -1.4,
    'cope': -1.3, 'copium': -1.4, 'hopium': -0.8,
    'ngmi': -1.5, 'not gonna make it': -1.5,
    'jeet': -1.7, 'jeeted': -1.8, 'jeeting': -1.7,
    'fade': -1.3, 'faded': -1.4, 'fading': -1.3,
    'dip': -0.6, 'dipping': -0.8,

    # VERY BEARISH (-4.0 to -2.5) - Scam/danger signals
    'rekt': -2.2, 'wrecked': -2.0, 'liquidated': -2.5,
    'rugpull': -3.5, 'rug pull': -3.5, 'rug': -3.0, 'rugged': -3.6,
    'scam': -3.2, 'scammer': -3.3, 'scamming': -3.4,
    'honeypot': -3.5, 'ponzi': -3.4, 'pyramid': -3.0,
    'exit scam': -3.8, 'exit liquidity': -2.9,
    'pump and dump': -3.0, 'pnd': -2.8,
    'fake': -2.5, 'fraud': -3.0, 'stolen': -2.8,
    'hack': -2.6, 'hacked': -2.8, 'exploit': -2.7,
    'worthless': -2.9, 'dead': -2.6, 'dead coin': -3.0,
    'abandon': -2.5, 'abandoned': -2.7,
    'cnbc': -2.1,

    # MEME COIN SPECIFIC
    'pepe': 0.3, 'wojak': 0.2,
    'doge': 0.4, 'shib': 0.3, 'bonk': 0.4,
    'nfa': 0.0, 'dyor': 0.1, 'zoom out': 0.3,

    # TECHNICAL TRADING TERMS
    'golden cross': 2.2, 'death cross': -2.3,
    'bullish divergence': 1.8, 'bearish divergence': -1.6,
    'higher lows': 1.3, 'lower highs': -1.2,
    'ascending triangle': 1.4, 'descending triangle': -1.3,
    'cup and handle': 1.6, 'head and shoulders': -1.5,
    'double bottom': 1.5, 'double top': -1.4,
    'oversold': 1.2, 'breakdown': -1.8,
    'rsi': 0.0, 'macd': 0.0, 'moving average': 0.0,

    # COMMUNITY/CULTURAL
    'community': 0.5, 'ecosystem': 0.4, 'adoption': 0.8,
    'partnership': 0.7, 'launch': 0.6, 'listing': 0.8,
    'burned': 0.7, 'buyback': 0.9, 'staking': 0.4,
    'utility': 0.5, 'roadmap': 0.3, 'whitepaper': 0.2,
    'audit': 0.6, 'audited': 0.7, 'doxxed': 0.5,
    'airdrop': 0.0, 'giveaway': -0.8,
    'telegram': -0.5, 'discord': -0.4,

    # EXCHANGE/LIQUIDITY TERMS
    'binance': 0.6, 'coinbase': 0.6, 'dex': 0.3,
    'liquidity': 0.5, 'locked liquidity': 1.0,
    'unlocked': -1.5, 'unlock': -1.3,
    'mcap': 0.0, 'market cap': 0.0, 'fdv': 0.0,
    'volume': 0.2, 'high volume': 0.6,
    'low liquidity': -0.9, 'illiquid': -1.1,
}

# ============================================================================
# HTTPX CLIENT SETUP
# ============================================================================

def setup_httpx_patching():
    """Patch httpx.Client to use rotating user agents and proper headers

    Must be called BEFORE importing twikit.Client
    Returns: None (modifies httpx.Client globally)
    """
    original_client = httpx.Client

    def patched_client(*args, **kwargs):
        if 'headers' not in kwargs:
            kwargs['headers'] = {}

        kwargs['headers'].update({
            'User-Agent': USER_AGENTS[randint(0, len(USER_AGENTS)-1)],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })

        kwargs.pop('proxy', None)
        return original_client(*args, **kwargs)

    httpx.Client = patched_client
    print("[OK] httpx client patched with user agent rotation")

# ============================================================================
# VADER SENTIMENT ANALYSIS
# ============================================================================

def init_vader_with_crypto_lexicon():
    """Initialize VADER with comprehensive crypto-specific lexicon (150+ terms)

    Based on research:
    - GitHub PR #81 (community-validated crypto terms)
    - Academic research (800-word crypto market lexicon)
    - 2025 Crypto Twitter slang & meme coin culture
    - Technical analysis & trading terminology

    Returns:
        SentimentIntensityAnalyzer: Configured VADER instance
    """
    vader = SentimentIntensityAnalyzer()
    vader.lexicon.update(CRYPTO_LEXICON)

    print(f"[OK] VADER initialized with {len(CRYPTO_LEXICON)} crypto terms")
    print("[OK] Lexicon covers: bullish/bearish, meme slang, TA, scam signals")

    return vader

def analyze_sentiment(vader, text):
    """Analyze sentiment using VADER

    Args:
        vader: SentimentIntensityAnalyzer instance
        text: Tweet text to analyze

    Returns:
        float: Compound sentiment score (-1 to 1)
    """
    scores = vader.polarity_scores(text)
    return scores['compound']

# ============================================================================
# BOT DETECTION
# ============================================================================

def calculate_bot_probability(user_data):
    """Calculate probability that an account is a bot

    Args:
        user_data: dict with keys: followers, following, username, bio, profile_image_custom

    Returns:
        float: 0.0 (human) to 1.0 (definitely bot)
    """
    score = 0

    # Followers check
    followers = user_data.get('followers', 0)
    if followers < 10:
        score += 0.3
    elif followers < 100:
        score += 0.1

    # Following/follower ratio
    following = user_data.get('following', 0)
    if followers > 0 and following / (followers + 1) > 50:
        score += 0.3

    # Username pattern
    username = user_data.get('username', '')
    if re.match(BOT_USERNAME_PATTERN, username):
        score += 0.4

    # Default profile indicators
    if not user_data.get('bio'):
        score += 0.1
    if not user_data.get('profile_image_custom'):
        score += 0.1

    return min(score, 1.0)

# ============================================================================
# YALE ENGAGEMENT COEFFICIENT
# ============================================================================

def calculate_influence_weight(user_data, engagement_data, use_bot_penalty=True):
    """Calculate normalized influence weight (0-1 scale) using Yale engagement coefficient

    Based on Yale research: "Social Media Engagement and Cryptocurrency Performance"
    - Optimal engagement: 0.0001 to 0.001 = highest returns (~200% in study)
    - Too low (< 0.00001): no real interest
    - Too high (> 0.001): likely bot manipulation

    Args:
        user_data: dict with 'followers' key
        engagement_data: dict with 'likes', 'retweets' keys
        use_bot_penalty: Apply bot probability penalty (default True)

    Returns:
        float: 0.0 (no influence) to 1.0 (maximum influence)
    """
    followers = user_data.get('followers', 0)
    retweets = engagement_data.get('retweets', 0)
    likes = engagement_data.get('likes', 0)

    # Yale formula: Retweets weighted at 0.31x (require more effort than likes)
    # Interaction coefficients from research: likes=1.0, retweets=0.31, replies=0.19
    weighted_engagement = (likes * 1.0) + (retweets * 0.31)

    # Calculate engagement coefficient (normalized by follower count)
    engagement_coef = weighted_engagement / (followers + 1)

    # Map to 0-1 scale based on Yale optimal thresholds
    if engagement_coef < 0.00001:
        base_weight = 0.0
    elif engagement_coef < 0.0001:
        base_weight = engagement_coef / 0.0001
    elif engagement_coef <= 0.001:
        base_weight = 1.0
    elif engagement_coef <= 0.01:
        excess = (engagement_coef - 0.001) / 0.009
        base_weight = 1.0 - (excess * 0.7)
    else:
        base_weight = 0.1

    # Apply bot probability penalty if requested
    if use_bot_penalty:
        bot_prob = calculate_bot_probability(user_data)
        bot_mult = 1.0 - (bot_prob * 0.8)
        final_weight = base_weight * bot_mult
    else:
        final_weight = base_weight

    return max(0.0, min(1.0, final_weight))

# ============================================================================
# PUMP PATTERN DETECTION
# ============================================================================

def detect_pump_pattern(tweets_batch, spam_keywords=SPAM_KEYWORDS):
    """Detect coordinated pump patterns in batch of tweets

    Args:
        tweets_batch: List of tweet dicts with 'text', 'followers' keys
        spam_keywords: List of spam keywords to check for

    Returns:
        float: 0.0 (no pump) to 1.0 (definite pump)
    """
    if len(tweets_batch) < 10:
        return 0

    indicators = 0

    # Check text similarity
    texts = [t['text'].lower() for t in tweets_batch]
    unique_texts = set(texts)
    if len(unique_texts) / len(texts) < 0.3:
        indicators += 0.3

    # Check for new accounts
    new_accounts = sum(1 for t in tweets_batch if t.get('followers', 0) < 100)
    if new_accounts / len(tweets_batch) > 0.6:
        indicators += 0.3

    # Check for spam keywords concentration
    spam_count = sum(1 for t in tweets_batch
                    if any(spam in t['text'].lower() for spam in spam_keywords))
    if spam_count / len(tweets_batch) > 0.5:
        indicators += 0.4

    return min(indicators, 1.0)

# ============================================================================
# TWITTER CLIENT INITIALIZATION
# ============================================================================

def init_twitter_client(cookies_path="cookies/cookies.json"):
    """Initialize twikit client with cookies

    Args:
        cookies_path: Path to cookies.json file

    Returns:
        Client: Configured twikit Client instance

    Raises:
        SystemExit: If cookies not found or initialization fails
    """
    from twikit import Client

    if not os.path.exists(cookies_path):
        print(f"[ERROR] {cookies_path} not found!")
        print(f"Please ensure {cookies_path} exists with Twitter auth tokens")
        sys.exit(1)

    try:
        client = Client('en-US')

        # Load cookies
        with open(cookies_path, 'r') as f:
            cookie_data = json.load(f)

        # Handle browser export format if needed
        if isinstance(cookie_data, dict) and 'cookies' in cookie_data:
            cookies = cookie_data['cookies']
            with open(cookies_path, 'w') as f:
                json.dump(cookies, f)

        client.load_cookies(cookies_path)
        print("[OK] Twitter client initialized")
        return client

    except Exception as e:
        print(f"[ERROR] Twitter client init failed: {e}")
        sys.exit(1)

def _acquire_single_account_lock(cookies_path, timeout=120):
    """
    Acquire lock for single-account mode cookie refresh

    Args:
        cookies_path: Path to cookies.json
        timeout: Max seconds to wait

    Returns:
        tuple: (acquired: bool, should_refresh: bool)
    """
    import time
    lock_file = Path(str(cookies_path) + ".lock")
    start_time = time.time()

    while True:
        if not lock_file.exists():
            try:
                lock_file.write_text(f"{os.getpid()}\n{datetime.now().isoformat()}")
                time.sleep(0.1)
                if lock_file.exists():
                    content = lock_file.read_text().strip()
                    if content.startswith(str(os.getpid())):
                        return (True, True)
            except:
                pass

        # Check for stale lock
        try:
            if lock_file.exists():
                content = lock_file.read_text().strip()
                lines = content.split('\n')
                if len(lines) >= 2:
                    lock_time = datetime.fromisoformat(lines[1])
                    age = (datetime.now() - lock_time).total_seconds()
                    if age > 120:
                        print(f"[Cookie Lock] Stale lock detected, removing...")
                        lock_file.unlink()
                        continue
        except:
            pass

        elapsed = time.time() - start_time
        if elapsed > timeout:
            print(f"[Cookie Lock] Timeout waiting for lock")
            return (False, False)

        print(f"[Cookie Lock] Waiting for another process to refresh... ({elapsed:.0f}s)")
        time.sleep(5)

def _release_single_account_lock(cookies_path):
    """Release single-account lock"""
    lock_file = Path(str(cookies_path) + ".lock")
    try:
        if lock_file.exists():
            lock_file.unlink()
    except:
        pass

def auto_refresh_cookies(client, cookies_path="cookies/cookies.json"):
    """Refresh cookies by extracting them from Chrome and creating a fresh client

    IMPORTANT: If using account pool, automatically detects which account and refreshes
    the correct account's cookies. Falls back to single-account mode if pool not available.

    Args:
        client: twikit Client instance (will be replaced with fresh instance)
        cookies_path: Path to save refreshed cookies (only used in single-account mode)

    Returns:
        Client or None: New twikit Client with fresh cookies, or None if failed
    """
    import time
    from twikit import Client
    from dotenv import load_dotenv
    orchestrator_mode = os.getenv('ORCHESTRATOR_RUNNING', 'false').lower() == 'true'
    max_attempts = int(os.getenv('TWITTER_COOKIE_REFRESH_RETRIES', 10))
    headless_cutover = max(max_attempts - 3, 0)

    def should_use_headless(attempt):
        if orchestrator_mode:
            return False  # Always show Chrome window when orchestrated
        return attempt <= headless_cutover if headless_cutover > 0 else False

    # Check if this client is from the account pool
    try:
        from nice_funcs.twitter_account_pool import account_pool

        account_num = account_pool.get_account_num(client)

        if account_num is not None:
            # This is a pooled account - refresh it properly
            print(f"[AUTO-REFRESH] Detected Account {account_num} needs refresh")
            print(f"[AUTO-REFRESH] Please ensure Account {account_num} is logged into Chrome" if not orchestrator_mode else "[AUTO-REFRESH] Headless refresh requested")
            print(f"[AUTO-REFRESH] Extracting fresh cookies...")

            success = account_pool.refresh_account(account_num, max_attempts=max_attempts)

            if success:
                # Get the refreshed client from the pool
                for acc in account_pool.clients:
                    if acc['account_num'] == account_num:
                        print(f"[AUTO-REFRESH] ✓ Account {account_num} refreshed successfully!")
                        return acc['client']
            else:
                print(f"[AUTO-REFRESH] ✗ Failed to refresh Account {account_num}")
                print(f"[AUTO-REFRESH] ✗ Make sure Account {account_num} is logged into Chrome")
                print(f"[AUTO-REFRESH] ✗ Or manually run: python scripts/setup_account_cookies.py --account {account_num}")
                return None

    except ImportError:
        # Account pool not available - use single-account mode
        pass
    except Exception as e:
        print(f"[AUTO-REFRESH] Pool check failed: {e}, falling back to single-account mode")

    # Single-account mode (fallback) with locking
    print(f"[AUTO-REFRESH] Using single-account mode")

    # Load credentials from .env
    load_dotenv(override=True)
    account_email = os.getenv('TWITTER_ACCOUNT1_EMAIL')
    account_password = os.getenv('TWITTER_PASSWORD')
    account_username = os.getenv('TWITTER_ACCOUNT1_USERNAME')

    print(f"[AUTO-REFRESH] Credentials loaded:")
    print(f"[AUTO-REFRESH]   Email: {account_email}")
    print(f"[AUTO-REFRESH]   Username: {account_username}")
    print(f"[AUTO-REFRESH]   Password: {'SET' if account_password else 'NOT SET'}")

    cookies_path = Path(cookies_path)
    prev_mtime = None
    if cookies_path.exists():
        try:
            prev_mtime = cookies_path.stat().st_mtime
        except OSError:
            prev_mtime = None
    acquired, should_refresh = _acquire_single_account_lock(cookies_path, timeout=180)

    try:
        if not acquired and not should_refresh:
            print(f"[AUTO-REFRESH] ✗ Timeout waiting for cookie refresh lock. Will retry.")
            return None

        if should_refresh:
            # We got the lock - do the refresh
            print(f"[AUTO-REFRESH] [LOCK ACQUIRED] This process will refresh cookies")
            print(f"[AUTO-REFRESH] Using credentials for: {account_email}")

            cookies = None
            for attempt in range(1, max_attempts + 1):
                use_headless = should_use_headless(attempt)
                mode_label = "headless" if use_headless else "interactive"
                print(f"[AUTO-REFRESH] Attempt {attempt}/{max_attempts} ({mode_label})")

                # Use the enhanced refresh (with SeleniumBase for Cloudflare)
                cookies = refresh_cookies(
                    headless=use_headless,
                    account_email=account_email,
                    account_password=account_password,
                    account_username=account_username
                )
                if cookies:
                    print(f"[AUTO-REFRESH] ✓ Enhanced refresh successful")

                if cookies:
                    break

                wait_seconds = min(5 * attempt, 30)
                print(f"[AUTO-REFRESH] Attempt {attempt} failed. Retrying in {wait_seconds}s...")
                time.sleep(wait_seconds)

            if not cookies:
                print(f"[AUTO-REFRESH] ✗ Failed to extract cookies after {max_attempts} attempts")
                return None

            if not save_cookies(cookies):
                print(f"[AUTO-REFRESH] ✗ Failed to save cookies")
                return None

            try:
                new_mtime = cookies_path.stat().st_mtime
            except OSError:
                new_mtime = None
            if new_mtime and prev_mtime and new_mtime == prev_mtime:
                print(f"[AUTO-REFRESH] ⚠ Cookie file timestamp did not change - verify refresh succeeded")
            else:
                print(f"[AUTO-REFRESH] ✓ Cookies saved")
        else:
            # Another process refreshed - just reload
            print(f"[AUTO-REFRESH] [WAIT COMPLETE] Another process refreshed, reloading...")

        # Create new client with fresh cookies (either we just saved them, or another process did)
        new_client = Client('en-US')
        if not cookies_path.exists():
            print(f"[AUTO-REFRESH] ✗ Cookie file not found at {cookies_path}")
            return None

        new_client.load_cookies(str(cookies_path))
        time.sleep(2)

        print(f"[AUTO-REFRESH] ✓ New client created successfully!")
        return new_client

    except Exception as e:
        print(f"[AUTO-REFRESH] ✗ Error: {e}")
        return None

    finally:
        if acquired:
            _release_single_account_lock(cookies_path)
            print(f"[AUTO-REFRESH] [LOCK RELEASED]")

def get_pooled_client():
    """Get a Twitter client from the account pool (with fallback to single account)

    This function tries to use the multi-account pool for rate limit avoidance.
    If the pool is not available, it falls back to single-account mode.

    Returns:
        Client: TwiKit Client instance
    """
    try:
        from nice_funcs.twitter_account_pool import account_pool

        # Try to get client from pool
        client = account_pool.get_client()

        if client:
            return client

        # Pool returned None - fall back to single account
        print("[Client Init] Pool unavailable, using single-account mode")
        return init_twitter_client()

    except Exception as e:
        # Account pool not available or failed - use single account
        print(f"[Client Init] Account pool not available: {e}")
        print("[Client Init] Using single-account mode")
        return init_twitter_client()

# ============================================================================
# DATABASE HELPERS
# ============================================================================

# Global connection pool (one per process)
_connection_pool = None

class DatabaseConnectionPool:
    """
    Simple connection pool wrapper for PostgreSQL
    Provides automatic reconnection and connection reuse
    """
    def __init__(self, host, port, database, user, password, minconn=1, maxconn=5):
        """
        Initialize connection pool

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            minconn: Minimum connections to maintain
            maxconn: Maximum connections allowed
        """
        try:
            self.pool = pool.SimpleConnectionPool(
                minconn,
                maxconn,
                host=host,
                port=port,
                database=database,
                user=user,
                password=password
            )
            print(f"[OK] Database connection pool created ({minconn}-{maxconn} connections)")
        except Exception as e:
            print(f"[ERROR] Failed to create connection pool: {e}")
            sys.exit(1)

    def get_connection(self):
        """
        Get a connection from the pool

        Returns:
            psycopg2.connection: Database connection
        """
        try:
            return self.pool.getconn()
        except Exception as e:
            print(f"[ERROR] Failed to get connection from pool: {e}")
            return None

    def return_connection(self, conn):
        """
        Return a connection to the pool

        Args:
            conn: Connection to return
        """
        if conn:
            try:
                self.pool.putconn(conn)
            except Exception as e:
                print(f"[WARNING] Failed to return connection to pool: {e}")

    def close_all(self):
        """Close all connections in the pool"""
        if self.pool:
            self.pool.closeall()


def init_db_pool(host, port, database, user, password):
    """
    Initialize the global database connection pool
    Call this once at scraper startup

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        password: Database password

    Returns:
        DatabaseConnectionPool: The connection pool instance
    """
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = DatabaseConnectionPool(host, port, database, user, password)
    return _connection_pool


def get_db_connection(host, port, database, user, password):
    """
    Create or get the database connection pool

    IMPORTANT: Now returns a connection pool instead of a single connection.
    Use pool.get_connection() / pool.return_connection() for operations.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        password: Database password

    Returns:
        DatabaseConnectionPool: Connection pool instance

    Raises:
        SystemExit: If pool creation fails
    """
    # Initialize pool if not already created
    return init_db_pool(host, port, database, user, password)

# ============================================================================
# VOLUME SPIKE CALCULATION
# ============================================================================

def calculate_volume_spike(volume_baseline_dict, token, current_count):
    """Calculate if there's a volume spike (PRIMARY SIGNAL)

    Updates baseline with exponential moving average and returns spike ratio.
    Used by token-based scrapers to detect unusual tweet volume.

    Args:
        volume_baseline_dict: Dict with token baselines, e.g. {'BTC': {'count': 20.0}}
        token: Token symbol (e.g., 'BTC', 'PEPE')
        current_count: Current tweet count for this cycle

    Returns:
        float: Spike ratio (e.g., 2.5 = 2.5x normal volume)
    """
    baseline = float(volume_baseline_dict[token]['count'] or 20.0)
    current = float(current_count)
    spike_ratio = current / (baseline + 1.0)

    # Update baseline with exponential moving average
    alpha = 0.1  # Smoothing factor
    volume_baseline_dict[token]['count'] = (
        alpha * current + (1.0 - alpha) * baseline
    )

    return spike_ratio

# ============================================================================
# VELOCITY TRACKING
# ============================================================================

def calculate_token_velocity_metrics(sentiment_history_dict, token, current_sentiment, current_volume_spike):
    """Calculate sentiment velocity and volume acceleration for token-based scrapers

    Measures rate of change per minute for sentiment and volume.
    Used to detect rapid momentum shifts 10-15 minutes earlier than traditional signals.

    Args:
        sentiment_history_dict: Dict storing last 3 cycles per token
        token: Token symbol
        current_sentiment: Current average sentiment score
        current_volume_spike: Current volume spike ratio

    Returns:
        dict or None: {
            'sentiment_velocity': float,  # Change in sentiment per minute
            'volume_acceleration': float, # Change in volume spike per minute
            'momentum': float,            # sentiment_velocity × volume_acceleration
            'prev_sentiment': float,
            'prev_volume_spike': float,
            'time_delta': float
        }
    """
    history = sentiment_history_dict[token]

    # Need at least one previous cycle to calculate velocity
    if not history:
        return None

    prev_cycle = history[-1]
    time_delta = (datetime.now() - prev_cycle['time']).total_seconds() / 60.0  # Minutes

    if time_delta < 1:  # Avoid division by very small numbers
        return None

    # Calculate rates of change per minute
    sentiment_velocity = (current_sentiment - prev_cycle['sentiment']) / time_delta
    volume_acceleration = (current_volume_spike - prev_cycle['volume_spike']) / time_delta

    # Momentum score: both metrics moving up together
    momentum = sentiment_velocity * volume_acceleration

    return {
        'sentiment_velocity': sentiment_velocity,
        'volume_acceleration': volume_acceleration,
        'momentum': momentum,
        'prev_sentiment': prev_cycle['sentiment'],
        'prev_volume_spike': prev_cycle['volume_spike'],
        'time_delta': time_delta
    }

def calculate_whale_velocity_metrics(sentiment_history_dict, token, current_sentiment, current_tweet_count):
    """Calculate sentiment velocity for whale account tracking

    Similar to token velocity but tracks tweet count instead of volume spike ratio.

    Args:
        sentiment_history_dict: Dict storing last 3 cycles per token
        token: Token symbol
        current_sentiment: Current average sentiment from whale tweets
        current_tweet_count: Number of whale tweets mentioning this token

    Returns:
        dict or None: {
            'sentiment_velocity': float,
            'volume_change': float,
            'momentum': float,
            'prev_sentiment': float,
            'prev_tweet_count': int,
            'time_delta': float
        }
    """
    history = sentiment_history_dict[token]

    if not history:
        return None

    prev_cycle = history[-1]
    time_delta = (datetime.now() - prev_cycle['time']).total_seconds() / 60.0

    if time_delta < 1:
        return None

    # Calculate rates of change per minute
    sentiment_velocity = (current_sentiment - prev_cycle['sentiment']) / time_delta
    volume_change = (current_tweet_count - prev_cycle['tweet_count']) / time_delta

    # Momentum score: both metrics moving up together
    momentum = sentiment_velocity * volume_change

    return {
        'sentiment_velocity': sentiment_velocity,
        'volume_change': volume_change,
        'momentum': momentum,
        'prev_sentiment': prev_cycle['sentiment'],
        'prev_tweet_count': prev_cycle['tweet_count'],
        'time_delta': time_delta
    }

def update_token_sentiment_history(sentiment_history_dict, token, sentiment, volume_spike):
    """Store current cycle data for token-based velocity tracking

    Args:
        sentiment_history_dict: defaultdict(list) storing history per token
        token: Token symbol
        sentiment: Current average sentiment
        volume_spike: Current volume spike ratio

    Returns:
        None (modifies sentiment_history_dict in place)
    """
    sentiment_history_dict[token].append({
        'time': datetime.now(),
        'sentiment': sentiment,
        'volume_spike': volume_spike
    })

    # Keep only last 3 cycles
    if len(sentiment_history_dict[token]) > 3:
        sentiment_history_dict[token] = sentiment_history_dict[token][-3:]

def update_whale_sentiment_history(sentiment_history_dict, token, sentiment, tweet_count):
    """Store current cycle data for whale velocity tracking

    Args:
        sentiment_history_dict: defaultdict(list) storing history per token
        token: Token symbol
        sentiment: Current average sentiment from whale tweets
        tweet_count: Number of whale tweets mentioning token

    Returns:
        None (modifies sentiment_history_dict in place)
    """
    sentiment_history_dict[token].append({
        'time': datetime.now(),
        'sentiment': sentiment,
        'tweet_count': tweet_count
    })

    # Keep only last 3 cycles
    if len(sentiment_history_dict[token]) > 3:
        sentiment_history_dict[token] = sentiment_history_dict[token][-3:]


def validate_sentiment_data(sentiment_score, bot_probability, pump_score,
                            influence_weight, volume_spike, token=None):
    """Validate and clamp sentiment-related metrics to valid ranges

    This function ensures all sentiment data is within valid bounds before
    inserting to database. Uses lenient approach: clamps out-of-range values
    instead of rejecting them, and logs warnings for transparency.

    Args:
        sentiment_score: VADER sentiment score (should be -1.0 to 1.0)
        bot_probability: Bot detection score (should be 0.0 to 1.0)
        pump_score: Pump pattern score (should be 0.0 to 1.0)
        influence_weight: Yale engagement coefficient (should be 0.0 to 1.0)
        volume_spike: Volume spike ratio (should be >= 0.0)
        token: Optional token name for logging

    Returns:
        dict: Validated values with all metrics clamped to valid ranges
    """
    validated = {}
    token_label = f"[{token}] " if token else ""

    # Validate sentiment_score (-1.0 to 1.0)
    if sentiment_score < -1.0 or sentiment_score > 1.0:
        print(f"[WARNING] {token_label}Sentiment score {sentiment_score:.4f} out of range, clamping to [-1, 1]")
        validated['sentiment_score'] = max(-1.0, min(1.0, sentiment_score))
    else:
        validated['sentiment_score'] = sentiment_score

    # Validate bot_probability (0.0 to 1.0)
    if bot_probability < 0.0 or bot_probability > 1.0:
        print(f"[WARNING] {token_label}Bot probability {bot_probability:.4f} out of range, clamping to [0, 1]")
        validated['bot_probability'] = max(0.0, min(1.0, bot_probability))
    else:
        validated['bot_probability'] = bot_probability

    # Validate pump_score (0.0 to 1.0)
    if pump_score < 0.0 or pump_score > 1.0:
        print(f"[WARNING] {token_label}Pump score {pump_score:.4f} out of range, clamping to [0, 1]")
        validated['pump_score'] = max(0.0, min(1.0, pump_score))
    else:
        validated['pump_score'] = pump_score

    # Validate influence_weight (0.0 to 1.0)
    if influence_weight < 0.0 or influence_weight > 1.0:
        print(f"[WARNING] {token_label}Influence weight {influence_weight:.4f} out of range, clamping to [0, 1]")
        validated['influence_weight'] = max(0.0, min(1.0, influence_weight))
    else:
        validated['influence_weight'] = influence_weight

    # Validate volume_spike (>= 0.0)
    if volume_spike < 0.0:
        print(f"[WARNING] {token_label}Volume spike {volume_spike:.2f} is negative, setting to 0.0")
        validated['volume_spike'] = 0.0
    else:
        validated['volume_spike'] = volume_spike

    return validated
