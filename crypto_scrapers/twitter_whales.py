"""
Twitter Whale Tracker - Monitors specific high-signal accounts
Tracks known market movers, alpha callers, and insider accounts
Designed to catch every tweet from whitelisted accounts
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
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

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

# WHALE WATCHLIST - High-signal accounts that move markets
# These accounts have proven track records of early calls
# Can monitor up to 45 accounts without hitting rate limits
WHALE_ACCOUNTS = {
    # Alpha Callers - Known for early gem calls
    'blknoiz06': 'Alpha Caller (MOG, WIF)',
    'LarpVonTrier': 'Alpha Caller (KeyCat)',
    'artsch00lreject': 'Alpha Caller (PopCat)',
    'thecexoffender': 'Alpha Caller (Early gems)',
    'larpalt': 'Alpha Caller (Super early memes)',
    'iambroots': 'Trader (Early gems)',
    'UniswapVillain': 'Trader (Early gems)',
    'CrashiusClay69': 'Trader (Early gems)',

    # Insiders & Deployers
    'GamesMasterFlex': 'Insider (Dogwifhat organizer)',
    'degenharambe': 'Insider (PEPE founder alias)',

    # Flow Signals - Whale movements
    'DeBankDeFi': 'Flow Signal (Whale tracking)',
    'whale_alert': 'Flow Signal (Large transactions)',
    'nansen_ai': 'Analytics (Smart Money)',
}

# Tokens to specifically look for in whale tweets
PRIORITY_TOKENS = [
    'PEPE', 'DOGE', 'SHIB', 'BONK', 'WIF', 'TURBO', 'FLOKI',
    'MOG', 'KEYCAT', 'POPCAT', 'MYRA', 'OMNOM', 'WELSH',
    'BTC', 'ETH', 'SOL'
]

TWEETS_PER_WHALE = 20  # Get last 20 tweets from each whale
POLLING_INTERVAL = 10 * 60  # 10 minutes (different from main scraper)

# Database config
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

class WhaleTracker:
    def __init__(self):
        self.client = None
        self.vader = None
        self.db_conn = None
        self.last_tweet_ids = defaultdict(str)  # Track last seen tweet per whale

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
            self.load_last_tweets()
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            sys.exit(1)

    def load_last_tweets(self):
        """Load last seen tweet IDs to avoid duplicates"""
        cursor = self.db_conn.cursor()
        try:
            cursor.execute("""
                SELECT DISTINCT ON (author_username)
                    author_username, tweet_id
                FROM twitter_sentiment
                WHERE source = 'whale_tracker'
                    AND author_username = ANY(%s)
                ORDER BY author_username, scraped_at DESC
            """, (list(WHALE_ACCOUNTS.keys()),))

            for username, tweet_id in cursor.fetchall():
                self.last_tweet_ids[username] = tweet_id
        except:
            pass  # Table might not have data yet
        finally:
            cursor.close()

    def init_vader(self):
        """Initialize VADER with crypto-specific lexicon"""
        self.vader = SentimentIntensityAnalyzer()

        # Add crypto-specific terms
        crypto_lexicon = {
            'moon': 0.4, 'mooning': 0.5, 'moonshot': 0.4,
            'lambo': 0.3, 'rocket': 0.3, 'pump': 0.4,
            'bullish': 0.4, 'hodl': 0.2, 'diamond hands': 0.3,
            'lfg': 0.3, 'wagmi': 0.3, 'gm': 0.1,
            'rekt': -0.5, 'dump': -0.5, 'rug': -0.8,
            'rugpull': -0.8, 'scam': -0.7, 'crash': -0.6,
            'bearish': -0.4, 'paper hands': -0.3, 'ngmi': -0.3,
            # Add token-specific sentiment
            'gem': 0.5, 'alpha': 0.5, 'early': 0.4,
            'launching': 0.3, 'stealth': 0.3, 'deployed': 0.3
        }

        self.vader.lexicon.update(crypto_lexicon)
        print("[OK] VADER initialized with crypto lexicon")

    def init_twitter_client(self):
        """Initialize twikit client with cookies.json"""
        if not os.path.exists("cookies.json"):
            print("[ERROR] cookies.json not found!")
            sys.exit(1)

        try:
            self.client = Client('en-US')
            with open("cookies.json", 'r') as f:
                cookie_data = json.load(f)

            if isinstance(cookie_data, dict) and 'cookies' in cookie_data:
                cookies = cookie_data['cookies']
                with open("cookies.json", 'w') as f:
                    json.dump(cookies, f)

            self.client.load_cookies("cookies.json")
            print("[OK] Twitter client initialized")
        except Exception as e:
            print(f"[ERROR] Twitter client init failed: {e}")
            sys.exit(1)

    def extract_mentioned_tokens(self, text):
        """Extract any crypto tokens mentioned in tweet"""
        mentioned = []
        text_upper = text.upper()

        # Check for $ prefixed tokens
        import re
        dollar_tokens = re.findall(r'\$([A-Z]{2,10})', text_upper)
        mentioned.extend(dollar_tokens)

        # Check for known tokens without $
        for token in PRIORITY_TOKENS:
            if token in text_upper:
                mentioned.append(token)

        # Deduplicate
        return list(set(mentioned))

    def calculate_whale_signal_strength(self, username, text, followers):
        """Calculate how strong this whale signal is"""
        signal = 1.0

        # Account type multiplier
        account_type = WHALE_ACCOUNTS.get(username, '')
        if 'Alpha Caller' in account_type:
            signal *= 2.0  # Alpha callers get 2x weight
        elif 'Insider' in account_type:
            signal *= 3.0  # Insiders get 3x weight
        elif 'Flow Signal' in account_type:
            signal *= 1.5  # Flow signals get 1.5x

        # Keywords that indicate strong signals
        strong_signals = ['launching', 'deployed', 'stealth', 'gem', 'early',
                         'accumulate', 'buying', 'loaded', 'aped']
        for keyword in strong_signals:
            if keyword in text.lower():
                signal *= 1.2

        # Multiple token mentions might dilute signal
        tokens = self.extract_mentioned_tokens(text)
        if len(tokens) > 3:
            signal *= 0.8  # Too many tokens = less focused

        return signal

    async def get_whale_tweets(self, username):
        """Get recent tweets from a specific whale account"""
        collected = []

        try:
            print(f"  Checking @{username}...")
            time.sleep(randint(2, 4))  # Be respectful

            # Get user object first
            user = await self.client.get_user_by_screen_name(username)

            if not user:
                print(f"    [WARN] User @{username} not found")
                return collected

            # Get user's tweets
            tweets = await self.client.get_user_tweets(
                user.id,
                tweet_type='Tweets',
                count=TWEETS_PER_WHALE
            )

            if tweets:
                for tweet in tweets:
                    # Skip if we've seen this tweet before
                    if tweet.id == self.last_tweet_ids.get(username):
                        break

                    # Skip retweets (we want original content)
                    if hasattr(tweet, 'retweeted_status') and tweet.retweeted_status:
                        continue

                    tweet_data = {
                        'tweet_id': tweet.id,
                        'username': username,
                        'text': tweet.text,
                        'followers': getattr(user, 'followers_count', 0),
                        'following': getattr(user, 'following_count', 0),
                        'bio': getattr(user, 'description', None),
                        'verified': getattr(user, 'verified', False),
                        'retweets': getattr(tweet, 'retweet_count', 0) or 0,
                        'likes': getattr(tweet, 'favorite_count', 0) or 0,
                        'created_at': getattr(tweet, 'created_at', datetime.now()),
                        'timestamp': datetime.now(),
                        'mentioned_tokens': self.extract_mentioned_tokens(tweet.text),
                        'account_type': WHALE_ACCOUNTS.get(username, 'Unknown')
                    }

                    collected.append(tweet_data)

                if collected:
                    # Update last seen tweet
                    self.last_tweet_ids[username] = collected[0]['tweet_id']
                    print(f"    [OK] Found {len(collected)} new tweets")
                else:
                    print(f"    [INFO] No new tweets")

        except TooManyRequests as e:
            reset_time = datetime.fromtimestamp(e.rate_limit_reset)
            wait_seconds = (reset_time - datetime.now()).total_seconds() + randint(5, 10)
            print(f"Rate limited. Waiting {int(wait_seconds)}s...")
            await asyncio.sleep(wait_seconds)
        except Exception as e:
            print(f"    [ERROR] Failed to fetch @{username}: {e}")

        return collected

    def save_to_db(self, all_tweets):
        """Save whale tweets with special handling"""
        if not all_tweets:
            return

        cursor = self.db_conn.cursor()
        saved = 0
        high_signal_tweets = []

        for tweet in all_tweets:
            # Analyze sentiment
            sentiment = self.vader.polarity_scores(tweet['text'])['compound']

            # Calculate signal strength
            signal_strength = self.calculate_whale_signal_strength(
                tweet['username'],
                tweet['text'],
                tweet['followers']
            )

            # Weighted score (sentiment × followers × signal_strength)
            weighted_score = sentiment * (tweet['followers'] ** 0.5) * signal_strength

            # Determine alert level - whales get boosted alerts
            if signal_strength >= 2.0 and abs(sentiment) > 0.3:
                alert_level = "WHALE_SIGNAL"
            elif weighted_score > 100 or signal_strength >= 1.5:
                alert_level = "HIGH"
            elif weighted_score > 50:
                alert_level = "MEDIUM"
            else:
                alert_level = "LOW"

            # Track high signal tweets for alerts
            if alert_level in ["WHALE_SIGNAL", "HIGH"] and tweet['mentioned_tokens']:
                high_signal_tweets.append({
                    'username': tweet['username'],
                    'tokens': tweet['mentioned_tokens'],
                    'text_preview': tweet['text'][:100],
                    'signal': signal_strength
                })

            # Save each mentioned token as separate entry
            tokens_to_save = tweet['mentioned_tokens'] if tweet['mentioned_tokens'] else ['GENERAL']

            for token in tokens_to_save:
                try:
                    cursor.execute("""
                        INSERT INTO twitter_sentiment
                        (tweet_id, token, tweet_text, sentiment_score, sentiment_label,
                         author_username, author_followers, retweet_count, like_count,
                         tweet_created_at, scraped_at, weighted_score, alert_level,
                         is_whale, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        round(weighted_score, 4),
                        alert_level,
                        True,  # All whale watchlist accounts are considered whales
                        'whale_tracker'  # Source identifier
                    ))

                    if cursor.rowcount > 0:
                        saved += 1

                except Exception as e:
                    self.db_conn.rollback()
                    print(f"[ERROR] Failed to save tweet: {e}")

        self.db_conn.commit()
        cursor.close()

        print(f"\n[OK] Saved {saved} new whale tweets")

        # Alert on high signal tweets
        if high_signal_tweets:
            print("\n" + "="*70)
            print("🐋 WHALE ALERTS - HIGH SIGNAL TWEETS 🐋")
            print("="*70)
            for alert in high_signal_tweets:
                tokens_str = ', '.join(alert['tokens'])
                print(f"@{alert['username']} ({alert['signal']:.1f}x signal)")
                print(f"Tokens: {tokens_str}")
                print(f"Preview: {alert['text_preview']}...")
                print("-"*70)

    async def run_cycle(self):
        """Check all whale accounts"""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting whale check cycle")
        print(f"Monitoring {len(WHALE_ACCOUNTS)} whale accounts...")

        all_tweets = []

        for username in WHALE_ACCOUNTS.keys():
            tweets = await self.get_whale_tweets(username)
            all_tweets.extend(tweets)

        if all_tweets:
            self.save_to_db(all_tweets)

        # Show summary
        cursor = self.db_conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(DISTINCT tweet_id) as total_tweets,
                COUNT(DISTINCT token) as tokens_mentioned,
                COUNT(DISTINCT author_username) as whales_active,
                MAX(weighted_score) as max_signal
            FROM twitter_sentiment
            WHERE source = 'whale_tracker'
                AND scraped_at > NOW() - INTERVAL '10 minutes'
        """)

        total, tokens, whales, max_signal = cursor.fetchone()

        print(f"\nCycle Summary:")
        print(f"  New whale tweets: {total or 0}")
        print(f"  Tokens mentioned: {tokens or 0}")
        print(f"  Active whales: {whales or 0}")
        print(f"  Max signal strength: {max_signal:.1f}" if max_signal else "  Max signal: N/A")

        cursor.close()

    async def run(self):
        """Main loop - runs every 10 minutes"""
        print("\n" + "="*60)
        print("Twitter Whale Tracker - High Signal Account Monitor")
        print(f"Tracking {len(WHALE_ACCOUNTS)} known market movers")
        print("="*60)

        self.init_db()
        self.init_vader()
        self.init_twitter_client()

        while True:
            try:
                await self.run_cycle()

                print(f"\nNext whale check in {POLLING_INTERVAL//60} minutes...")
                await asyncio.sleep(POLLING_INTERVAL)

            except KeyboardInterrupt:
                print("\n[INFO] Shutting down whale tracker...")
                break
            except Exception as e:
                print(f"[ERROR] Cycle failed: {e}")
                await asyncio.sleep(60)

async def main():
    tracker = WhaleTracker()
    await tracker.run()

if __name__ == "__main__":
    asyncio.run(main())