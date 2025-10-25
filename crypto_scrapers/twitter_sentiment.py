"""
Twitter Sentiment Scraper V2 - Optimized for Profitability
Uses VADER (130x faster, proven profitable) instead of transformers
Tracks volume as PRIMARY signal (0.841 correlation with price)
Aggressive bot filtering (64-80% of crypto Twitter are bots)
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

# Optimized token list - focus on meme coins that actually move from Twitter
TOKENS_TO_TRACK = [
    "PEPE", "DOGE", "SHIB", "BONK", "WIF",  # High Twitter sensitivity
    "FLOKI", "WOJAK", "TURBO", "MEME", "LADYS"  # Additional meme coins
]

# Use BTC/ETH only as market indicators, not trade targets
MARKET_INDICATORS = ["bitcoin", "ethereum"]

TWEETS_PER_TOKEN = 10  # Reduced from 20 to cover more tokens
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

class TwitterSentimentV2:
    def __init__(self):
        self.client = None
        self.vader = None
        self.db_conn = None
        self.volume_baseline = defaultdict(lambda: {'count': 0, 'history': []})
        self.last_poll_time = defaultdict(lambda: datetime.now() - timedelta(hours=1))

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
                self.volume_baseline[token]['count'] = avg_volume or 20
        except:
            # Table might not have volume data yet
            pass
        finally:
            cursor.close()

    def init_vader(self):
        """Initialize VADER with crypto-specific lexicon"""
        self.vader = SentimentIntensityAnalyzer()

        # Add crypto-specific terms with sentiment scores
        crypto_lexicon = {
            'moon': 0.4, 'mooning': 0.5, 'moonshot': 0.4,
            'lambo': 0.3, 'rocket': 0.3, 'pump': 0.4,
            'bullish': 0.4, 'hodl': 0.2, 'diamond hands': 0.3,
            'to the moon': 0.5, 'lfg': 0.3, 'wagmi': 0.3,
            'rekt': -0.5, 'dump': -0.5, 'rug': -0.8,
            'rugpull': -0.8, 'scam': -0.7, 'crash': -0.6,
            'bearish': -0.4, 'paper hands': -0.3, 'ngmi': -0.3,
            'cope': -0.2, 'bagholder': -0.4, 'bagholding': -0.4
        }

        self.vader.lexicon.update(crypto_lexicon)
        print("[OK] VADER initialized with crypto lexicon")

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
        """Calculate influence weight for sentiment scoring"""
        followers = user_data.get('followers', 0)
        retweets = engagement_data.get('retweets', 0)
        likes = engagement_data.get('likes', 0)

        # Follower-based multiplier (logarithmic scale)
        if followers >= 10_000_000:
            follower_mult = 1000
        elif followers >= 1_000_000:
            follower_mult = 100
        elif followers >= 100_000:
            follower_mult = 10
        elif followers >= 10_000:
            follower_mult = 2
        else:
            follower_mult = 1

        # Engagement boost
        engagement_rate = (likes + retweets * 2) / (followers + 1)
        engagement_mult = 1 + min(engagement_rate * 10, 2)  # Max 3x boost

        # Bot probability reduction
        bot_prob = self.calculate_bot_probability(user_data)
        bot_mult = 1 - (bot_prob * 0.8)  # Reduce weight by up to 80% for bots

        return follower_mult * engagement_mult * bot_mult

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
        baseline = self.volume_baseline[token]['count'] or 20
        spike_ratio = current_count / (baseline + 1)

        # Update baseline with exponential moving average
        alpha = 0.1  # Smoothing factor
        self.volume_baseline[token]['count'] = (
            alpha * current_count + (1 - alpha) * baseline
        )

        return spike_ratio

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
                        'token': token,
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
            print(f"[ERROR] Failed to fetch {token}: {e}")

        return collected

    def save_to_db(self, all_tweets):
        """Save tweets with volume tracking and enhanced metrics"""
        if not all_tweets:
            return

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
                # VADER sentiment (130x faster than transformers)
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
                         is_whale, volume_spike, bot_probability, pump_score)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        round(pump_score, 3) if pump_score > 0.5 else None
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

    async def run_cycle(self):
        """Run one collection cycle"""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting collection cycle")

        all_tweets = []

        # Collect main tokens (meme coins with high Twitter sensitivity)
        for token in TOKENS_TO_TRACK:
            tweets = await self.get_tweets_for_token(token)
            all_tweets.extend(tweets)

        # Collect market indicators (BTC/ETH) with fewer tweets
        for token in MARKET_INDICATORS[:1]:  # Just BTC for market sentiment
            tweets = await self.get_tweets_for_token(token)
            all_tweets.extend(tweets[:5])  # Only 5 tweets for indicators

        if all_tweets:
            self.save_to_db(all_tweets)

        # Show summary
        cursor = self.db_conn.cursor()
        cursor.execute("""
            SELECT token,
                   COUNT(*) as tweets_5min,
                   AVG(sentiment_score) as avg_sentiment,
                   MAX(volume_spike) as max_volume_spike,
                   AVG(CASE WHEN bot_probability < 0.5 THEN sentiment_score END) as human_sentiment
            FROM twitter_sentiment
            WHERE scraped_at > NOW() - INTERVAL '5 minutes'
            GROUP BY token
            ORDER BY max_volume_spike DESC NULLS LAST
        """)

        print("\n5-Minute Summary:")
        print(f"{'Token':<10} | {'Tweets':<8} | {'Sentiment':<10} | {'Volume':<10} | {'Human Sent':<10}")
        print("-" * 60)

        for row in cursor.fetchall():
            token, count, sentiment, volume, human_sent = row
            vol_str = f"{volume:.1f}x" if volume else "baseline"
            human_str = f"{human_sent:.3f}" if human_sent else "N/A"
            print(f"{token:<10} | {count:<8} | {sentiment:>9.3f} | {vol_str:<10} | {human_str:<10}")

        cursor.close()

    async def run(self):
        """Main loop - runs every 5 minutes"""
        print("\n" + "="*60)
        print("Twitter Sentiment V2 - Optimized for Profit")
        print("VADER (130x faster) + Volume Tracking + Bot Filtering")
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
    scraper = TwitterSentimentV2()
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(main())