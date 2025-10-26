"""
Twitter Sentiment Scraper
Tracks crypto sentiment with volume tracking and bot filtering
"""

import os
import sys
import asyncio
import time
import json
import psycopg2
from datetime import datetime, timedelta
from pathlib import Path
from random import randint
from dotenv import load_dotenv
import httpx
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import numpy as np
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from monitors.health_monitor import HealthMonitor
from monitors.refresh_cookies import refresh_cookies, save_cookies

# Patch httpx for twikit
original_client = httpx.Client

def patched_client(*args, **kwargs):
    if 'headers' not in kwargs:
        kwargs['headers'] = {}

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]

    kwargs['headers'].update({
        'User-Agent': user_agents[randint(0, len(user_agents)-1)],
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    })

    kwargs.pop('proxy', None)
    return original_client(*args, **kwargs)

httpx.Client = patched_client

from twikit import Client, TooManyRequests

# Optimized token list - focus on TOP meme coins with proven Twitter sensitivity
# Fewer tokens = deeper coverage = better whale detection (95%+ vs 40%)
TOKENS_TO_TRACK = [
    "PEPE",   # Massive Twitter community, high liquidity
    "DOGE",   # Elon tweets move it instantly
    "SHIB",   # Large community, responds to sentiment
    "BONK",   # Active Solana community
    "WIF"     # Newer, high volatility, Twitter-sensitive
]

# Use BTC only as market indicator, not trade target
MARKET_INDICATORS = ["BITCOIN"]  # Uppercase for consistency

TWEETS_PER_TOKEN = 30  # 5 tokens × 30 tweets = ~30 searches (60% rate limit usage)
POLLING_INTERVAL = 5 * 60  # 5 minutes (optimal for signal freshness)

# Enhanced spam/bot filtering
SPAM_KEYWORDS = [
    'discord', 'telegram', 'airdrop', 'giveaway', 'free tokens',
    'DM me', 'click here', 'join now', '100x guaranteed',
    'presale', 'whitelist', 'mint now'
]

# Bot pattern detection
BOT_USERNAME_PATTERN = r'^[a-zA-Z]{7,8}\d{8}$'  # Common bot pattern

# Database config
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

class TwitterSentiment:
    def __init__(self):
        self.client = None
        self.vader = None
        self.db_conn = None
        self.volume_baseline = defaultdict(lambda: {'count': 20.0, 'history': []})
        self.last_poll_time = defaultdict(lambda: datetime.now() - timedelta(hours=1))
        self.health = HealthMonitor('twitter_sentiment', alert_threshold=3)
        self.cookies_refreshed = False  # Track if we already tried refreshing this cycle

        # Velocity tracking - stores last 3 cycles per token
        self.sentiment_history = defaultdict(list)  # {token: [{'time': ..., 'sentiment': ..., 'volume_spike': ...}]}
        self.cycle_interval = POLLING_INTERVAL / 60.0  # Convert to minutes for velocity calc

    def init_db(self):
        try:
            self.db_conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            print("[OK] Database connected")
            self.load_volume_baseline()
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            sys.exit(1)

    def load_volume_baseline(self):
        """Load historical volume data for baseline calculations"""
        cursor = self.db_conn.cursor()
        try:
            cursor.execute("""
                SELECT token, AVG(tweet_count) as avg_volume
                FROM (
                    SELECT token,
                           DATE_TRUNC('hour', scraped_at) as hour,
                           COUNT(*) as tweet_count
                    FROM twitter_sentiment
                    WHERE scraped_at > NOW() - INTERVAL '24 hours'
                    GROUP BY token, hour
                ) as hourly_counts
                GROUP BY token
            """)

            for token, avg_volume in cursor.fetchall():
                # Convert Decimal to float to avoid type errors
                self.volume_baseline[token]['count'] = float(avg_volume) if avg_volume else 20.0
        except:
            # Table might not have volume data yet
            pass
        finally:
            cursor.close()

    def init_vader(self):
        """Initialize VADER with comprehensive crypto-specific lexicon (150+ terms)

        Based on research:
        - GitHub PR #81 (community-validated crypto terms)
        - Academic research (800-word crypto market lexicon)
        - 2025 Crypto Twitter slang & meme coin culture
        - Technical analysis & trading terminology
        """
        self.vader = SentimentIntensityAnalyzer()

        # Comprehensive crypto lexicon with sentiment scores (-4 to +4 scale)
        crypto_lexicon = {
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

        self.vader.lexicon.update(crypto_lexicon)
        print(f"[OK] Sentiment analyzer initialized with {len(crypto_lexicon)} crypto terms")
        print("[OK] Lexicon covers: bullish/bearish, meme slang, TA, scam signals")

    def calculate_bot_probability(self, user_data):
        """Calculate probability that an account is a bot"""
        score = 0

        # Account age (if available from user object)
        # Followers
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
        import re
        username = user_data.get('username', '')
        if re.match(BOT_USERNAME_PATTERN, username):
            score += 0.4

        # Default profile indicators
        if not user_data.get('bio'):
            score += 0.1
        if not user_data.get('profile_image_custom'):
            score += 0.1

        return min(score, 1.0)

    def calculate_influence_weight(self, user_data, engagement_data):
        """Calculate normalized influence weight (0-1 scale) using Yale engagement coefficient

        Based on Yale research: "Social Media Engagement and Cryptocurrency Performance"
        - Optimal engagement: 0.0001 to 0.001 = highest returns (~200% in study)
        - Too low (< 0.00001): no real interest
        - Too high (> 0.001): likely bot manipulation

        Returns:
            float: 0.0 (no influence) to 1.0 (maximum influence)
        """
        followers = user_data.get('followers', 0)
        retweets = engagement_data.get('retweets', 0)
        likes = engagement_data.get('likes', 0)

        # Yale formula: Retweets are weighted at 0.31x (require more effort than likes)
        # Interaction coefficients from research: likes=1.0, retweets=0.31, replies=0.19
        weighted_engagement = (likes * 1.0) + (retweets * 0.31)

        # Calculate engagement coefficient (normalized by follower count)
        engagement_coef = weighted_engagement / (followers + 1)

        # Map to 0-1 scale based on Yale optimal thresholds
        if engagement_coef < 0.00001:
            # Too low - no real interest
            base_weight = 0.0
        elif engagement_coef < 0.0001:
            # Below optimal - scale from 0.0 to 1.0
            base_weight = engagement_coef / 0.0001
        elif engagement_coef <= 0.001:
            # OPTIMAL RANGE - maximum weight
            base_weight = 1.0
        elif engagement_coef <= 0.01:
            # Above optimal - potential bot activity, decrease weight
            # Scale from 1.0 down to 0.3
            excess = (engagement_coef - 0.001) / 0.009
            base_weight = 1.0 - (excess * 0.7)
        else:
            # Very high (> 0.01) - likely bot swarm, minimal weight
            base_weight = 0.1

        # Apply bot probability penalty
        bot_prob = self.calculate_bot_probability(user_data)
        bot_mult = 1.0 - (bot_prob * 0.8)  # Reduce weight by up to 80% for bots

        # Final normalized weight (0-1 scale)
        final_weight = base_weight * bot_mult

        return max(0.0, min(1.0, final_weight))  # Ensure stays in 0-1 range

    def detect_pump_pattern(self, tweets_batch):
        """Detect coordinated pump patterns"""
        if len(tweets_batch) < 10:
            return 0

        indicators = 0

        # Check text similarity
        texts = [t['text'].lower() for t in tweets_batch]
        unique_texts = set(texts)
        if len(unique_texts) / len(texts) < 0.3:  # 70%+ similar
            indicators += 0.3

        # Check for new accounts
        new_accounts = sum(1 for t in tweets_batch
                          if t.get('followers', 0) < 100)
        if new_accounts / len(tweets_batch) > 0.6:
            indicators += 0.3

        # Check for spam keywords concentration
        spam_count = sum(1 for t in tweets_batch
                        if any(spam in t['text'].lower() for spam in SPAM_KEYWORDS))
        if spam_count / len(tweets_batch) > 0.5:
            indicators += 0.4

        return min(indicators, 1.0)

    def analyze_sentiment_vader(self, text):
        """Fast VADER sentiment analysis"""
        scores = self.vader.polarity_scores(text)
        # Return compound score (-1 to 1)
        return scores['compound']

    def calculate_volume_spike(self, token, current_count):
        """Calculate if there's a volume spike (PRIMARY SIGNAL)"""
        baseline = float(self.volume_baseline[token]['count'] or 20.0)
        current = float(current_count)
        spike_ratio = current / (baseline + 1.0)

        # Update baseline with exponential moving average
        alpha = 0.1  # Smoothing factor
        self.volume_baseline[token]['count'] = (
            alpha * current + (1.0 - alpha) * baseline
        )

        return spike_ratio

    def calculate_velocity_metrics(self, token, current_sentiment, current_volume_spike):
        """Calculate sentiment velocity and volume acceleration"""
        history = self.sentiment_history[token]

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

    def update_sentiment_history(self, token, sentiment, volume_spike):
        """Store current cycle data and trim to last 3 cycles"""
        self.sentiment_history[token].append({
            'time': datetime.now(),
            'sentiment': sentiment,
            'volume_spike': volume_spike
        })

        # Keep only last 3 cycles
        if len(self.sentiment_history[token]) > 3:
            self.sentiment_history[token] = self.sentiment_history[token][-3:]

    def auto_refresh_cookies(self):
        """Automatically refresh cookies when they expire"""
        print("\n[AUTO-REFRESH] Cookies expired, refreshing...")
        try:
            cookies = refresh_cookies(headless=False)
            if cookies and save_cookies(cookies):
                print("[AUTO-REFRESH] Cookies refreshed successfully!")
                # Reload cookies into client
                self.client.load_cookies("cookies.json")
                self.cookies_refreshed = True
                return True
            else:
                print("[AUTO-REFRESH] Failed to refresh cookies")
                return False
        except Exception as e:
            print(f"[AUTO-REFRESH] Error: {e}")
            return False

    def init_twitter_client(self):
        """Initialize twikit client with cookies.json"""
        if not os.path.exists("cookies.json"):
            print("[ERROR] cookies.json not found!")
            print("Please ensure cookies.json exists with Twitter auth tokens")
            sys.exit(1)

        try:
            self.client = Client('en-US')

            # Load cookies
            with open("cookies.json", 'r') as f:
                cookie_data = json.load(f)

            # Handle browser export format if needed
            if isinstance(cookie_data, dict) and 'cookies' in cookie_data:
                cookies = cookie_data['cookies']
                with open("cookies.json", 'w') as f:
                    json.dump(cookies, f)

            self.client.load_cookies("cookies.json")
            print("[OK] Twitter client initialized")
        except Exception as e:
            print(f"[ERROR] Twitter client init failed: {e}")
            sys.exit(1)

    async def get_tweets_for_token(self, token):
        """Fetch tweets for a token with enhanced data"""
        collected = []

        try:
            search_term = f"${token}" if token.upper() in TOKENS_TO_TRACK else token
            print(f"\nSearching: {search_term}")
            time.sleep(randint(1, 3))  # Reduced delay for 5-min cycles

            tweets = await self.client.search_tweet(search_term, product='Latest')

            if tweets:
                for tweet in tweets:
                    if len(collected) >= TWEETS_PER_TOKEN:
                        break

                    # Enhanced spam filtering
                    text_lower = tweet.text.lower()
                    if any(spam in text_lower for spam in SPAM_KEYWORDS):
                        continue

                    user = tweet.user if hasattr(tweet, 'user') and tweet.user else None

                    tweet_data = {
                        'tweet_id': tweet.id,
                        'token': token.upper(),  # Always uppercase for consistency
                        'text': tweet.text,
                        'username': getattr(user, 'screen_name', 'unknown') if user else 'unknown',
                        'followers': getattr(user, 'followers_count', 0) if user else 0,
                        'following': getattr(user, 'following_count', getattr(user, 'friends_count', 0)) if user else 0,
                        'bio': getattr(user, 'description', None) if user else None,
                        'profile_image_custom': hasattr(user, 'profile_image_url') if user else False,
                        'retweets': getattr(tweet, 'retweet_count', 0) or 0,
                        'likes': getattr(tweet, 'favorite_count', 0) or 0,
                        'created_at': getattr(tweet, 'created_at', datetime.now()),
                        'timestamp': datetime.now()
                    }

                    collected.append(tweet_data)

            print(f"[OK] Collected {len(collected)} quality tweets for {token}")

        except TooManyRequests as e:
            # Handle rate limiting
            reset_time = datetime.fromtimestamp(e.rate_limit_reset)
            wait_seconds = (reset_time - datetime.now()).total_seconds() + randint(5, 10)
            print(f"Rate limited. Waiting {int(wait_seconds)}s...")
            time.sleep(wait_seconds)
        except Exception as e:
            error_msg = str(e).lower()
            # Auto-refresh cookies on authentication errors (404, unauthorized, etc.)
            if ('404' in error_msg or 'unauthorized' in error_msg or 'forbidden' in error_msg) and not self.cookies_refreshed:
                print(f"[WARN] Authentication error detected: {e}")
                if self.auto_refresh_cookies():
                    print(f"[RETRY] Retrying search for {token}...")
                    return await self.get_tweets_for_token(token)
            print(f"[ERROR] Failed to fetch {token}: {e}")

        return collected

    def save_to_db(self, all_tweets):
        """Save tweets with volume tracking and enhanced metrics"""
        if not all_tweets:
            return 0

        cursor = self.db_conn.cursor()

        # Group tweets by token for volume analysis
        by_token = defaultdict(list)
        for tweet in all_tweets:
            by_token[tweet['token']].append(tweet)

        saved = 0
        volume_alerts = []

        for token, tweets in by_token.items():
            # Calculate volume spike (PRIMARY SIGNAL)
            volume_spike = self.calculate_volume_spike(token, len(tweets))

            if volume_spike >= 2.0:  # 2x baseline = strong signal
                volume_alerts.append((token, volume_spike, len(tweets)))

            # Detect pump patterns
            pump_score = self.detect_pump_pattern(tweets)

            for tweet in tweets:
                # Analyze sentiment
                sentiment = self.analyze_sentiment_vader(tweet['text'])

                # Calculate influence-weighted score
                influence_weight = self.calculate_influence_weight(
                    {'followers': tweet['followers'],
                     'following': tweet['following'],
                     'username': tweet['username'],
                     'bio': tweet['bio'],
                     'profile_image_custom': tweet['profile_image_custom']},
                    {'retweets': tweet['retweets'], 'likes': tweet['likes']}
                )

                weighted_sentiment = sentiment * influence_weight

                # Bot probability
                bot_prob = self.calculate_bot_probability({
                    'followers': tweet['followers'],
                    'following': tweet['following'],
                    'username': tweet['username'],
                    'bio': tweet['bio'],
                    'profile_image_custom': tweet['profile_image_custom']
                })

                # Determine alert level
                if weighted_sentiment > 500 or (tweet['followers'] > 10_000_000 and abs(sentiment) > 0.5):
                    alert_level = "EXTREME"
                elif weighted_sentiment > 100 or (tweet['followers'] > 1_000_000 and abs(sentiment) > 0.6):
                    alert_level = "HIGH"
                elif weighted_sentiment > 50:
                    alert_level = "MEDIUM"
                elif weighted_sentiment > 10:
                    alert_level = "LOW"
                else:
                    alert_level = None

                try:
                    cursor.execute("""
                        INSERT INTO twitter_sentiment
                        (tweet_id, token, tweet_text, sentiment_score, sentiment_label,
                         author_username, author_followers, retweet_count, like_count,
                         tweet_created_at, scraped_at, weighted_score, alert_level,
                         is_whale, volume_spike, bot_probability, pump_score, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tweet_id, token) DO NOTHING
                    """, (
                        tweet['tweet_id'],
                        token,
                        tweet['text'],
                        round(sentiment, 4),
                        'positive' if sentiment > 0.1 else 'negative' if sentiment < -0.1 else 'neutral',
                        tweet['username'],
                        tweet['followers'],
                        tweet['retweets'],
                        tweet['likes'],
                        tweet['created_at'],
                        tweet['timestamp'],
                        round(weighted_sentiment, 4),
                        alert_level,
                        tweet['followers'] >= 100000,
                        round(volume_spike, 2),
                        round(bot_prob, 3),
                        round(pump_score, 3) if pump_score > 0.5 else None,
                        'general_search'  # Source identifier for general meme coin searches
                    ))

                    if cursor.rowcount > 0:
                        saved += 1

                except Exception as e:
                    self.db_conn.rollback()

        self.db_conn.commit()
        cursor.close()

        print(f"[OK] Saved {saved} new tweets")

        # VOLUME ALERTS (Primary trading signal!)
        if volume_alerts:
            print("\n" + "="*70)
            print("🚨 VOLUME SPIKE ALERTS (PRIMARY TRADING SIGNAL) 🚨")
            print("="*70)
            for token, spike, count in volume_alerts:
                signal = "STRONG BUY" if spike >= 3 else "BUY SIGNAL"
                print(f"{token}: {spike:.1f}x normal volume ({count} tweets) - {signal}")
            print("="*70)

        return saved

    async def run_cycle(self):
        """Run one collection cycle"""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting collection cycle")

        # Reset cookie refresh flag for this cycle
        self.cookies_refreshed = False

        all_tweets = []

        # Collect main tokens (meme coins with high Twitter sensitivity)
        for token in TOKENS_TO_TRACK:
            tweets = await self.get_tweets_for_token(token)
            all_tweets.extend(tweets)

        # Collect market indicators (BTC/ETH) with fewer tweets
        for token in MARKET_INDICATORS[:1]:  # Just BTC for market sentiment
            tweets = await self.get_tweets_for_token(token)
            all_tweets.extend(tweets[:5])  # Only 5 tweets for indicators

        # Save tweets and track health
        saved = 0
        if all_tweets:
            saved = self.save_to_db(all_tweets)

        self.health.record_cycle(saved)

        # Show cycle summary from collected tweets
        momentum_alerts = []
        if all_tweets:
            by_token = defaultdict(list)
            for tweet in all_tweets:
                by_token[tweet['token']].append(tweet)

            print("\nCycle Summary:")
            print(f"{'Token':<10} | {'Tweets':<8} | {'Human %':<10} | {'Avg Sent':<10}")
            print("-" * 50)

            for token in sorted(by_token.keys(), key=lambda t: len(by_token[t]), reverse=True):
                tweets = by_token[token]
                count = len(tweets)
                human_count = sum(1 for t in tweets if t.get('followers', 0) >= 10)  # Basic human filter
                human_pct = (human_count / count * 100) if count > 0 else 0

                # Calculate average sentiment from the actual tweets
                sentiments = []
                for tweet in tweets:
                    sent = self.analyze_sentiment_vader(tweet['text'])
                    sentiments.append(sent)
                avg_sent = sum(sentiments) / len(sentiments) if sentiments else 0

                print(f"{token:<10} | {count:<8} | {human_pct:>8.0f}% | {avg_sent:>9.3f}")

                # Calculate volume spike for velocity tracking
                baseline = float(self.volume_baseline[token]['count'] or 20.0)
                volume_spike = float(count) / (baseline + 1.0)

                velocity = self.calculate_velocity_metrics(token, avg_sent, volume_spike)

                if velocity:
                    # Check for significant momentum
                    if velocity['sentiment_velocity'] > 0.06 and velocity['volume_acceleration'] > 0.2:  # Per minute thresholds
                        momentum_alerts.append({
                            'token': token,
                            'velocity': velocity,
                            'current_sentiment': avg_sent,
                            'current_volume_spike': volume_spike
                        })

                # Update history for next cycle
                self.update_sentiment_history(token, avg_sent, volume_spike)

        else:
            print("\nNo tweets collected this cycle.")

        # Print momentum alerts
        if momentum_alerts:
            print("\n" + "="*70)
            print("🚀 MOMENTUM ALERTS (RAPID SENTIMENT CHANGE DETECTED)")
            print("="*70)
            for alert in sorted(momentum_alerts, key=lambda x: x['velocity']['momentum'], reverse=True):
                v = alert['velocity']
                print(f"\n{alert['token']}:")
                print(f"  Sentiment velocity: {v['sentiment_velocity']:+.3f}/min ({v['prev_sentiment']:.2f} → {alert['current_sentiment']:.2f})")
                print(f"  Volume acceleration: {v['volume_acceleration']:+.2f}/min ({v['prev_volume_spike']:.1f}x → {alert['current_volume_spike']:.1f}x)")
                print(f"  Momentum score: {v['momentum']:.3f}")

                # Classify signal strength
                if v['momentum'] > 0.05:
                    print(f"  Signal: 🔥 STRONG BUY - Rapid improvement detected!")
                elif v['momentum'] > 0.02:
                    print(f"  Signal: ⚡ MODERATE BUY - Sentiment accelerating")
                else:
                    print(f"  Signal: 📈 WATCH - Positive momentum building")
            print("="*70)

        # Health status
        self.health.print_health_summary()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Cycle completed")

    async def run(self):
        """Main loop - runs every 5 minutes"""
        print("\n" + "="*60)
        print("Twitter Sentiment Scraper")
        print("Volume Tracking + Bot Filtering")
        print("="*60)

        self.init_db()
        self.init_vader()
        self.init_twitter_client()

        while True:
            try:
                await self.run_cycle()

                print(f"\nNext cycle in {POLLING_INTERVAL//60} minutes...")
                await asyncio.sleep(POLLING_INTERVAL)

            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                break
            except Exception as e:
                print(f"[ERROR] Cycle failed: {e}")
                await asyncio.sleep(60)  # Wait 1 min on error

async def main():
    scraper = TwitterSentiment()
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(main())