"""
Shared Twitter Scraping Functions
Used by all Twitter scrapers in crypto_scrapers/
Includes: VADER setup, bot detection, Yale coefficient, client initialization
"""

import os
import sys
import json
import psycopg2
import httpx
import re
from random import randint
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pathlib import Path

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

def init_twitter_client(cookies_path="cookies.json"):
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

def auto_refresh_cookies(client, cookies_path="cookies.json"):
    """Refresh cookies by extracting them from Firefox and creating a fresh client

    IMPORTANT: Creates a completely new client instance to clear any cached state.
    The calling code should handle retry logic if this fails.

    Args:
        client: twikit Client instance (will be replaced with fresh instance)
        cookies_path: Path to save refreshed cookies

    Returns:
        Client or None: New twikit Client with fresh cookies, or None if failed
    """
    import time
    from twikit import Client

    try:
        cookies = refresh_cookies(headless=False)
        if cookies and save_cookies(cookies):
            # CRITICAL: Create a completely new client instance to avoid cached state
            print(f"[AUTO-REFRESH] ✓ Cookies saved, creating fresh client instance...")
            new_client = Client('en-US')
            new_client.load_cookies(cookies_path)

            # Wait a moment for session to stabilize
            time.sleep(2)

            print(f"[AUTO-REFRESH] ✓ New client created successfully!")
            return new_client
        else:
            print(f"[AUTO-REFRESH] ✗ Failed to extract/save cookies")
            return None
    except Exception as e:
        print(f"[AUTO-REFRESH] ✗ Error: {e}")
        return None

# ============================================================================
# DATABASE HELPERS
# ============================================================================

def get_db_connection(host, port, database, user, password):
    """Create PostgreSQL database connection

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        password: Database password

    Returns:
        psycopg2.connection: Database connection

    Raises:
        SystemExit: If connection fails
    """
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        print("[OK] Database connected")
        return conn
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        sys.exit(1)

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
