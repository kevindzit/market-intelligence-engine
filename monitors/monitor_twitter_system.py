"""
Unified Twitter System Monitor
Combines: database overview, recent tweets, trading signals, and multi-scraper status
One script to see everything about your Twitter data collection system
"""
import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)

cur = conn.cursor()

print("\n" + "="*120)
print(f"TWITTER SYSTEM MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*120)

# ============================================================================
# SECTION 1: DATABASE OVERVIEW
# ============================================================================
print("\n" + "="*120)
print("1. DATABASE OVERVIEW")
print("="*120)

# Total tweets
cur.execute("SELECT COUNT(*) FROM twitter_sentiment")
total = cur.fetchone()[0]
print(f"Total tweets in database: {total:,}")

# Time windows
print("\nTweets by time window:")
time_windows = [
    ("Last 5 minutes", "5 minutes"),
    ("Last 15 minutes", "15 minutes"),
    ("Last 30 minutes", "30 minutes"),
    ("Last 1 hour", "1 hour"),
    ("Last 6 hours", "6 hours"),
    ("Last 24 hours", "24 hours"),
]

for label, interval in time_windows:
    cur.execute(f"""
        SELECT COUNT(*), MIN(scraped_at), MAX(scraped_at)
        FROM twitter_sentiment
        WHERE scraped_at > NOW() - INTERVAL '{interval}'
    """)
    count, min_time, max_time = cur.fetchone()
    if count > 0:
        print(f"  {label:<20}: {count:>5,} tweets")

# Tokens tracked
print("\nTokens in database:")
cur.execute("""
    SELECT token, COUNT(*) as total, MAX(scraped_at) as last_scraped
    FROM twitter_sentiment
    GROUP BY token
    ORDER BY total DESC
""")

for token, count, last in cur.fetchall():
    age = (datetime.now() - last.replace(tzinfo=None)) if last else None
    age_str = f"{int(age.total_seconds() / 60)}m ago" if age and age.total_seconds() < 3600 else f"{int(age.total_seconds() / 3600)}h ago" if age else "N/A"
    print(f"  {token:<10}: {count:>6,} tweets (last: {age_str})")

# ============================================================================
# SECTION 2: DATA SOURCES STATUS
# ============================================================================
print("\n" + "="*120)
print("2. DATA SOURCES STATUS (Last Hour)")
print("="*120)

cur.execute("""
    SELECT
        source,
        COUNT(*) as tweets,
        COUNT(DISTINCT token) as tokens,
        COUNT(DISTINCT author_username) as users,
        MAX(scraped_at) as last_update,
        NOW() - MAX(scraped_at) as age
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
    GROUP BY source
    ORDER BY tweets DESC
""")

print(f"\n{'Source':<20} | {'Tweets':>8} | {'Tokens':>8} | {'Users':>8} | {'Last Update':<25} | {'Age'}")
print("-"*120)

for source, tweets, tokens, users, last_update, age in cur.fetchall():
    age_str = f"{int(age.total_seconds() / 60)}m ago" if age.total_seconds() < 3600 else f"{int(age.total_seconds() / 3600)}h ago"
    print(f"{source:<20} | {tweets:>8} | {tokens:>8} | {users:>8} | {str(last_update):<25} | {age_str}")

# ============================================================================
# SECTION 3: WHALE SIGNALS
# ============================================================================
print("\n" + "="*120)
print("3. WHALE SIGNALS (High-Value Account Activity)")
print("="*120)

cur.execute("""
    SELECT
        author_username,
        COUNT(DISTINCT token) as tokens_mentioned,
        array_agg(DISTINCT token ORDER BY token) as token_list,
        MAX(weighted_score) as max_signal,
        MAX(scraped_at) as last_tweet
    FROM twitter_sentiment
    WHERE source = 'whale_tracker'
        AND scraped_at > NOW() - INTERVAL '30 minutes'
        AND alert_level IN ('WHALE_SIGNAL', 'HIGH')
    GROUP BY author_username
    ORDER BY max_signal DESC
    LIMIT 10
""")

whale_results = cur.fetchall()
if whale_results:
    print(f"\n{'Whale Account':<20} | {'Tokens':<40} | {'Signal':>8} | {'Last Tweet'}")
    print("-"*120)
    for username, token_count, tokens, signal, last in whale_results:
        tokens_str = ', '.join(tokens) if tokens else 'N/A'
        tokens_display = tokens_str[:40] if len(tokens_str) <= 40 else tokens_str[:37] + '...'
        print(f"{username:<20} | {tokens_display:<40} | {signal:>8.1f} | {str(last)}")
else:
    print("\nNo high-signal whale tweets in last 30 minutes")

# ============================================================================
# SECTION 4: TRADING SIGNALS
# ============================================================================
print("\n" + "="*120)
print("4. ACTIVE TRADING SIGNALS (Last 15 Minutes)")
print("="*120)
print(f"{'Token':<10} | {'Signal':<12} | {'Volume':<10} | {'Sentiment':<10} | {'Tweets':<8} | {'Pump Risk':<10} | {'Action'}")
print("-"*120)

cur.execute("""
    SELECT
        token,
        CASE
            WHEN MAX(volume_spike) >= 3.0 AND AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) > 0.2
                THEN 'STRONG BUY'
            WHEN MAX(volume_spike) >= 2.0 AND AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) > 0.1
                THEN 'BUY'
            WHEN MAX(volume_spike) >= 2.0 AND AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) < -0.2
                THEN 'SELL'
            WHEN MAX(pump_score) >= 0.7
                THEN 'PUMP WARN'
            ELSE 'HOLD'
        END as signal,
        MAX(volume_spike) as volume,
        AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) as quality_sentiment,
        COUNT(*) as total_tweets,
        MAX(pump_score) as pump_risk
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '15 minutes'
    GROUP BY token
    HAVING COUNT(*) >= 5
    ORDER BY 3 DESC NULLS LAST
""")

signals = []
for row in cur.fetchall():
    token, signal, volume, sentiment, tweets, pump = row
    volume_str = f"{volume:.1f}x" if volume else "baseline"
    sent_str = f"{sentiment:.3f}" if sentiment else "N/A"
    pump_str = f"{pump:.2f}" if pump else "Safe"

    action = ""
    if signal == "STRONG BUY":
        action = ">>> ENTER NOW (exit <24h)"
        signals.append((token, signal, volume))
    elif signal == "BUY":
        action = "Enter position"
    elif signal == "SELL":
        action = "Exit/Short"
    elif signal == "PUMP WARN":
        action = "!!! AVOID"
    else:
        action = "Wait"

    print(f"{token:<10} | {signal:<12} | {volume_str:<10} | {sent_str:<10} | {tweets:<8} | {pump_str:<10} | {action}")

if signals:
    print("\n" + "!!!"*40)
    print("ALERTS:")
    for token, signal, volume in signals:
        print(f"  !!! {token}: {signal} signal with {volume:.1f}x volume spike!")
    print("!!!"*40)

# ============================================================================
# SECTION 5: VOLUME SPIKE ANALYSIS
# ============================================================================
print("\n" + "="*120)
print("5. VOLUME SPIKE ANALYSIS (5-Minute Intervals)")
print("="*120)
print(f"{'Time':<8} | {'Token':<10} | {'Tweets':<8} | {'Volume':<10} | {'Human %':<10} | {'Sentiment':<10} | {'Whales'}")
print("-"*120)

cur.execute("""
    SELECT
        TO_CHAR(DATE_TRUNC('minute', scraped_at) -
                (EXTRACT(minute FROM scraped_at)::integer % 5) * INTERVAL '1 minute', 'HH24:MI') as time_5min,
        token,
        COUNT(*) as tweet_count,
        MAX(volume_spike) as max_spike,
        (COUNT(*) FILTER (WHERE bot_probability < 0.5))::float / NULLIF(COUNT(*), 0) * 100 as human_pct,
        AVG(CASE WHEN bot_probability < 0.5 THEN sentiment_score END) as human_sentiment,
        COUNT(*) FILTER (WHERE is_whale = true) as whale_count
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '30 minutes'
    GROUP BY time_5min, token
    HAVING COUNT(*) > 5
    ORDER BY time_5min DESC, max_spike DESC NULLS LAST
    LIMIT 15
""")

for row in cur.fetchall():
    time_str, token, tweets, spike, human_pct, sentiment, whales = row
    spike_str = f"{spike:.1f}x" if spike else "baseline"
    human_str = f"{human_pct:.0f}%" if human_pct else "N/A"
    sent_str = f"{sentiment:.3f}" if sentiment else "N/A"
    whale_str = f"{whales} whales" if whales > 0 else "-"

    print(f"{time_str:<8} | {token:<10} | {tweets:<8} | {spike_str:<10} | {human_str:<10} | {sent_str:<10} | {whale_str}")

# ============================================================================
# SECTION 6: BOT DETECTION
# ============================================================================
print("\n" + "="*120)
print("6. BOT ACTIVITY ANALYSIS")
print("="*120)
print(f"{'Token':<10} | {'Total':<8} | {'Bots':<8} | {'Bot %':<10} | {'Humans':<8} | {'Quality'}")
print("-"*120)

cur.execute("""
    SELECT
        token,
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE bot_probability >= 0.7) as likely_bots,
        (COUNT(*) FILTER (WHERE bot_probability >= 0.7))::float / NULLIF(COUNT(*), 0) * 100 as bot_pct,
        COUNT(*) FILTER (WHERE bot_probability < 0.3) as likely_humans,
        CASE
            WHEN (COUNT(*) FILTER (WHERE bot_probability >= 0.7))::float / NULLIF(COUNT(*), 0) > 0.5
                THEN 'X Poor'
            WHEN (COUNT(*) FILTER (WHERE bot_probability >= 0.7))::float / NULLIF(COUNT(*), 0) > 0.3
                THEN '! Suspicious'
            ELSE 'Good'
        END as quality
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
    GROUP BY token
    ORDER BY bot_pct DESC
""")

for row in cur.fetchall():
    token, total, bots, bot_pct, humans, quality = row
    bot_pct_str = f"{bot_pct:.1f}%"
    print(f"{token:<10} | {total:<8} | {bots:<8} | {bot_pct_str:<10} | {humans:<8} | {quality}")

# ============================================================================
# SECTION 7: HIGH-IMPACT INFLUENCERS
# ============================================================================
print("\n" + "="*120)
print("7. HIGH-IMPACT TWEETS (Whales & Influencers)")
print("="*120)
print(f"{'Token':<10} | {'Username':<20} | {'Followers':>12} | {'Sentiment':<10} | {'Weight':<10} | {'Alert'}")
print("-"*120)

cur.execute("""
    SELECT
        token,
        author_username,
        author_followers,
        sentiment_score,
        weighted_score,
        alert_level
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
        AND author_followers >= 100000
        AND bot_probability < 0.5
    ORDER BY weighted_score DESC
    LIMIT 10
""")

for row in cur.fetchall():
    token, username, followers, sentiment, weight, alert = row
    username_str = username[:20] if username else "unknown"
    sent_str = "Bullish" if sentiment > 0.2 else "Bearish" if sentiment < -0.2 else "Neutral"
    weight_str = f"{weight:.1f}" if weight else "N/A"
    alert_str = f"!!! {alert}" if alert else "-"

    print(f"{token:<10} | {username_str:<20} | {followers:>12,} | {sent_str:<10} | {weight_str:<10} | {alert_str}")

# ============================================================================
# SECTION 8: RECENT TWEETS SAMPLE
# ============================================================================
print("\n" + "="*120)
print("8. RECENT TWEETS SAMPLE (Last 30 Minutes)")
print("="*120)
print(f"{'Token':<8} | {'Username':<15} | {'Followers':>10} | {'Tweet':<50} | {'Sent':>6} | {'Bot':>5} | {'Source':<15}")
print("-"*120)

cur.execute("""
    SELECT
        token,
        author_username,
        author_followers,
        LEFT(tweet_text, 80) as tweet_preview,
        sentiment_score,
        bot_probability,
        source
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '30 minutes'
    ORDER BY scraped_at DESC
    LIMIT 20
""")

for row in cur.fetchall():
    token, username, followers, tweet, sentiment, bot_prob, source = row

    tweet_clean = tweet.replace('\n', ' ').strip()[:50] if tweet else "N/A"
    sent_str = f"{sentiment:.2f}" if sentiment else "N/A"
    bot_str = f"{bot_prob:.2f}" if bot_prob else "N/A"

    print(f"{token:<8} | {username:<15} | {followers:>10,} | {tweet_clean:<50} | {sent_str:>6} | {bot_str:>5} | {source:<15}")

# ============================================================================
# SECTION 9: OVERALL STATISTICS
# ============================================================================
print("\n" + "="*120)
print("9. OVERALL STATISTICS (Last Hour)")
print("="*120)

cur.execute("""
    SELECT
        COUNT(DISTINCT token) as tokens_tracked,
        COUNT(*) as total_tweets,
        COUNT(DISTINCT author_username) as unique_users,
        AVG(bot_probability) * 100 as avg_bot_prob,
        COUNT(*) FILTER (WHERE volume_spike >= 2.0) as volume_spikes,
        COUNT(*) FILTER (WHERE alert_level IN ('HIGH', 'EXTREME', 'WHALE_SIGNAL')) as high_alerts,
        MAX(weighted_score) as max_impact,
        COUNT(DISTINCT CASE WHEN source = 'whale_tracker' THEN author_username END) as active_whales,
        COUNT(DISTINCT CASE WHEN source = 'general_search' THEN token END) as general_tokens
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
""")

stats = cur.fetchone()
if stats:
    tokens, tweets, users, bot_avg, spikes, alerts, impact, whales, gen_tokens = stats
    print(f"Tokens Tracked:         {tokens}")
    print(f"  - General Search:     {gen_tokens}")
    print(f"  - Whale Mentions:     {tokens - gen_tokens if tokens and gen_tokens else 'N/A'}")
    print(f"Total Tweets:           {tweets:,}")
    print(f"Unique Users:           {users:,}")
    print(f"Active Whales:          {whales}")
    print(f"Bot Percentage:         {bot_avg:.1f}%" if bot_avg else "Bot Percentage:         N/A")
    print(f"Volume Spikes (2x+):    {spikes}")
    print(f"High Alerts:            {alerts}")
    print(f"Max Impact Score:       {impact:.1f}" if impact else "Max Impact Score:       N/A")

# ============================================================================
# TRADING TIPS
# ============================================================================
print("\n" + "="*120)
print("TRADING TIPS:")
print("- Volume spikes (2-3x) are the PRIMARY buy signal")
print("- Exit all Twitter-based positions within 24-48 hours")
print("- Ignore signals with >50% bot activity")
print("- Focus on meme coins (PEPE, DOGE, SHIB, etc), not BTC/ETH")
print("- Whale signals from insiders/alpha callers > general sentiment")
print("="*120 + "\n")

cur.close()
conn.close()
