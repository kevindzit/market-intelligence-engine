"""
Twitter Whale Tracker - Monitors specific high-signal accounts
Tracks known market movers, alpha callers, and insider accounts
Designed to catch every tweet from whitelisted accounts
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
    get_pooled_client,
    auto_refresh_cookies,
    get_db_connection,
    calculate_bot_probability,
    calculate_influence_weight,
    analyze_sentiment,
    calculate_whale_velocity_metrics,
    update_whale_sentiment_history
)

# Setup httpx patching before importing twikit
setup_httpx_patching()

from twikit import TooManyRequests

# WHALE WATCHLIST - High-signal accounts that move markets
# CURRENT: 42 accounts (rate limit safe, MAX = 45)
# Updated: October 29, 2025 - Added 4 top-tier 2025 influencers
WHALE_ACCOUNTS = {
    # ========== ALPHA CALLERS & EARLY GEM SPECIALISTS (15) ==========
    'blknoiz06': 'Alpha Caller (MOG, WIF) - Ansem, meme king, $20-30M net worth',
    'LarpVonTrier': 'Alpha Caller (KeyCat)',
    'artsch00lreject': 'Alpha Caller (PopCat)',
    'thecexoffender': 'Alpha Caller (Early gems)',
    'larpalt': 'Alpha Caller (Super early memes)',
    'iambroots': 'Trader (Early gems)',
    'UniswapVillain': 'Trader (Early gems)',
    'CrashiusClay69': 'Trader (Early gems)',
    'Kmoney_69': 'Meme Coin Maestro (MOG/PEPE/TRUMP) - 10x gains',
    'ValueandTime': 'Trading Signals & Stories',
    'Cryptozins': 'Wallet Tracking CEO (100% win rate claim)',
    'FrankDeGods': 'Community Leader & Social Experimenter',
    'zachxbt': 'Crypto Detective (Scam exposure)',
    'tier10k': 'Alpha Caller (Hidden gems)',
    'MustStopMurad': 'Alpha Caller (Meme super cycle) - Works with Ansem',
    'Trader_XO_': 'Alpha Caller (500K) - Precise altcoin setups, swing trading',

    # ========== INSIDERS & DEPLOYERS (2) ==========
    'GamesMasterFlex': 'Insider (Dogwifhat organizer)',
    'degenharambe': 'Insider (PEPE founder alias)',

    # ========== ON-CHAIN ANALYSTS & WHALE TRACKERS (9) ==========
    'lookonchain': 'On-Chain Detective (284K) - Smart money tracker',
    'woonomic': 'Senior Analyst (Willy Woo) - NVT ratio pioneer',
    'WClementeIII': 'Lead Analyst (Will Clemente, 706K) - Blockware',
    'DylanLeClair_': 'Bitcoin On-Chain Expert - Independent analyst',
    'ali_charts': 'TA Charts (Ali Martinez, 135K) - Clean explanations',
    'cryptoquant_com': 'On-Chain Platform - Real-time insights',
    'rasmr_eth': 'Blockchain Researcher - Trading signals',
    'DeBankDeFi': 'Flow Signal (Whale tracking DeFi)',
    'arkhamintel': 'On-Chain Intel (331K) - Whale movements, multi-chain',

    # ========== TECHNICAL ANALYSIS EXPERTS (3) ==========
    'CryptoCred': 'Technical Analysis Expert (700K) - London-based',
    'SmartContractor': 'Technical Analysis (Bluntz) - Elliott Wave',
    'VentureCoinist': 'TA Expert (308K) - Trade entries',

    # ========== HIGH-PROFILE GENERAL CRYPTO (7) ==========
    'Ashcryptoreal': 'Dubai Analyst (1.7M) - Market forecasts since 2015',
    'thecryptodog': 'Altcoin Commentary (715K) - Top altcoins',
    'Pentosh1': 'Free Alpha Provider (700K+) - 4+ years',
    'BenjaminCowen': 'Data-Driven Cycles - Math-based logic',
    'VitalikButerin': 'Ethereum Co-Founder - Macro insights',
    'APompliano': 'Anthony Pompliano - Macro + Bitcoin',
    'CryptoKaleo': 'Options Trader (473K) - Daily market commentary, top calls',

    # ========== PLATFORM/ECOSYSTEM (6) ==========
    'TheCryptoLark': 'Market Analysis (Lark Davis) - Meme updates',
    'DegenerateNews': 'Solana News & NFTs - Breaking news',
    'pumpdotfun': 'Solana Launch Platform - Pump alerts',
    'BasedBrett': 'Base Chain Memecoin - Official account',
    'Aeyakovenko': 'Solana Co-Founder - Anatoly Yakovenko',
    'whale_alert': 'Flow Signal (Large transactions) - Real-time alerts',
}  # Total: 42 accounts (3 slots available for new whales)

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
        self.db_pool = None  # Changed from db_conn to db_pool
        self.last_tweet_ids = defaultdict(str)  # Track last seen tweet per whale
        self.health = HealthMonitor('twitter_whales', alert_threshold=10)

        # Velocity tracking - stores last 3 cycles per token
        self.sentiment_history = defaultdict(list)  # {token: [{'time': ..., 'sentiment': ..., 'tweet_count': ...}]}
        self.cycle_interval = POLLING_INTERVAL / 60.0  # Convert to minutes for velocity calc

    def init_db(self):
        """Initialize database connection pool

        Note: last_tweet_ids tracks seen tweets within current session only.
        Database ON CONFLICT clause handles cross-session duplicates automatically.
        """
        self.db_pool = get_db_connection(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)

    def init_vader(self):
        """Initialize VADER with crypto lexicon"""
        self.vader = init_vader_with_crypto_lexicon()

    def init_twitter_client(self):
        """Initialize twikit client from account pool"""
        self.client = get_pooled_client()

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
                        'replies': getattr(tweet, 'reply_count', 0) or 0,
                        'quotes': getattr(tweet, 'quote_count', 0) or 0,
                        'created_at': getattr(tweet, 'created_at', datetime.now()),
                        'timestamp': datetime.now(),
                        'mentioned_tokens': self.extract_mentioned_tokens(tweet.text),
                        'account_type': WHALE_ACCOUNTS.get(username, 'Unknown'),
                        # Extract metadata for AI analysis
                        'has_urls': bool('http://' in tweet.text or 'https://' in tweet.text),
                        'hashtag_count': tweet.text.count('#')
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
            error_msg = str(e).lower()
            # Check for authentication errors - raise to trigger global cookie refresh
            if '404' in error_msg or 'unauthorized' in error_msg or 'forbidden' in error_msg:
                print(f"    [WARN] Authentication error for @{username}: {e}")
                raise  # Raise to trigger global cookie refresh in main loop
            print(f"    [ERROR] Failed to fetch @{username}: {e}")

        return collected

    def save_to_db(self, all_tweets):
        """Save whale tweets with special handling"""
        if not all_tweets:
            return 0

        conn = self.db_pool.get_connection()
        if not conn:
            print("[ERROR] Could not get database connection to save whale tweets")
            return 0

        try:
            cursor = conn.cursor()
            saved = 0
            high_signal_tweets = []

            for tweet in all_tweets:
                # Analyze sentiment
                sentiment = analyze_sentiment(self.vader, tweet['text'])

                # Calculate signal strength
                signal_strength = self.calculate_whale_signal_strength(
                    tweet['username'],
                    tweet['text'],
                    tweet['followers']
                )

                # Calculate normalized engagement coefficient (0-1 scale)
                user_data = {
                    'followers': tweet['followers'],
                    'following': tweet.get('following', 0),
                    'username': tweet['username'],
                    'bio': tweet.get('bio'),
                    'profile_image_custom': True  # Whales have custom images
                }
                engagement_data = {'likes': tweet.get('likes', 0), 'retweets': tweet.get('retweets', 0)}

                # Calculate bot probability (for security monitoring)
                bot_prob = calculate_bot_probability(user_data)

                influence_weight = calculate_influence_weight(user_data, engagement_data, use_bot_penalty=False)

                # Weighted score using Yale engagement coefficient
                # influence_weight (0-1) × 100 to maintain alert threshold compatibility
                # Replaces follower^0.5 with research-backed engagement normalization
                weighted_score = sentiment * signal_strength * (influence_weight * 100)

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
                            round(weighted_score, 4),
                            alert_level,
                            True,  # All whale watchlist accounts are considered whales
                            None,  # volume_spike - N/A for account-based tracking
                            round(bot_prob, 3),  # bot_probability - for security monitoring
                            None,  # pump_score - whales are trusted sources
                            round(influence_weight, 4),
                            'whale_tracker',  # Source identifier
                            tweet.get('verified', False),
                            tweet.get('has_urls', False),
                            tweet.get('hashtag_count', 0),
                            tweet.get('following', 0),
                            None,  # sentiment_velocity - calculated per token, not per tweet
                            None,  # volume_acceleration - N/A for account-based
                            None   # momentum_score - N/A for account-based
                        ))

                        if cursor.rowcount > 0:
                            saved += 1

                    except Exception as e:
                        print(f"[WARNING] Failed to insert whale tweet: {e}")
                        conn.rollback()

            conn.commit()
            cursor.close()

            print(f"\n[OK] Saved {saved} new whale tweets")

            # Show count of high signal tweets without previews
            if high_signal_tweets:
                print(f"[INFO] {len(high_signal_tweets)} high-signal tweets detected (saved to database)")

            return saved

        except Exception as e:
            print(f"[ERROR] Database operation failed: {e}")
            if conn:
                conn.rollback()
            return 0

        finally:
            if conn:
                self.db_pool.return_connection(conn)

    async def run_cycle(self):
        """Check all whale accounts"""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting whale check cycle")
        print(f"Monitoring {len(WHALE_ACCOUNTS)} whale accounts...")

        all_tweets = []

        # Check whale accounts - retry up to 10 times with fresh cookies if auth fails
        max_refresh_attempts = 10
        for refresh_attempt in range(max_refresh_attempts):
            try:
                for username in WHALE_ACCOUNTS.keys():
                    tweets = await self.get_whale_tweets(username)
                    all_tweets.extend(tweets)
                break  # Success - exit retry loop

            except Exception as e:
                error_msg = str(e).lower()
                if '404' in error_msg or 'unauthorized' in error_msg or 'forbidden' in error_msg:
                    # Auth error - refresh cookies and retry
                    print(f"\n[AUTH ERROR] Authentication failed (refresh cycle {refresh_attempt + 1}/{max_refresh_attempts})")
                    print(f"[REFRESH] Getting fresh cookies and creating new client...")

                    new_client = auto_refresh_cookies(self.client)
                    if new_client:
                        self.client = new_client
                        all_tweets = []  # Clear any partial results
                        print(f"[RETRY] Retrying all whale accounts with fresh client...")
                        continue  # Retry the loop with new client
                    else:
                        print(f"[FATAL] Failed to refresh cookies. Skipping this cycle.")
                        break
                else:
                    # Non-auth error - just log and continue
                    print(f"[ERROR] Unexpected error: {e}")
                    break
        else:
            # Loop completed without break = hit max attempts
            print(f"[FATAL] Still failing after {max_refresh_attempts} refresh attempts. Skipping this cycle.")

        # Save tweets and track health
        saved = 0
        if all_tweets:
            saved = self.save_to_db(all_tweets)

        self.health.record_cycle(saved)

        # Calculate velocity metrics per token
        momentum_alerts = []
        if all_tweets and self.vader:
            # Group tweets by token to analyze sentiment velocity
            by_token = defaultdict(list)
            for tweet in all_tweets:
                for token in tweet.get('mentioned_tokens', ['GENERAL']):
                    by_token[token].append(tweet)

            for token, tweets in by_token.items():
                if token == 'GENERAL':  # Skip general tweets without specific tokens
                    continue

                # Calculate average whale sentiment for this token
                sentiments = []
                for tweet in tweets:
                    sentiment = analyze_sentiment(self.vader, tweet['text'])
                    sentiments.append(sentiment)

                avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
                tweet_count = len(tweets)

                # Calculate velocity
                velocity = calculate_whale_velocity_metrics(self.sentiment_history, token, avg_sentiment, tweet_count)

                if velocity:
                    # Check for significant whale momentum (lower threshold since whales are high-signal)
                    if velocity['sentiment_velocity'] > 0.03 and velocity['volume_change'] > 0.1:  # Per minute
                        momentum_alerts.append({
                            'token': token,
                            'velocity': velocity,
                            'current_sentiment': avg_sentiment,
                            'current_tweet_count': tweet_count,
                            'whale_count': len(set(t['username'] for t in tweets))
                        })

                # Update history
                update_whale_sentiment_history(self.sentiment_history, token, avg_sentiment, tweet_count)

        # Print momentum alerts (whale signals are especially important!)
        if momentum_alerts:
            print("\n" + "="*70)
            print("🐋 WHALE MOMENTUM ALERTS (HIGH-SIGNAL ACCOUNTS ACCELERATING)")
            print("="*70)
            for alert in sorted(momentum_alerts, key=lambda x: x['velocity']['momentum'], reverse=True):
                v = alert['velocity']
                print(f"\n{alert['token']}:")
                print(f"  Whale count: {alert['whale_count']}")
                print(f"  Sentiment velocity: {v['sentiment_velocity']:+.3f}/min ({v['prev_sentiment']:.2f} → {alert['current_sentiment']:.2f})")
                print(f"  Volume change: {v['volume_change']:+.1f} tweets/min ({int(v['prev_tweet_count'])} → {alert['current_tweet_count']})")
                print(f"  Momentum score: {v['momentum']:.3f}")

                # Classify signal strength (whales get stronger signals)
                if v['momentum'] > 0.03:
                    print(f"  Signal: 🔥🐋 WHALE STRONG BUY - Multiple whales accelerating!")
                elif v['momentum'] > 0.01:
                    print(f"  Signal: ⚡🐋 WHALE BUY - Whale sentiment building")
                else:
                    print(f"  Signal: 📈🐋 WHALE WATCH - Positive whale momentum")
            print("="*70)

        # Show summary (use saved count instead of querying database to avoid timezone issues)
        if all_tweets:
            # Group by token to count unique mentions
            tokens_mentioned = set()
            whales_active = set()
            for tweet in all_tweets:
                for token in tweet.get('mentioned_tokens', []):
                    if token != 'GENERAL':
                        tokens_mentioned.add(token)
                whales_active.add(tweet['username'])

            print(f"\nCycle Summary:")
            print(f"  New whale tweets: {saved}")
            print(f"  Tokens mentioned: {len(tokens_mentioned)}")
            print(f"  Active whales: {len(whales_active)}")
        else:
            print(f"\nCycle Summary:")
            print(f"  New whale tweets: 0")
            print(f"  Tokens mentioned: 0")
            print(f"  Active whales: 0")

        # Health status
        self.health.print_health_summary()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Cycle completed")

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