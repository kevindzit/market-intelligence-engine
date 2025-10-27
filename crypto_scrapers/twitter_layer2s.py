"""
Twitter Layer 2 Scraper
Tracks Ethereum Layer 2 scaling solution sentiment
Focus: Ethereum L2s - sentiment drives TVL migration and ecosystem growth
"""

import os
import sys
import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
from random import randint
from dotenv import load_dotenv
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from monitors.health_monitor import HealthMonitor
from nice_funcs.twitter_funcs import (
    setup_httpx_patching,
    init_vader_with_crypto_lexicon,
    init_twitter_client,
    auto_refresh_cookies,
    get_db_connection,
    calculate_bot_probability,
    calculate_influence_weight,
    detect_pump_pattern,
    analyze_sentiment,
    calculate_volume_spike,
    calculate_token_velocity_metrics,
    update_token_sentiment_history,
    SPAM_KEYWORDS
)

# Setup httpx patching before importing twikit
setup_httpx_patching()

from twikit import TooManyRequests

# LAYER 2 TOKENS - Ethereum scaling solutions (sentiment drives L2 migration)
TOKENS_TO_TRACK = [
    "ARB",      # Arbitrum - $12.5B TVL, largest L2, DAO governance
    "OP",       # Optimism - $7.8B TVL, OP Stack, superchain vision
    "MATIC",    # Polygon - $4.5B TVL, zkEVM, enterprise adoption
    "METIS",    # Metis - Optimistic rollup, decentralized sequencer
    "IMX"       # Immutable X - Gaming/NFT L2, StarkEx-based
]

TWEETS_PER_TOKEN = 30  # 5 tokens × 30 tweets = ~30 searches (60% rate limit usage)
POLLING_INTERVAL = 5 * 60  # 5 minutes (optimal for signal freshness)
MIN_FOLLOWERS = 5000  # Quality filter to reduce bot/spam noise

# Database config
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

class TwitterLayer2s:
    def __init__(self):
        self.client = None
        self.vader = None
        self.db_conn = None
        self.volume_baseline = defaultdict(lambda: {'count': 20.0, 'history': []})
        self.last_poll_time = defaultdict(lambda: datetime.now() - timedelta(hours=1))
        self.health = HealthMonitor('twitter_layer2s', alert_threshold=5)  # 5 empty cycles before alert (adjusted for MIN_FOLLOWERS filter)

        # Velocity tracking - stores last 3 cycles per token
        self.sentiment_history = defaultdict(list)  # {token: [{'time': ..., 'sentiment': ..., 'volume_spike': ...}]}
        self.cycle_interval = POLLING_INTERVAL / 60.0  # Convert to minutes for velocity calc

    def init_db(self):
        self.db_conn = get_db_connection(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
        self.load_volume_baseline()

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
        """Initialize VADER with crypto lexicon"""
        self.vader = init_vader_with_crypto_lexicon()

    def init_twitter_client(self):
        """Initialize twikit client"""
        self.client = init_twitter_client()

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

                    # Quality filter - skip low-follower accounts (reduces 56% of bot noise)
                    followers = getattr(user, 'followers_count', 0) if user else 0
                    if followers < MIN_FOLLOWERS:
                        continue

                    tweet_data = {
                        'tweet_id': tweet.id,
                        'token': token.upper(),  # Always uppercase for consistency
                        'text': tweet.text,
                        'username': getattr(user, 'screen_name', 'unknown') if user else 'unknown',
                        'followers': followers,
                        'following': getattr(user, 'following_count', getattr(user, 'friends_count', 0)) if user else 0,
                        'bio': getattr(user, 'description', None) if user else None,
                        'profile_image_custom': hasattr(user, 'profile_image_url') if user else False,
                        'verified': getattr(user, 'verified', False) if user else False,
                        'retweets': getattr(tweet, 'retweet_count', 0) or 0,
                        'likes': getattr(tweet, 'favorite_count', 0) or 0,
                        'replies': getattr(tweet, 'reply_count', 0) or 0,
                        'quotes': getattr(tweet, 'quote_count', 0) or 0,
                        'created_at': getattr(tweet, 'created_at', datetime.now()),
                        'timestamp': datetime.now(),
                        # Extract metadata for AI analysis
                        'has_urls': bool('http://' in tweet.text or 'https://' in tweet.text),
                        'hashtag_count': tweet.text.count('#')
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
            if '404' in error_msg or 'unauthorized' in error_msg or 'forbidden' in error_msg:
                print(f"[WARN] Authentication error detected: {e}")
                raise  # Raise to trigger global cookie refresh in main loop
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
            volume_spike = calculate_volume_spike(self.volume_baseline, token, len(tweets))

            if volume_spike >= 2.0:  # 2x baseline = strong signal
                volume_alerts.append((token, volume_spike, len(tweets)))

            # Calculate average sentiment for velocity tracking
            sentiments = [analyze_sentiment(self.vader, t['text']) for t in tweets]
            avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0

            # Calculate velocity metrics
            velocity_metrics = calculate_token_velocity_metrics(self.sentiment_history, token, avg_sentiment, volume_spike)
            if velocity_metrics:
                sentiment_velocity = velocity_metrics['sentiment_velocity']
                volume_acceleration = velocity_metrics['volume_acceleration']
                momentum_score = velocity_metrics['momentum']
            else:
                sentiment_velocity = None
                volume_acceleration = None
                momentum_score = None

            # Update history for next cycle
            update_token_sentiment_history(self.sentiment_history, token, avg_sentiment, volume_spike)

            # Detect pump patterns
            pump_score = detect_pump_pattern(tweets, SPAM_KEYWORDS)

            for tweet in tweets:
                # Analyze sentiment
                sentiment = analyze_sentiment(self.vader, tweet['text'])

                # Calculate influence-weighted score
                user_data = {
                    'followers': tweet['followers'],
                    'following': tweet['following'],
                    'username': tweet['username'],
                    'bio': tweet['bio'],
                    'profile_image_custom': tweet['profile_image_custom']
                }
                engagement_data = {'retweets': tweet['retweets'], 'likes': tweet['likes']}

                influence_weight = calculate_influence_weight(user_data, engagement_data)
                weighted_sentiment = sentiment * influence_weight

                # Bot probability
                bot_prob = calculate_bot_probability(user_data)

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
                         reply_count, quote_count,
                         tweet_created_at, scraped_at, weighted_score, alert_level,
                         is_whale, volume_spike, bot_probability, pump_score, influence_weight, source,
                         verified, has_urls, hashtag_count, following_count,
                         sentiment_velocity, volume_acceleration, momentum_score)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        tweet['replies'],
                        tweet['quotes'],
                        tweet['created_at'],
                        tweet['timestamp'],
                        round(weighted_sentiment, 4),
                        alert_level,
                        tweet['followers'] >= 100000,
                        round(volume_spike, 2),
                        round(bot_prob, 3),
                        round(pump_score, 3) if pump_score > 0.5 else None,
                        round(influence_weight, 4),
                        'layer2s',  # Source identifier for Layer 2 blockchain searches
                        tweet.get('verified', False),
                        tweet.get('has_urls', False),
                        tweet.get('hashtag_count', 0),
                        tweet.get('following', 0),
                        round(sentiment_velocity, 6) if sentiment_velocity is not None else None,
                        round(volume_acceleration, 6) if volume_acceleration is not None else None,
                        round(momentum_score, 6) if momentum_score is not None else None
                    ))

                    if cursor.rowcount > 0:
                        saved += 1

                except Exception:
                    if self.db_conn:
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

        all_tweets = []

        # Collect tweets - retry once with fresh cookies if auth fails
        for attempt in range(2):  # Max 2 attempts: original + 1 retry after cookie refresh
            try:
                for token in TOKENS_TO_TRACK:
                    tweets = await self.get_tweets_for_token(token)
                    all_tweets.extend(tweets)
                break  # Success - exit retry loop

            except Exception as e:
                error_msg = str(e).lower()
                if '404' in error_msg or 'unauthorized' in error_msg or 'forbidden' in error_msg:
                    if attempt == 0:  # First attempt failed
                        print(f"\n[AUTH ERROR] Authentication failed. Refreshing cookies...")
                        new_client = auto_refresh_cookies(self.client)
                        if new_client:
                            self.client = new_client
                            print(f"[RETRY] Retrying all tokens with fresh client...")
                            all_tweets = []  # Clear any partial results
                            continue  # Retry the loop
                        else:
                            print(f"[FATAL] Cookie refresh failed after 10 attempts. Skipping this cycle.")
                            break
                    else:  # Second attempt also failed
                        print(f"[FATAL] Still failing after cookie refresh. Skipping this cycle.")
                        break
                else:
                    # Non-auth error - just log and continue
                    print(f"[ERROR] Unexpected error: {e}")
                    break

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
                    sent = analyze_sentiment(self.vader, tweet['text'])
                    sentiments.append(sent)
                avg_sent = sum(sentiments) / len(sentiments) if sentiments else 0

                print(f"{token:<10} | {count:<8} | {human_pct:>8.0f}% | {avg_sent:>9.3f}")

                # Calculate volume spike for velocity tracking
                baseline = float(self.volume_baseline[token]['count'] or 20.0)
                volume_spike = float(count) / (baseline + 1.0)

                velocity = calculate_token_velocity_metrics(self.sentiment_history, token, avg_sent, volume_spike)

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
                update_token_sentiment_history(self.sentiment_history, token, avg_sent, volume_spike)

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
        print("Twitter Layer 2 Scraper")
        print("Tracking: ARB, OP, MATIC, METIS, IMX")
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
    scraper = TwitterLayer2s()
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(main())
